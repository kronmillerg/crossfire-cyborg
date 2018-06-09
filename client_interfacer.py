import collections
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
    # Note: long ago I tried using a DEFAULT_COUNT of 0 and something went
    # wrong, though I don't remember what. So use a DEFAULT_COUNT of 1 and just
    # trust the user to specify the count when moving items.
    DEFAULT_COUNT = 1

    def __init__(self, maxPendingCommands=6):
        super(ClientInterfacer, self).__init__()

        # We use select() for non-blocking reads from stdin, which won't work
        # on Windows. I have no idea about Macs, but I'm not likely to try to
        # run this on a Mac so let's just be conservative about the check. If
        # we're not on Linux, give up now rather than run into cryptic errors
        # later.
        if platform.system() != "Linux":
            raise NotImplementedError("ClientInterfacer only implemented for "
                "Linux.")

        # Do this preemptively because the whole infrastructure we use to issue
        # commands depends on it.
        # TODO: Look into using "sync" instead of "watch comc"?
        self._sendToClient("watch comc")

        # All of our queues are implemented using collections.deque. New
        # elements are enqueued (pushed) on the right (via append()), and the
        # oldest element is dequeued (popped) from the left (popleft()).

        # Command handling. When a command is issued, it goes through (up to) 3
        # states: queued, pending, done. Let's say that we've already sent a
        # few commands to the server, but they haven't been executed yet. Then
        # (1) a new command will first be put into the commandQueue ("queued"),
        # stored until later to avoid inundating the server and risking
        # commands being dropped. At some point we'll hear back from the server
        # that some of the previous commands were completed, at which point (2)
        # we pop the new command off of the queue and actually send it to the
        # server. After this, it takes some time for the command to reach the
        # server and for the server to resolve it and tell the client, during
        # which time the command is "pending". Once the client hears back from
        # the server that the command has been resolved, it is "done".
        #
        # In practice, we don't keep track of _which_ commands are pending,
        # because there's no point. We just keep a count of how many commands
        # are pending so that we can do things like "send more commands up to
        # maxPendingCommands" or "wait until all pending commands are done".
        #
        # INVARIANT: On entry/exit from all public API calls, there are no
        # queuedCommands unless we're maxed out on pending commands. That is:
        #     self.numPendingCommands >= self.maxPendingCommands or \
        #         len(self.commandQueue) == 0
        self.commandQueue = collections.deque()
        self.numPendingCommands = 0
        self.maxPendingCommands = maxPendingCommands

        # Queues for particular types of inputs.
        self.pendingScripttells = collections.deque()

        # Catchall queue for inputs that aren't otherwise handled. Note that
        # use of this queue (and the functions that access it) is not
        # forward-compatible; inputs that currently get filed into it may later
        # be moved to their own queues.
        self.pendingMiscInputs = collections.deque()

    ########################################################################
    # Issuing commands to the player

    ### Execute a command ###

    # The following three methods start a new command through the command
    # pipeline and wait (respectively) until it is at least (1) queued, (2)
    # pending, (3) done.
    #
    # Note: for most purposes you can just use issueCommand. That way there
    # will always be maxPendingCommands in flight, and the command queue will
    # never build up a bunch of extra commands.

    def queueCommand(self, command, count=DEFAULT_COUNT):
        """
        Add a new command to the queue. If we're not already at
        maxPendingCommands, issue commands from the queue until either we are
        at maxPendingCommands or the queue is empty. Return immediately.

        If you are not moving items, count can be omitted. If you are moving
        items, then count must be specified: 0 to move all matching items, or
        else the number of items to move.
        """

        self._checkInvariants()

        self.commandQueue.append(self._encodeCommand(command, count))
        self._pumpQueue()

        self._checkInvariants()

    def issueCommand(self, command, count=DEFAULT_COUNT, maxQueueSize=0):
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

        self.queueCommand(command, count=count)
        self.issueQueuedCommands(maxQueueSize=maxQueueSize)

        self._checkInvariants()

    def execCommand(self, command, count=DEFAULT_COUNT):
        """
        Same as queueCommand, but block until the command has been fully
        executed (that is, until the server has confirmed that it's done).
        """

        self._checkInvariants()

        self.queueCommand(command, count=count)
        self.flushCommands()

        self._checkInvariants()

    ### Flush queued/pending commands ###

    def issueQueuedCommands(self, maxQueueSize=0):
        """
        Block until the command queue has at most maxQueueSize commands in it
        (because all others have been dispatched to the server). Note that
        maxQueueSize is in addition to any pending commands.

        Note that if you intend to handle any inputs of your own, you probably
        want to use idle() instead of this function, since this function will
        allow arbitrarily many unhandled inputs of other types to build up
        while it's waiting for commands to resolve.

        Postcondition: len(self.commandQueue) <= maxQueueSize
        """

        self._checkInvariants()

        self._idleUntil(lambda: len(self.commandQueue) <= maxQueueSize)

        assert len(self.commandQueue) <= maxQueueSize
        self._checkInvariants()

    def flushCommands(self):
        """
        Block until all queued commands have been fully executed.

        As with issueQueuedCommands, if you intend to handle any inputs of your
        own, you probably want to use idle() instead of this function.

        Postcondition:
            len(self.commandQueue) == 0 and self.numPendingCommands == 0
        """

        self._checkInvariants()

        self._idleUntil(lambda: len(self.commandQueue) == 0 and \
            self.numPendingCommands == 0)

        assert len(self.commandQueue) == 0 and self.numPendingCommands == 0
        self._checkInvariants()

    ### Check how many commands are in the pipeline ###

    def hasAnyPendingCommands(self):
        self._checkInvariants()
        return self.numPendingCommands > 0

    def hasMaxPendingCommands(self):
        self._checkInvariants()
        return self.numPendingCommands >= self.maxPendingCommands

    def numQueuedCommands(self):
        self._checkInvariants()
        return len(self.commandQueue)

    ### Other misc. related to issuing commands ###

    # Allow changing this dynamically because sometimes you want one part of a
    # script to be careful and another part to be fast.
    def setMaxPendingCommands(self, maxPendingCommands):
        """
        Change the number of commands that may be pending on the server before
        we start putting commands in the queue. Increasing this value will
        cause the oldest few commands from the queue to be sent to the server
        immediately.
        """

        self._checkInvariants()

        self.maxPendingCommands = maxPendingCommands
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
        self.commandQueue.clear()
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
        queue, until either the queue is empty or there are maxPendingCommands
        pending commands.

        This method is called internally by some other methods to restore the
        following invariant:
            self.numPendingCommands >= self.maxPendingCommands or \
                len(self.commandQueue) == 0
        """

        while self.commandQueue and \
                self.numPendingCommands < self.maxPendingCommands:
            self._sendCommand(self.commandQueue.popleft())

        assert self.numPendingCommands >= self.maxPendingCommands or \
            len(self.commandQueue) == 0

    def _sendCommand(self, encodedCommand):
        self._sendToClient(encodedCommand)
        self.numPendingCommands += 1

    def _encodeCommand(self, command, count):
        return "issue %s 1 %s" % (count, command)

    def _checkInvariants(self):
        assert self.numPendingCommands >= self.maxPendingCommands or \
            len(self.commandQueue) == 0

    ########################################################################
    # Yielding control to the client interfacer.

    def idle(self):
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
        """

        self._checkInvariants()
        self._waitForClientInput()
        self._handlePendingClientInputs()
        self._checkInvariants()

    def pumpEvents(self):
        """
        Do internal handling for any inputs received from the client. Do not
        block.

        Some examples of handling done by this function:
          - If we're below maxPendingCommands, then commands are automatically
            issued from the command queue to get up to maxPendingCommands (or
            until the queue is empty).
          - Misc internal bookkeeping that would otherwise be handled lazily.
            You don't need to call this function for this purpose.
        """
        # TODO: Also updating based on 'watch stat hp' and similar.

        # CLEANUP: Maybe just inline _handlePendingClientInputs here and then
        # call this one internally? I'm not sure there's much benefit to
        # distinguishing between the two functions.
        self._checkInvariants()
        self._handlePendingClientInputs()
        self._checkInvariants()

    ########################################################################
    # Handling inputs from the client

    # scripttells
    def hasScripttell(self):
        return self._hasInputInQueue(self.pendingScripttells)

    def getNextScripttell(self):
        return self._getNextInputFromQueue(self.pendingScripttells)

    def waitForScripttell(self):
        self._waitForInputInQueue(self.pendingScripttells)

    # Misc other inputs that don't have their own handling.
    # NOTE: Use of these next three functions is not forward-compatible! Inputs
    # that are currently categorized as "misc inputs" may in the future be
    # given their own queues. I'm providing these functions for completeness,
    # but you probably shouldn't use them if you want your script to still work
    # tomorrow.

    def hasMiscInput(self):
        return self._hasInputInQueue(self.pendingMiscInputs)

    def getNextMiscInput(self):
        return self._getNextInputFromQueue(self.pendingMiscInputs)

    def waitForMiscInput(self):
        self._waitForInputInQueue(self.pendingMiscInputs)

    ########################################################################
    # Internal helpers -- handling client input

    def _hasInputInQueue(self, queue):
        # If there's something already buffered, then that's an unhandled
        # input. In this case don't check stdin, because that's needlessly
        # slow.
        if len(queue) > 0:
            return True

        # Otherwise, we need to check what's on stdin to determine the answer.
        self._handlePendingClientInputs()
        return len(queue) > 0

    def _getNextInputFromQueue(self, queue):
        self._waitForInputInQueue(queue)
        assert len(queue) > 0
        return queue.popleft()

    def _waitForInputInQueue(self, queue):
        # Note: queue must be a reference to a queue that actually gets updated
        # when we _handleClientInput; otherwise this will hang.
        self._idleUntil(lambda: len(queue) > 0)

    def _handlePendingClientInputs(self):
        while self._checkForClientInput():
            self._handleClientInput(self._readLineFromClient())

    def _handleClientInput(self, msg):
        if msg.startswith("watch comc"):
            if self.numPendingCommands > 0:
                self.numPendingCommands -= 1
                self._pumpQueue()
            # if self.numPendingCommands == 0, then just swallow the message.
            # This can happen if the player executes some commands while we're
            # trying to drive (perhaps while the script is idle). There's no
            # other use for "watch comc" messages, so still don't store them.
        elif msg.startswith("scripttell "):
            msg = msg[len(  "scripttell "):]
            self.pendingScripttells.append(msg)
        else:
            self.pendingMiscInputs.append(msg)

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
        self._sendToClient("draw %s %s" % (color, msg))

    def fatal(self, msg):
        """
        Print a fatal error message then exit.
        """

        self.draw(msg, color=Color.RED)
        sys.exit()

    # Provide a public API function for outputting to the console so that other
    # modules can do this. Note that this method outputs the string passed in
    # regardless of whether DEBUG is set.
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


def chompSuffix(s, suffix="\n"):
    if s.endswith(suffix):
        return s[:-len(suffix)]
    else:
        return s

