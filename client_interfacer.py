# TODO
#
# Okay, lemme rethink the public API here.
# Things that scripts will need to do:
#   - Draw text
#   - Send a command...
#       - ...and return immediately.
#       - ...and wait until it's dispatched (for pacing).
#       - ...and wait until it's finished.
#   - Query state of commands:
#       - Are there any queued?
#       - Are there any pending?
#       - Are we at maxPendingCommands?
#   - Wait for previous commands:
#       - Wait until queue is empty
#       - Wait until all are done (flush)
#       - Not sure about these:
#           - Wait until at least one more is dispatched
#           - Wait until at least one more is completed
#   - Other waiting:
#       - Wait for <some particular type of input>
#       - Wait until anything happens (idle)
#
# Also, should probably establish a convention for who pulls from the queue.
# When is it allowed that:
#     numPendingCommands < maxPendingCommands and len(commandQueue) == 0
# ? Can we just say this is never true outside of a call to a method?



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
        self.commandQueue = collections.deque()
        self.numPendingCommands = 0
        self.maxPendingCommands = maxPendingCommands

        self.pendingInputs = collections.deque()

    ########################################################################
    # Command execution

    # Allow changing this dynamically because sometimes you want one part of a
    # script to be careful and another part to be fast.
    def setMaxPendingCommands(self, maxPendingCommands):
        self.maxPendingCommands = maxPendingCommands

    # The following three methods start a new command through the command
    # pipeline and wait (respectively) until it is at least (1) queued, (2)
    # pending, (3) done.
    #
    # Note: for most purposes you can just use issueCommand. That way there
    # will always be maxPendingCommands in flight, and the command queue will
    # never build up a bunch of extra commands.

    def queueCommand(self, command, count=DEFAULT_COUNT):
        """
        Issue a command, or add it to the queue if we're already at
        maxPendingCommands. Return immediately.

        If you are not moving items, count can be omitted. If you are moving
        items, then count must be specified: 0 to move all matching items, or
        else the number of items to move.
        """

        self.issueCommandsFromQueue()

        encoded = self._encodeCommand(command, count)
        if self.numPendingCommands >= self.maxPendingCommands:
            self.commandQueue.append(encoded)
        else:
            # We just called issueCommandsFromQueue, which means one of:
            #     len(self.commandQueue) == 0
            #     self.numPendingCommands >= self.maxPendingCommands
            # must be true. Since we just ruled out the first one, the queue
            # must be empty, so it's safe to bypass the queue and just send the
            # command directly.
            self._sendCommand(encoded)

    def issueCommand(self, command, count=DEFAULT_COUNT):
        """
        Same as queueCommand, but block until the command has actually been
        submitted to the server (which may require some commands ahead of it to
        be fully executed).
        """

        # Empty the queue, then wait until we're below maxPendingCommands.
        self.issueAllQueuedCommands()
        # Note: this is "while" instead of "if" in case the user recently
        # called setMaxPendingCommands to decrease maxPendingCommands.
        while self.numPendingCommands >= self.maxPendingCommands:
            self._waitUntilNextCommandFinishes()

        # The queue is empty and numPendingCommands < maxPendingCommands.
        assert not self.commandQueue
        assert self.numPendingCommands < self.maxPendingCommands
        # Therefore, it is safe to bypass the queue and send this command to
        # the client directly.
        self._sendCommand(self._encodeCommand(command, count))

    def execCommand(self, command, count=DEFAULT_COUNT):
        """
        Same as issueCommand, but block until the command has been fully
        executed (that is, until the server has confirmed that it's done).
        """

        self.queueCommand(command, count=count)
        self.execAllPendingCommands()

    def flushCommands(self):
        """
        Equivalent to self.execAllPendingCommands().
        """

        self.execAllPendingCommands()

    def execAllPendingCommands(self):
        """
        Block until all queued commands have been fully executed.

        Postcondition:
            len(self.commandQueue) == 0 and self.numPendingCommands == 0
        """

        # First wait until everything in the queue has been dispatched, then
        # wait until everything dispatched has been completed.
        self.issueAllQueuedCommands()
        while self.numPendingCommands > 0:
            self._waitUntilNextCommandFinishes()

        assert len(self.commandQueue) == 0 and self.numPendingCommands == 0

    def issueAllQueuedCommands(self):
        """
        Block until all commands in the command queue (if any) have been
        dispatched to the server.

        Postcondition: len(self.commandQueue) == 0
        """

        while self.commandQueue:
            self.issueCommandsFromQueue()
            if self.commandQueue:
                self._waitUntilNextCommandFinishes()

        assert len(self.commandQueue) == 0

    def issueCommandsFromQueue(self):
        """
        Immediately send to the server the next few commands from the command
        queue, until either the queue is empty or there are maxPendingCommands
        pending commands.

        Postcondition:
            len(self.commandQueue) == 0 or \\
                self.numPendingCommands >= self.maxPendingCommands
        """

        while self.commandQueue and \
                self.numPendingCommands < self.maxPendingCommands:
            self._sendCommand(self.commandQueue.popleft())

        assert len(self.commandQueue) == 0 or \
            self.numPendingCommands >= self.maxPendingCommands

    def dropAllQueuedCommands(self):
        """
        Immediately clear the command queue, without sending the queued
        commands to the server. Use with caution!
        
        This is mainly provided so it can be called from a panic() function
        which needs to stop everything as quickly as possible and then try to
        recover.
        """

        self.commandQueue.clear()

    def _waitUntilNextCommandFinishes(self):
        """
        Block until at least one pending command is finished executing. If
        there are no pending commands, return immediately, regardless of what's
        in the command queue.
        """
        
        if self.numPendingCommands <= 0:
            return

        oldNumPendingCommands = self.numPendingCommands
        while self.numPendingCommands >= oldNumPendingCommands:
            self.handlePendingClientInputs()
            if self.numPendingCommands >= oldNumPendingCommands:
                self._waitForClientInput()

    def _sendCommand(self, encodedCommand):
        self._sendToClient(encodedCommand)
        self.numPendingCommands += 1

    def _encodeCommand(self, command, count):
        return "issue %s 1 %s" % (count, command)

    ########################################################################
    # Handling inputs

    def hasInput(self):
        """
        Return true if there is unhandled input from the client.
        """

        # If there's something already buffered, then that's an unhandled
        # input. In this case don't check stdin, because that's needlessly
        # slow.
        if len(self.pendingInputs) > 0:
            return True

        # Otherwise, we need to check what's on stdin to determine the answer.
        self.handlePendingClientInputs()
        return len(self.pendingInputs) > 0

    def getNextInput(self):
        if self.pendingInputs:
            # Already have something.
            return self.pendingInputs.popleft()

        # Else, need to wait for input.
        while not self.pendingInputs:
            self.handlePendingClientInputs()
            if not self.pendingInputs:
                self._waitForClientInput()

        assert len(self.pendingInputs) > 0
        return self.pendingInputs.popleft()

    def handlePendingClientInputs(self):
        while self._checkForClientInput():
            self._handleClientInput(self._readLineFromClient())

    def _handleClientInput(self, msg):
        if msg.startswith("watch comc"):
            if self.numPendingCommands > 0:
                self.numPendingCommands -= 1
            # if self.numPendingCommands == 0, then just swallow the message.
            # This can happen if the player executes some commands while we're
            # trying to drive (perhaps while the script is idle). There's no
            # other use for "watch comc" messages, so still don't store them.
        else:
            self.pendingInputs.append(msg)

    ########################################################################
    # Drawing information to the screen.

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
            self._sendToConsole(msg)
            return

        if lowerPanel:
            # For the client this is just another color code.
            color = 0
        self._sendToClient("draw %s %s" % (color, msg))

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

