"""
Copyright (c) 2025 Greg Kronmiller

Reading from stdin without blocking (or with a finite timeout).
"""

import queue
import sys
import threading

# Implement this using a worker thread and a synchronized queue.
#
# Yes, you read that right. In order to read from stdin (a pipe) without
# blocking, I _spawn a second thread_ and bring in a thread-safe data structure
# to communicate with it. This module is about 20 lines of code but a whole lot
# of systemic complexity to solve a problem that _really seems like it should
# be simple_ but somehow (AFAICT) isn't.
#
# The obvious alternative approach is to use select() to check for input on
# stdin. I used to do this instead. Two problems with it:
#
# 1) You can't select() on stdin (maybe on pipes generally?) on Windows.
# Currently the CrossFire client's script-spawning code seems broken on Windows
# anyway, so this isn't a blocker yet, but it would eventually have been the
# thing that stopped these scripts from working on Windows.
#
# 2) I believe select() on stdin only checks if the underlying pipe has data on
# it, not if the stream has data in its buffer. So you can get into situations
# where select() on stdin returns False, but stdin.readline() would return
# immediately. This really did come up in practice; a fairly reliable way to
# test for it was by running test/print_inv.py and observing that the script
# gets stuck without printing the full inventory (or often any inventory).
#
# Some more information here:
#     https://stackoverflow.com/q/33305131
#     https://stackoverflow.com/a/3670470
# In Python 2 I worked around it with:
#     sys.stdin = os.fdopen(sys.stdin.fileno(), "r", 0)
# but in Python 3 you can't disable buffering on a text stream. I could
# probably reopen it "rb" instead, but then reads return bytes rather than str
# so I'd have to have a read wrapper which decodes them. Or supposedly I could
# have run and runtest pass -u to Python, but for some reason that didn't work
# for me.
#
# TODO: Is there a better way to do this with asyncio? But see:
#     https://stackoverflow.com/a/58461085
# Might need to bring in aioconsole (or prompt_toolkit?) to use it on stdin.

class InputHandler:
    def __init__(self):
        self.inputQueue = queue.Queue()
        self.inputThread = threading.Thread(target=self._doInputThread,
                daemon=True)
        self.inputThread.start()

    def _doInputThread(self):
        while True:
            self.inputQueue.put(sys.stdin.readline().rstrip("\n"))

    # Note: intentionally no function like hasInput (returning a bool) for two
    # reasons, neither one completely decisive:
    #   - Code like:
    #         if hasInput():
    #             doSomething(getInput())
    #     makes me nervous about TOCTOU races, though with only one thread
    #     pulling from the queue I think the above form should be safe (just
    #     not the reverse: "if not hasInput(): ...")
    #   - More useful than a wait-free hasInput would be hasInput with a
    #     timeout, but queue.Queue doesn't provide that interface. We'd have to
    #     actually get a line from the queue, and then InputHandler would need
    #     to store it for the next checkForInput().

    def checkForInput(self):
        """
        Return the next line of input. If no input is ready, return None
        (immediately).
        """

        try:
            return self.inputQueue.get(block=False)
        except queue.Empty:
            return None

    def waitForInput(self, timeout=None):
        """
        Wait up to timeout seconds (or indefinitely if not specified) until
        input is ready. Return the next line of input, or None if no input is
        ready.
        """

        try:
            return self.inputQueue.get(block=True, timeout=timeout)
        except queue.Empty:
            assert timeout is not None
            return None

