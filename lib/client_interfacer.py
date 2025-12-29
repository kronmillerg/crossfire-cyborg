"""
Copyright (c) 2018 Greg Kronmiller

Module for basic interfacing between CrossFire scripts and the client.
"""

import collections
import os
import platform
import select
import sys

DEBUG = False


# Must be defined before ClientInterfacer so ClientInterfacer.draw can use one
# of its members as the default value. (Well, unless we want to use None and
# then recompute the default dynamically...)
class Color:
    BLACK       =  1 # Comes out bold in new client.
    NAVY        =  2 # Same as some readables.
    RED         =  3 # Same as 'shout' or changes in level
    ORANGE      =  4 # Same as 'tell'
    BLUE        =  5 # Same as 'chat'
    DARK_ORANGE =  6
    GREEN       =  7
    PALE_GREEN  =  8
    GRAY = GREY =  9
    BROWN       = 10
    YELLOW      = 11
    PALE_YELLOW = 12

    # I just tried up to 50 on client 1.71, and 13-50 all rendered as just
    # black. I imagine the above is all the colors recognized, but I don't know
    # how robust that conclusion is (or even whether the above colors can be
    # depended on in the long-term).
    #
    # Oh, also, I get this rather telling error message in the console:
    #     [EE] (info.c::draw_ext_info) Passed invalid color from server: 14,
    #     max allowed is 13
    # So I think that settles that.
    #
    # Interestingly, on that client, color=0 renders in the same information
    # window as the rest, but it's plain black whereas color=1 is bold black.

    DEFAULT = NAVY


class ClientInterfacer(object):
    """
    Class responsible for maintaining some basic state and handling all direct
    communications with the client.

    Introduction to some terminology used when handling commands:

        When a command is issued, it goes through (up to) 3 states: queued,
        pending, done. Let's say that we've already sent a few commands to the
        server, but they haven't been executed yet. Then (1) a new command will
        first be put into a queue of commands to be sent ("queued"), stored
        until later to avoid inundating the server and risking commands being
        dropped. At some point we'll hear back from the server that some of the
        previous commands were completed, at which point (2) we pop the new
        command off of the queue and actually send it to the server. After
        this, it takes some time for the command to reach the server and for
        the server to resolve it and tell the client, during which time the
        command is "pending". Once the client hears back from the server that
        the command has been resolved, it is "done".
    """

    _numCreated = 0

    def __init__(self, targetPendingCommands=6):
        super(ClientInterfacer, self).__init__()

        # We use select() for non-blocking reads from stdin, which won't work
        # on Windows. I have no idea about Macs, but I'm not likely to try to
        # run this on a Mac so let's just be conservative about the check. If
        # we're not on Linux, give up now rather than run into cryptic errors
        # later.
        if platform.system() != "Linux":
            raise NotImplementedError("ClientInterfacer only implemented for "
                "Linux.")

        self.__class__._numCreated += 1
        if self.__class__._numCreated > 1:
            raise RuntimeError("Cannot create more than 1 ClientInterfacer.")

        # Disable buffering for sys.stdin.
        #
        # This is necessary because apparently, select on stdin returns False
        # if there is input but it's all buffered by Python. I'd guess Python's
        # select is just a thin wrapper around the real select(), which knows
        # if the pipe has data in it, but not if Python has read that data out
        # of the pipe into its own buffer. So without this line, the script can
        # hang because there's input waiting for it but it doesn't know about
        # that input. (If more input comes in, that can trigger the select and
        # unblock the script, but that can take indefinitely long).
        #
        # To see this happen in practice, try commenting out this line and
        # running print_inv.py.
        #
        # Thanks to:
        #     https://stackoverflow.com/q/33305131
        #     https://stackoverflow.com/a/3670470
        # for the fix.
        #
        # TODO: This doesn't work in py3. Could open it in binary mode instead,
        # but trying '-u' instead for now...
        #   - Update: "rb" doesn't easily work, would have to deal with bin vs.
        #     str issues everywhere else in the code
        # TODO not convinced '-u' works reliably. Further testing is needed. I
        # might have to bite the bullet and implement a worker thread for
        # blocking reads from stdin. Would probably need that on Windows
        # anyway...
        #sys.stdin = os.fdopen(sys.stdin.fileno(), "r", 0)

        # This one is considered part of the public API. If it needs to be
        # calculated, I'll @property it.
        self.playerInfo = PlayerInfo()

        # Mappings from request type ("inv", "on", etc.) to lists of Items.
        #   - _itemLists[type] contains the most recent fully-parsed list of
        #     items from a request of that type. If we have never fully
        #     resolved a request of a given type, then that key is not present
        #     in the mapping.
        #   - _itemListsInProgress[type] contains the list of items parsed so
        #     far from a currently-active request of that type. If a given type
        #     of items has never been requested, or if the most recent request
        #     has been fully resolved, then the key is not present.
        # Note that all 4 combinations of
        #     ((key in _itemLists), (key in _itemListsInProgress))
        # are possible:
        #   - Not in either -- The item type has never been requested
        #   - In _itemListsInProgress only -- The item type has been requested
        #     once, but we're not finished handling the response.
        #   - In _itemLists only -- The item type has been requested once, and
        #     we're finished resolving that request.
        #   - In both -- The item type has been requested more than once, and
        #     we're currently in the middle of resolving the latest request.
        self._itemLists           = {}
        self._itemListsInProgress = {}

        # All of our queues are implemented using collections.deque. New
        # elements are enqueued (pushed) on the right (via append()), and the
        # oldest element is dequeued (popped) from the left (popleft()).

        # Command handling. See this class's doc string for an introduction to
        # the terminology used here. _commandQueue stores the queued commands,
        # _pendingCommands stores the pending commands. "Done" commands aren't
        # stored anywhere, because there's no need to keep track of them.
        #
        # INVARIANT: On entry/exit from all public API calls, there are no
        # queued commands unless we're maxed out on pending commands. That is:
        #     self._hasTargetPendingCommands() or len(self._commandQueue) == 0
        self._commandQueue = collections.deque()
        self._pendingCommands = collections.deque()
        self._targetPendingCommands = targetPendingCommands

        # Queues for particular types of inputs.
        self._pendingScripttells = collections.deque()

        # Catchall queue for inputs that aren't otherwise handled. Note that
        # use of this queue (and the functions that access it) is not
        # forward-compatible; inputs that currently get filed into it may later
        # be moved to their own queues.
        # TODO: Put a max length on this so it doesn't slowly fill up all
        # available memory in long-running scripts.
        #   - Actually, maybe do this for all the queues?
        #   - Actually, can we just get rid of _pendingMiscInputs? I don't know
        #     of any useful reason for it to be tracked...
        self._pendingMiscInputs = collections.deque()

        # Do this preemptively because the whole infrastructure we use to issue
        # commands depends on it.
        # TODO: Consider using "sync" instead of "watch comc"?
        self._sendToClient("watch comc")

        # Also request (and block until we receive) the basic player info. We
        # can't pick up items without knowing the player's tag, and I don't
        # want users to have to worry about this.
        self._sendToClient("request player")
        self._idleUntil(lambda: self.playerInfo.tag is not None)

    ########################################################################
    # Issuing commands to the player

    ### Sending a command ###

    # The following three methods start a new command through the command
    # pipeline and wait (respectively) until it is at least (1) queued, (2)
    # pending, (3) done.
    #
    # Note: for most purposes you can just use issueCommand. That way there
    # will always be targetPendingCommands in flight, and the command queue
    # will never build up a bunch of extra commands.

    def queueCommand(self, command, **kwargs):
        """
        Add a new command to the queue. If we're not already at
        targetPendingCommands, issue commands from the queue until either we
        are at targetPendingCommands or the queue is empty. Return immediately.

        If you are not moving items, count can be omitted. If you are moving
        items, then count must be specified: 0 to move all matching items, or
        else the number of items to move.

        Normally command is just a string, and you can pass the same keyword
        arguments to this function that you would pass when creating a Command.
        But as an alternative, you can pass an actual Command object to this
        function, in which case any keyword arguments will be ignored.
        """

        self._checkInvariants()

        if not isinstance(command, Command):
            command = Command(command, **kwargs)
        self._commandQueue.append(command)
        self._pumpQueue()

        self._checkInvariants()

    def issueCommand(self, command, maxQueueSize=0, **kwargs):
        """
        Same as queueCommand, but block until the command has actually been
        submitted to the server (which may require some commands ahead of it to
        be fully executed).

        If maxQueueSize is specified, instead block until the queue size is at
        most maxQueueSize. Specifying a maxQueueSize > 0 might be useful if
        you're doing a nontrivial calculation between issueCommand()s and you
        want to make sure you're keeping the client busy. For that to work,
        note that you'll need to regularly give the client a chance to actually
        send commands from the queue, by calling pumpEvents().
        """

        self._checkInvariants()

        self.queueCommand(command, **kwargs)
        self.issueQueuedCommands(maxQueueSize=maxQueueSize)

        self._checkInvariants()

    def execCommand(self, command, **kwargs):
        """
        Same as queueCommand, but block until the command has been fully
        executed (that is, until the server has confirmed that it's done).
        """

        self._checkInvariants()

        self.queueCommand(command, **kwargs)
        self.flushCommands()

        self._checkInvariants()

    ### Flushing queued/pending commands ###

    def issueQueuedCommands(self, maxQueueSize=0):
        """
        Block until the command queue has at most maxQueueSize commands in it
        (because all others have been dispatched to the server). Note that
        maxQueueSize is in addition to any pending commands.

        Note that if you intend to handle any inputs of your own, you probably
        want to use idle() instead of this function, since this function will
        allow arbitrarily many unhandled inputs of other types to build up
        while it's waiting for commands to resolve.

        Postcondition: len(self._commandQueue) <= maxQueueSize
        """

        self._checkInvariants()

        self._idleUntil(lambda: len(self._commandQueue) <= maxQueueSize)

        assert len(self._commandQueue) <= maxQueueSize
        self._checkInvariants()

    # TODO: Register this to run at exit / on destruction.
    def flushCommands(self):
        """
        Block until all queued commands have been fully executed.

        As with issueQueuedCommands, if you intend to handle any inputs of your
        own, you probably want to use idle() instead of this function.

        Postcondition:
            len(self._commandQueue) == 0 and \\
                self._boundPendingCommandsHigh() == 0
        """

        self._checkInvariants()

        self._ensureCanWaitOnPendingCommands()
        self._idleUntil(lambda: len(self._commandQueue) == 0 and \
            self._boundPendingCommandsHigh() == 0)

        assert len(self._commandQueue) == 0 and \
            self._boundPendingCommandsHigh() == 0
        self._checkInvariants()

    ### Checking how many commands are in the pipeline ###

    def hasAnyPendingCommands(self):
        """
        Return True if there might still be pending commands.
        """

        self._checkInvariants()
        # Note: I was tempted to call _ensureCanWaitOnPendingCommands here, but
        # I don't think it's necessary. The rule I've decided on is that any
        # function within the ClientInterfacer that waits on a condition that
        # _might_ be affected by _pendingCommands needs to call
        # _ensureCanWaitOnPendingCommands. So if a function within the
        # ClientInterfacer waits based on this function, it's that function's
        # responsibility to call _ensureCanWaitOnPendingCommands, not this
        # function's.
        return self._boundPendingCommandsHigh() > 0

    def hasTargetPendingCommands(self):
        """
        Return True if the number of pending commands is definitely as large as
        the target value, meaning that given the opportunity we would not
        dispatch more commands from the queue.
        """

        self._checkInvariants()
        return self._hasTargetPendingCommands()

    def numQueuedCommands(self):
        """
        Return the number of commands that are queued. Note that this does not
        include pending commands.
        """

        self._checkInvariants()
        return len(self._commandQueue)

    ### Other misc. related to issuing commands ###

    # Allow changing this dynamically because sometimes you want one part of a
    # script to be careful and another part to be fast.
    def setTargetPendingCommands(self, targetPendingCommands):
        """
        Change the number of commands that may be pending on the server before
        we start putting commands in the queue. Increasing this value will
        cause the oldest few commands from the queue to be sent to the server
        immediately. Decreasing this value will _not_ cause the script to block
        waiting for the number of pending commands to shrink.
        """

        self._checkInvariants()

        self._targetPendingCommands = targetPendingCommands
        self._pumpQueue()

        self._checkInvariants()

    def dropAllQueuedCommands(self):
        """
        Immediately clear the command queue, without sending the queued
        commands to the server. Use with caution!
        
        This is mainly provided so it can be called from a panic() function
        which needs to stop everything as quickly as possible and then try to
        recover.
        """

        self._checkInvariants()
        self._commandQueue.clear()
        self._checkInvariants()

    ########################################################################
    # Internal helpers -- issuing commands

    def _idleUntil(self, pred):
        """
        Idle until pred() is satisfied. This is internal-only because in
        practice the pred() has to be based on internal state of the
        ClientInterfacer for this to be useful. (At least I can't think of any
        way that wouldn't be true.) Nevertheless, the invariants must be
        satisfied upon entering this function, for the sake of self.idle();
        this means that pred() can also depend on the invariants to hold.
        """

        self._checkInvariants()
        while not pred():
            self.idle()
            self._checkInvariants()

    def _pumpQueue(self):
        """
        Immediately send to the server the next few commands from the command
        queue, until either the queue is empty or there are (at least)
        targetPendingCommands pending commands.

        This method is called internally by some other methods to restore the
        following invariant:
            self._hasTargetPendingCommands() or len(self._commandQueue) == 0
        """

        lowBound    = self._boundPendingCommandsLow()
        anyGetsComc = any(cmd.getsComc for cmd in self._pendingCommands)
        assert anyGetsComc == (lowBound != 0)

        # Largest number of consecutive commands we'll send that aren't going
        # to be acknowledged by the server. See the large comment in the loop
        # for how this is used.
        maxConsecutiveNonComc = max(self._targetPendingCommands - 1, 1)

        sentAny = False
        while self._commandQueue and lowBound < self._targetPendingCommands:
            nextCommand = self._commandQueue.popleft()

            # This next part is a workaround for an annoying quirk of CrossFire
            # that I discovered the hard way. The short version is that certain
            # special[*] commands don't get a "comc" acknowledgement from the
            # server, which can mess up our timing if we're not careful. This
            # applies to both the "watch comc" and the "sync" methods of
            # timing. For example, if you send 40 "issue move" commands to the
            # server and then an "east", then...
            #   - You won't get a "watch comc" for a while as all the moves
            #     resolve, until finally you get just one "watch comc" when the
            #     "east" resolves.
            #   - If you try to sync then you'll immediately get back "sync 1",
            #     even though the moves have not resolved yet.
            #
            # I work around this by (1) taking into account which pending
            # commands are expected to get a "comc" when resolving "watch comc"
            # messages (see _handleClientInput), and (2) ensuring that we don't
            # send an unbounded number of non-getsComc commands to the server
            # in a row by interspersing no-ops every so often (the code below
            # this comment). For (2), the rule I choose is that we never send
            # as many as self._targetPendingCommands non-getsComc commands in a
            # row -- so if we've already sent (self._targetPendingCommands - 1)
            # non-getsComc commands and the next one would also be
            # non-getsComc, then we first send a no-op for the sake of timing.
            # The one exception is if _targetPendingCommands is 1, in which
            # case we'll allow 1 non-getsComc comand in a row (because we have
            # to) but not 2.
            #
            # (The motivation for this rule is that it means I don't allow us
            # to get into a situation where 0 pending commands and
            # _targetPendingCommands are indistinguishable. I don't have a
            # particularly substantial reason for that choice, it just sounds
            # nice.)
            #
            # [*] For those somewhat knowledgeable about the CrossFire source
            #     itself, I believe the important distinction here is that only
            #     commands which are sent to the server as "ncom" (new command)
            #     get "comc" acknowledgements.
            if not anyGetsComc and not nextCommand.getsComc and \
                    len(self._pendingCommands) >= maxConsecutiveNonComc:
                assert lowBound == 0
                self._sendNoOp()
                anyGetsComc = True
                lowBound    = 1

            # If _targetPendingCommands is 1 and we just sent a noop, then we
            # may already be at _targetPendingCommands. Still send the next
            # command in that case, though, to ensure that we make some
            # progress on the command queue.
            self._sendCommand(nextCommand)
            sentAny = True
            if anyGetsComc:
                lowBound += 1

        # Check our postcondition.
        assert self._hasTargetPendingCommands() or len(self._commandQueue) == 0

        if sentAny:
            # In this case, make sure that we only added the minimum that we
            # needed to. Normally this means that _boundPendingCommandsLow is
            # at most _targetPendingCommands. However, if
            # _targetPendingCommands is 1, then we may have sent a no-op as
            # well as a real command, so the lower bound might be as large as
            # 2.
            assert self._boundPendingCommandsLow() <= \
                max(2, self._targetPendingCommands)

    def _ensureCanWaitOnPendingCommands(self):
        """
        Ensure that it is safe to wait until a pending command resolves. If it
        is not already safe, this is accomplished by sending a no-op command to
        the server. See _canWaitOnPendingCommands for the reason why it might
        not be safe.

        Important: any function within the ClientInterfacer that waits on a
        condition that _might_ be affected by _pendingCommands needs to call
        this function first. Otherwise, we could hang waiting for a "watch
        comc" that will never arrive!
        """

        if not self._canWaitOnPendingCommands():
            self._sendNoOp()

        assert self._canWaitOnPendingCommands()

    def _canWaitOnPendingCommands(self):
        """
        Return True if it is safe to wait until a pending command resolves.
          - If there are no pending commands, then it is safe to wait because
            any attempt to wait will just return immediately.
          - Elif there is at least one pending command that getsComc, then it
            is safe to wait because eventually we'll get a comc for that
            command.
          - Else there is at least one pending command, but no pending command
            getsComc. In this case it is NOT safe to wait, because we may never
            get a comc and therefore the script could hang.
        """

        return len(self._pendingCommands) == 0 or \
            any(cmd.getsComc for cmd in self._pendingCommands)

    def _sendNoOp(self):
        """
        Send a no-op command to the server.
        """

        # Normally "stay" is used for "stay fire", which is definitely not a
        # no-op. But you can also send "stay" as its own command (without the
        # "fire" modifier). The server recognizes it as a directional command,
        # but doesn't actually do anything with it (aside from sending back a
        # comc). See server/c_move.c, function "command_stay".
        self._sendCommand(Command("stay"))

    def _sendCommand(self, command):
        """
        Send the specified command to the server. (Technically we send it to
        the client, and the client re-encodes it and sends it to the server on
        our behalf.)
        """

        self._sendToClient(command.encode())
        self._pendingCommands.append(command)

    def _checkInvariants(self):
        # TODO: Call this more consistently.
        assert self._hasTargetPendingCommands() or len(self._commandQueue) == 0

    def _hasTargetPendingCommands(self):
        """
        Same as hasTargetPendingCommands, but doesn't assert the invariants.
        """

        return self._boundPendingCommandsLow() >= self._targetPendingCommands

    def _boundPendingCommandsLow(self):
        """
        Return a lower bound on the number of pending commands.

        Really this just means the smallest possible number of commands that
        could still be pending as of the last time we
        _handlePendingClientInputs()ed. It's always possible that more commands
        have resolved but we haven't yet seen the "watch comc" for them; we
        don't make any attempt to resolve that race condition.
        """

        # Count how many pending commands at the front of the queue are
        # "uncertain", in the sense that we wouldn't get an acknowledgement for
        # them anyway so we don't know if they've resolved.
        numUncertain = 0
        for x in self._pendingCommands:
            if x.getsComc:
                break
            else:
                numUncertain += 1

        return len(self._pendingCommands) - numUncertain

    def _boundPendingCommandsHigh(self):
        """
        Return an upper bound on the number of pending commands.
        """

        return len(self._pendingCommands)

    def _boundPendingCommandsBoth(self):
        """
        Return a pair (lower, upper) of bounds on the number of pending
        commands.
        """

        return (self._boundPendingCommandsLow(),
                self._boundPendingCommandsHigh())

    ########################################################################
    # Generating specific types of commands.

    # Note that you have to actually pass the returned Commands to queueCommand
    # or one of the similar functions if you want to issue them.

    def getMarkCommand(self, item):
        """
        Generate a command to mark an item.
        """

        return Command("mark %d" % item.tag, isSpecial=True)

    def getApplyCommand(self, item):
        """
        Generate a command to apply an item.
        """

        return Command("apply %d" % item.tag, isSpecial=True)

    def getDropCommand(self, item, count=0):
        """
        Generate a command to drop an item.

        IMPORTANT: The generated command will use the special "move" command,
        which ignores the "locked" status of the item! In an attempt to prevent
        accidentally dropping locked items, this function checks if the
        specified item is marked as "locked", and gives a fatal error if so.
        However, this is based on the Item object in the script, and therefore
        subject to a race condition if the player (or another script) locks the
        item after our last "request items inv" and before this command is
        resolved. So don't call this function on an item unless you have reason
        to believe that it won't be locked.
        """

        return self._getMoveCommand(item, 0, count)

    def getPickupCommand(self, item, count=0):
        """
        Generate a command to pick up an item from the ground.

        See getDropCommand for warning about locked items.
        """

        return self._getMoveCommand(item, self.playerInfo.tag, count)

    def getMoveCommand(self, item, dest, count=0):
        """
        Generate a command to move an item into a container.

        See getDropCommand for warning about locked items.
        """

        return self._getMoveCommand(item, dest.tag, count)

    ### Internal helper ###

    def _getMoveCommand(self, item, destTag, count):
        """
        Common helper for all "move"-based getXCommand functions.
        """

        if item.locked:
            # TODO maybe this should just be a warning and then we refuse to
            # move the item?
            self.fatal("Attempt to move locked item %s <tag=%s>." %
                (item.name, item.tag))
            return None
        commandString = "move %d %d %d" % (destTag, item.tag, count)
        return Command(commandString, isSpecial=True)

    ########################################################################
    # Yielding control to the client interfacer.

    def idle(self, timeout=None):
        """
        Wait until something happens. Do internal handling for any inputs
        received (as with pumpEvents).

        More precisely, wait until we receive some sort of message from the
        client. The message could be of any sort. For example, it might be an
        acknowledgement that one of the pending commands was completed, or it
        might be information on the player stats from a previous "watch stat
        hp", or it might be a "scripttell" message from the player.

        Most scripts will want to call this function somewhere in their main
        loop, to avoid busy-waiting.

        NOTE: By default, this will block indefinitely waiting for input. If
        you don't want that, you can specify a timeout (in seconds).
        """

        self._checkInvariants()
        # We are waiting for "something" to happen. One possible thing that
        # might happen is that the next pendingCommand resolves. This means
        # that this wait is potentially affected by pending commands, so we
        # need to ensure that it's safe to wait on pending commands.
        #
        # Note: the only user-visible functions that can wait on a condition
        # are idle() itself and various functions that call idle() (via
        # _idleUntil). So an _ensureCanWaitOnPendingCommands() here is enough
        # to insulate the user from any concerns about
        # _canWaitOnPendingCommands().
        self._ensureCanWaitOnPendingCommands()
        self._waitForClientInput(timeout=timeout)
        self._handlePendingClientInputs()
        self._checkInvariants()

    def pumpEvents(self):
        """
        Do internal handling for any inputs already received from the client.
        Do not block.

        Some examples of handling done by this function:
          - If we're below targetPendingCommands, then commands are
            automatically issued from the command queue to get up to
            targetPendingCommands (or until the queue is empty).
          - Update playerInfo based on any incoming messages with stat info.
        """

        # CLEANUP: Maybe just inline _handlePendingClientInputs here and then
        # call this one internally? I'm not sure there's much benefit to
        # distinguishing between the two functions.
        self._checkInvariants()
        self._handlePendingClientInputs()
        self._checkInvariants()

    ########################################################################
    # Handling inputs from the client

    # Watch stats. This needs to be enabled explicitly because the messages are
    # pretty spammy.
    def watchStats(self, waitForInitialValues=True):
        """
        Start watching for changes to the player's stats. Also send out
        requests for all of the values that will be tracked, so we can have
        starting values.

        If waitForInitialValues is True (default), then block until responses
        come back for all of those initial requests.

        If waitForInitialValues is False, then return immediately, but some
        stats will be None until all of the requests have come back.
        """

        for requestType in self.playerInfo.getAllRequestTypes():
            self._sendToClient("request " + requestType)
        self._sendToClient("watch stats")

        if waitForInitialValues:
            # TODO: Should we clear the playerInfo in this case? If the user
            # previously called unwatchStats(), then this isn't going to work.
            self._idleUntil(self.playerInfo.haveAllStats)

    def unwatchStats(self):
        """
        Stop watching for changes to the player's stats.
        """

        self._sendToClient("unwatch stats")


    # Querying inventory.

    def getInventory(self):
        """
        Equivalent to self.getItemsOfType("inv")
        """

        return self.getItemsOfType("inv")

    def requestInventory(self):
        """
        Equivalent to self.requestItemsOfType("inv")
        """

        self.requestItemsOfType("inv")

    @property
    def inventory(self):
        """
        Return a reference to the most-recently parsed list of items in the
        player's inventory, or None if we've never completed a request for the
        player's inventory.

        This is almost the same as self.itemsOfType("inv"), except that this
        returns a direct reference to the list, whereas that other call returns
        a copy of the list.
        """

        # This is a @property, which means that (1) it should be very cheap, so
        # we can't do a linear-time copy of a list whose length is more or less
        # unbounded, and (2) users are more likely to expect that modifying it
        # will modify our internal state. So return a direct reference to the
        # "items inv" list.
        #
        # (Now, if only I knew of a way to create a copy-on-write duplicate of
        # the original list and return that instead... or, y'know, if only the
        # language provided a way to mark the return value as "const".)
        return self._itemLists.get("inv", None)

    def hasInventory(self):
        """
        Equivalent to self.hasItemsOfType("inv")
        """

        return self.hasItemsOfType("inv")

    def hasUpdInventory(self):
        """
        Equivalent to self.hasUpdItemsOfType("inv")
        """

        return self.hasUpdItemsOfType("inv")


    # Querying items more generally.

    def getItemsOfType(self, requestType):
        """
        Ask the client for a list of items of the given type if we haven't
        already, block until we get a complete response, and return the parsed
        item list.
        """

        if requestType not in self._itemListsInProgress:
            self.requestItemsOfType(requestType)
        self._idleUntil(lambda: self.hasItemsOfType(requestType))
        return self.itemsOfType(requestType)

    def requestItemsOfType(self, requestType):
        """
        Ask the client for a list of items of the given type, but return
        immediately. You can use self.hasUpdItemsOfType(requestType) to check
        if the request has resolved yet, and self.itemsOfType(requestType) to
        get the list once the request has resolved.
        """

        if requestType in self._itemListsInProgress:
            self.logError("Already in the middle of requesting items %s, " \
                "better not request them again." % requestType)
            return
        self._itemListsInProgress[requestType] = []
        self._sendToClient("request items %s" % requestType)

    def itemsOfType(self, requestType):
        """
        Return the most recently resolved list of items of the given type, or
        None if we've never gotten a complete list of items of the given type.
        """

        # Note: this is very slightly different from
        # self._itemLists.get(requestType, None) because we copy the list if
        # it's present, but we can't do None[:].
        if self.hasItemsOfType(requestType):
            # Make a copy of the item list because this is a real member
            # function, not a @property, so it would be confusing if the user
            # modified the returned list and it messed with our internal state.
            return self._itemLists[requestType][:]
        else:
            return None

    def hasItemsOfType(self, requestType):
        """
        Return True if we have a complete list of items of the given type, even
        if there is currently a newer request outstanding for items of that
        type.
        """

        return requestType in self._itemLists

    def hasUpdItemsOfType(self, requestType):
        """
        Check if the most recent request for items of the given type has fully
        resolved. If we have never requested items of that type, return False.
        """

        return requestType in self._itemLists and \
            requestType not in self._itemListsInProgress


    # scripttells

    def hasScripttell(self):
        return self._hasInputInQueue(self._pendingScripttells)

    def getNextScripttell(self):
        return self._getNextInputFromQueue(self._pendingScripttells)

    def waitForScripttell(self):
        self._waitForInputInQueue(self._pendingScripttells)


    # Misc other inputs that don't have their own handling.
    # NOTE: Use of these next three functions is not forward-compatible! Inputs
    # that are currently categorized as "misc inputs" may in the future be
    # given their own queues. I'm providing these functions for completeness,
    # but you probably shouldn't use them if you want your script to still work
    # in the future.
    # TODO: Provide API calls for things like "watch X", "request X",
    # "monitor", so that these aren't necessary anymore.

    def hasMiscInput(self):
        return self._hasInputInQueue(self._pendingMiscInputs)

    def getNextMiscInput(self):
        return self._getNextInputFromQueue(self._pendingMiscInputs)

    def waitForMiscInput(self):
        self._waitForInputInQueue(self._pendingMiscInputs)

    ########################################################################
    # Internal helpers -- handling client input

    def _hasInputInQueue(self, queue):
        """
        Check if there are any pending inputs that either (1) are already on
        the specified queue, or (2) would go on that queue if we handled any
        arrived-but-unprocessed inputs from the client.
        """

        # If there's something already buffered, then that's an unhandled
        # input. In this case don't check stdin, because that's needlessly
        # slow.
        if len(queue) > 0:
            return True

        # Otherwise, we need to check what's on stdin to determine the answer.
        self._handlePendingClientInputs()
        return len(queue) > 0

    def _getNextInputFromQueue(self, queue):
        """
        Get the next input that would go on the given queue, blocking if
        necessary.
        """

        self._waitForInputInQueue(queue)
        assert len(queue) > 0
        return queue.popleft()

    def _waitForInputInQueue(self, queue):
        """
        Block until there is input on the given queue.
        """

        # Note: queue must be a reference to a queue that actually gets updated
        # when we _handleClientInput; otherwise this will hang.
        self._idleUntil(lambda: len(queue) > 0)

    def _handlePendingClientInputs(self):
        """
        Handle any inputs that have already arrived from the client. Do not
        block.
        """

        while self._checkForClientInput():
            self._handleClientInput(self._readLineFromClient())

    def _handleClientInput(self, msg):
        """
        Handle the given input from the client. Do any necessary internal
        bookkeeping, put it on one or more queues if appropriate, etc.
        """

        # Do "watch comc" first, because it's the most common case in most
        # simple scripts. Also, this way we don't have to hide the code for it
        # in with the other "watch" handling, which is substantially different.
        if msg.startswith("watch comc"):
            if self._pendingCommands:
                # See large comment in _pumpQueue for why this is necessary.
                while self._pendingCommands:
                    cmd = self._pendingCommands.popleft()
                    if cmd.getsComc:
                        break
                self._pumpQueue()
            # if self._pendingCommands is empty, then just swallow the message.
            # This can happen if the player executes some commands while we're
            # listening (perhaps while the script is idle). There's no other
            # use for "watch comc" messages, so still don't store them.
            return

        # Do watch and request next, because they can be fairly high-volume
        # when they do show up.
        isWatch, rest = checkPrefix(msg, "watch ")
        if isWatch:
            self._handleWatch(rest)
            return
        isRequest, rest = checkPrefix(msg, "request ")
        if isRequest:
            self._handleRequest(rest)
            return

        # Scripttells shouldn't come in at a high rate, so leave them until
        # last.
        isScripttell, rest = checkPrefix(msg, "scripttell ")
        if isScripttell:
            self._pendingScripttells.append(rest)
            return

        # If none of the code above handled it, throw it in the "misc inputs"
        # queue.
        self._pendingMiscInputs.append(msg)

    def _handleWatch(self, msg):
        """
        Handle a "watch" input (except "watch comc").

        msg has the initial "watch " stripped off, but is otherwise passed
        through from the client.
        """

        isStats, rest = checkPrefix(msg, "stats ")
        if isStats:
            stat, _, value = rest.partition(" ")

            # Vital stats ("request stat hp")
            if stat == "hp":
                self.playerInfo.hp = int(value)
            elif stat == "maxhp":
                self.playerInfo.maxhp = int(value)
            elif stat == "sp":
                self.playerInfo.sp = int(value)
            elif stat == "maxsp":
                self.playerInfo.maxsp = int(value)
            elif stat == "grace":
                self.playerInfo.grace = int(value)
            elif stat == "maxgrace":
                self.playerInfo.maxgrace = int(value)
            elif stat == "food":
                self.playerInfo.food = int(value)

            # Combat stats ("request stat cmbt")
            elif stat == "wc":
                self.playerInfo.wc = int(value)
            elif stat == "ac":
                self.playerInfo.ac = int(value)
            elif stat == "dam":
                self.playerInfo.dam = int(value)
            elif stat == "speed":
                self.playerInfo.speed = int(value)
            elif stat == "weapon_sp":
                self.playerInfo.weapon_sp = int(value)

            # Ability scores ("request stat stats")
            elif stat == "str":
                self.playerInfo.str = int(value)
            elif stat == "con":
                self.playerInfo.con = int(value)
            elif stat == "dex":
                self.playerInfo.dex = int(value)
            elif stat == "int":
                self.playerInfo.int = int(value)
            elif stat == "wis":
                self.playerInfo.wis = int(value)
            elif stat == "pow":
                self.playerInfo.pow = int(value)
            elif stat == "cha":
                self.playerInfo.cha = int(value)

            # Intentionally no else block; there are known cases that we don't
            # handle.

        # Anything other than stats, just ignore.

    def _handleRequest(self, msg):
        """
        msg has the initial "request " stripped off, but is otherwise passed
        through from the client.
        """

        isStat, rest = checkPrefix(msg, "stat ")
        if isStat:
            self._handleRequestStat(rest)
            return

        isItem, rest = checkPrefix(msg, "items ")
        if isItem:
            self._handleRequestItem(rest)
            return

        isPlayer, rest = checkPrefix(msg, "player ")
        if isPlayer:
            tag, _, title = rest.partition(" ")
            title = chompPrefix(title, "Player:").lstrip()
            self.playerInfo.setPlayerId(tag, title)
            return

        self.logError('Unrecognized request "%s"' % msg)

    def _handleRequestStat(self, msg):
        """
        msg has the initial "request stat " stripped off, but is otherwise
        passed through from the client.
        """

        isVital, rest = checkPrefix(msg, "hp ")
        if isVital:
            parts = rest.split()
            # hp maxhp sp maxsp grace maxgrace food
            if len(parts) != 7:
                self.logError('"request stat hp": got %d items, expected 7.' %
                    len(parts))
                return
            self.playerInfo.setVitalStats(*parts)
            return

        isCombat, rest = checkPrefix(msg, "cmbt ")
        if isCombat:
            parts = rest.split()
            # wc ac dam speed weapon_sp
            if len(parts) != 5:
                self.logError('"request stat cmbt": got %d items, expected 5.'
                    % len(parts))
                return
            self.playerInfo.setCombatStats(*parts)
            return

        isAbil, rest = checkPrefix(msg, "stats ")
        if isAbil:
            parts = rest.split()
            # str con dex int wis pow cha
            if len(parts) != 7:
                self.logError('"request stat stats": got %d items, expected 7.'
                    % len(parts))
                return
            self.playerInfo.setAbilityScores(*parts)
            return

        self.logError('Unrecognized request stat "%s"' % msg)

    def _handleRequestItem(self, msg):
        """
        msg has the initial "request items " stripped off, but is otherwise
        passed through from the client.
        """

        requestType, _, rest = msg.partition(" ")
        if requestType not in self._itemListsInProgress:
            # If we're not expecting an item update of the given type, drop the
            # message. Conceivably we could try to lazily start a list, but I
            # worry it would come out incomplete or with some duplicate items.
            self.logWarning('Received unexpected request items %s "%s"' %
                (requestType, rest))
            return

        if rest == "end":
            self._itemLists[requestType] = \
                self._itemListsInProgress[requestType]
            del self._itemListsInProgress[requestType]
            return

        # Split into <tag> <num> <weight> <flags> <type> <name>
        # That's 6 parts, so 5 splits.
        parts = rest.split(None, 5)
        if len(parts) != 6:
            self.logError('"request items %s": got %d fields, expected 6.' %
                (requestType, len(parts)))
            return
        tag, num, weight, flags, clientType, name = parts
        item = Item(int(tag), int(num), int(weight), int(flags),
                    int(clientType), name)
        self._itemListsInProgress[requestType].append(item)

    ########################################################################
    # Drawing information to the screen

    def draw(self, msg, color=Color.DEFAULT, lowerPanel=False, console=False):
        """
        Draw msg to the screen, in the specified color, for the player to see.

        If lowerPanel is True, ignore color and write to the lower
        (non-critical) message panel in the client.

        If console is True, ignore both color and lowerPanel and write to
        stderr (which goes to the underlying console, assuming there is one).

        Note: any leading spaces will be stripped out by the client.
        """

        if console:
            self.debugOut(msg)
            return

        if lowerPanel:
            # For the client this is just another color code.
            color = 0
        # TODO: It looks like there's a limit of 127 bytes or so of drawn
        # information, excluding the initial "draw <color>". (Probably 128
        # bytes but the last one is a '\0'.) If the message is longer than
        # that, split it up and wrap onto new lines.
        self._sendToClient("draw %s %s" % (color, msg))

    # TODO: Of the next 6 functions, I'm not sure I like the names/behavior of
    # any except fatal. Don't count on the other 5 sticking around unchanged in
    # the public API.
    # TODO: At least pick one set of names here and stick with it.

    def drawWarning(self, msg):
        self.draw("WARNING: " + str(msg), color=Color.ORANGE)

    def drawError(self, msg):
        self.draw("ERROR: " + str(msg), color=Color.RED)

    def logWarning(self, msg):
        self.draw("WARNING: " + str(msg), color=Color.ORANGE)

    def logError(self, msg):
        self.draw("ERROR: " + str(msg), color=Color.RED)

    def fatal(self, msg):
        """
        Print a fatal error message then exit.
        """

        self.draw("FATAL: " + str(msg), color=Color.RED)
        sys.exit()

    # Provide a public API function for outputting to the console so that other
    # modules can do this. Note that this method outputs the string passed in
    # regardless of whether DEBUG is set. (TODO: rename this and make _debug
    # public?)
    def debugOut(self, msg):
        self._sendToConsole(msg)

    ########################################################################
    # Internal helpers -- direct client access

    def _checkForClientInput(self):
        # NOTE! It's assumed in many places that the following sequence:
        #     if self._checkForClientInput():
        #         self._readLineFromClient()
        # will not block. I'm pretty sure this assumption is wrong, at least in
        # theory. If there's data on stdin but not a newline, then I think the
        # readLine will block. This probably won't happen in practice since the
        # client should only be sending us whole lines. But in theory a better
        # implementation would probably be to have our own buffer in which we
        # could store a partial input line. Then _checkForClientInput could
        # first select(), then if stdin is ready to read it could also do
        # (Python's equivalent of) a raw read() on the fd into our buffer. If
        # there's a newline in that string, then throw it into an "unhandled
        # input lines" queue and return True. Else leave it in the buffer and
        # return False.
        #
        # It doesn't seem worth implementing this until/unless it actually
        # becomes a problem.

        # https://docs.python.org/2/library/select.html#select.select
        rlist, _wlist, _xlist = select.select([sys.stdin], [], [], 0)
        return len(rlist) > 0

    def _waitForClientInput(self, timeout=None):
        """
        Wait up to timeout seconds (or indefinitely if timeout is None) for
        input from the client. Return True if there is input ready afte
        waiting.
        """

        if timeout is not None:
            rlist, _wlist, _xlist = select.select([sys.stdin], [], [], timeout)
        else:
            rlist, _wlist, _xlist = select.select([sys.stdin], [], [])
            if not rlist:
                self._logWarning("Waited indefinitely for input but there's "
                    "still no input.")
        return len(rlist) > 0

    def _readLineFromClient(self):
        ret = chompSuffix(sys.stdin.readline())
        self._debug("In:  " + ret)
        return ret

    def _sendToClient(self, msg):
        msg = str(msg)
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()
        self._debug("Out: " + msg)

    # For internal problems with the script, not actually communicating with
    # the player.
    def _logWarning(self, msg):
        self._sendToConsole("Warning: " + str(msg))

    def _debug(self, msg):
        if DEBUG:
            self._sendToConsole(msg)

    def _sendToConsole(self, msg):
        sys.stderr.write(str(msg) + "\n")
        sys.stderr.flush()


# Note: requests are handled at:
#     client/trunk/common/script.c@r20030:1175-1440
# Watches are basically just passed through from the server, but there's some
# special logic for stats at least, at:
#     client/trunk/common/script.c@r20030:674-873
# (in script_watch).
class PlayerInfo:
    def __init__(self):
        # Player identification ("request player")
        self.tag   = None
        self.title = None
        self.havePlayerId = False

        # Vital stats ("request stat hp")
        self.hp       = None
        self.maxhp    = None
        self.sp       = None
        self.maxsp    = None
        self.grace    = None
        self.maxgrace = None
        self.food     = None
        self.haveVitalStats = False

        # Combat stats ("request stat cmbt")
        self.wc        = None
        self.ac        = None
        self.dam       = None
        self.speed     = None
        self.weapon_sp = None
        self.haveCombatStats = False

        # Ability scores ("request stat stats")
        self.str = None
        self.con = None
        self.dex = None
        self.int = None
        self.wis = None
        self.pow = None
        self.cha = None
        self.haveAbilityScores = False

        # Experience and levels ("request stat xp") omitted for now, because
        # I don't want to deal with mapping skill names to their levels (and
        # because I have yet to write a script that needs this).

        # Resistances ("request stat resists") ditto.
        # Spell path atunements etc. ("request stat paths") ditto.

    @property
    def name(self):
        if self.title is None:
            return None
        return self.title.partition(" ")[0]

    def getAllRequestTypes(self):
        return [
            "player",
            "stat hp",
            "stat stats",
            "stat cmbt",
        ]

    def setPlayerId(self, tag, title):
        self.tag   = int(tag)
        self.title = str(title)
        self.havePlayerId = True

    def setVitalStats(self, hp, maxhp, sp, maxsp, grace, maxgrace, food):
        self.hp       = int(hp)
        self.maxhp    = int(maxhp)
        self.sp       = int(sp)
        self.maxsp    = int(maxsp)
        self.grace    = int(grace)
        self.maxgrace = int(maxgrace)
        self.food     = int(food)
        self.haveVitalStats = True

    def setCombatStats(self, wc, ac, dam, speed, weapon_sp):
        self.wc        = int(wc)
        self.ac        = int(ac)
        self.dam       = int(dam)
        self.speed     = int(speed)
        self.weapon_sp = int(weapon_sp)
        self.haveCombatStats = True

    def setAbilityScores(self, str_, con, dex, int_, wis, pow_, cha):
        self.str = int(str_)
        self.con = int(con )
        self.dex = int(dex )
        self.int = int(int_)
        self.wis = int(wis )
        self.pow = int(pow_)
        self.cha = int(cha )
        self.haveAbilityScores = True

    def haveAllStats(self):
        return self.havePlayerId and self.haveVitalStats and \
            self.haveAbilityScores and self.haveCombatStats


# One-off classes used by ClientInterfacer.

class Command:
    # Note: long ago I tried using a DEFAULT_COUNT of 0 and something went
    # wrong, though I don't remember what. So use a DEFAULT_COUNT of 1 and just
    # trust the user to specify the count when moving items.
    DEFAULT_COUNT = 1

    def __init__(self, commandString, count=None, isSpecial=False):
        self.commandString = commandString
        self.count         = count
        self.isSpecial     = isSpecial

    # See the large comment in ClientInterfacer._pumpQueue for an explanation
    # of why this property is necessary.
    @property
    def getsComc(self):
        """
        Will a "comc" acknowledgement be sent for this command?
        """

        return not self.isSpecial

    def encode(self):
        ret = "issue "
        if not self.isSpecial:
            count = self.count
            if count is None:
                count = Command.DEFAULT_COUNT
            ret += "%s 1 " % count
        ret += self.commandString
        return ret


# Actual classes that more or less make sense on their own.

class Item:
    def __init__(self, tag, num, weight, flags, clientType, name):
        self.tag        = tag        # Unique identifier
        self.num        = num        # Size of stack
        self.weight     = weight     # integer number of grams
        self.flags      = flags      # See functions to unpack this
        self.clientType = clientType # Determines sorting order

        # Human-readable name. A couple notes about this:
        #   1. This is the display name, which is subject to any custom
        #      renaming that the player has done.
        #   2. The name includes any human-readable description of the stack
        #      size -- for example, "nine silver coins".
        self.name       = name

    # Unpacking the flags bitmask. This is assembled in script_send_item
    # (common/script.c). The bits are:
    #     0x0200  512     unidentified
    #     0x0100  256     magical
    #     0x0080  128     cursed
    #     0x0040   64     damned
    #     0x0020   32     unpaid
    #     0x0010   16     locked
    #     0x0008    8     applied
    #     0x0004    4     open
    #     0x0002    2     was_open
    #     0x0001    1     inv_updated
    @property
    def unidentified(self): return self._flagBit(0x0200)
    @property
    def magical     (self): return self._flagBit(0x0100)
    @property
    def cursed      (self): return self._flagBit(0x0080)
    @property
    def damned      (self): return self._flagBit(0x0040)
    @property
    def unpaid      (self): return self._flagBit(0x0020)
    @property
    def locked      (self): return self._flagBit(0x0010)
    @property
    def applied     (self): return self._flagBit(0x0008)
    @property
    def open        (self): return self._flagBit(0x0004)
    @property
    def wasOpen     (self): return self._flagBit(0x0002)
    @property
    def invUpdated  (self): return self._flagBit(0x0001)

    # Properties for setting the flag bits. Useful if you're updating Item
    # objects as you move the actual items around, to avoid having to re-query
    # for the whole list.
    @unidentified.setter
    def unidentified(self, val): return self._setFlagBit(0x0200, val)
    @magical.setter
    def magical     (self, val): return self._setFlagBit(0x0100, val)
    @cursed.setter
    def cursed      (self, val): return self._setFlagBit(0x0080, val)
    @damned.setter
    def damned      (self, val): return self._setFlagBit(0x0040, val)
    @unpaid.setter
    def unpaid      (self, val): return self._setFlagBit(0x0020, val)
    @locked.setter
    def locked      (self, val): return self._setFlagBit(0x0010, val)
    @applied.setter
    def applied     (self, val): return self._setFlagBit(0x0008, val)
    @open.setter
    def open        (self, val): return self._setFlagBit(0x0004, val)
    @wasOpen.setter
    def wasOpen     (self, val): return self._setFlagBit(0x0002, val)
    @invUpdated.setter
    def invUpdated  (self, val): return self._setFlagBit(0x0001, val)

    def _flagBit(self, bit):
        return (self.flags & bit) != 0

    def _setFlagBit(self, flag, val):
        if val:
            self.flags |= flag
        else:
            self.flags = self.flags & ~flag


def checkPrefix(s, prefix):
    """
    Return a pair (hasPrefix, rest).
    If prefix is a prefix of s:
        hasPrefix is True
        rest is everything after the prefix
    Else:
        hasPrefix is False
        rest is s
    """

    if s.startswith(prefix):
        return (True, s[len(prefix):])
    else:
        return (False, s)

def chompSuffix(s, suffix="\n"):
    if s.endswith(suffix):
        return s[:-len(suffix)]
    else:
        return s

def chompPrefix(s, prefix):
    if s.startswith(prefix):
        return s[len(prefix):]
    else:
        return s

