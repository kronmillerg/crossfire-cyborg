"""
Test script, just to showcase/smoketest some of the simpler features of
ClientInterfacer.
"""

import client_interfacer

cf = client_interfacer.ClientInterfacer()

MAX_ITERS = 20

count = 0
done = False
while not done:
    cf.issueCommand("north")
    cf.issueCommand("east")
    cf.issueCommand("south")
    cf.issueCommand("west")
    if cf.hasScripttell():
        done = True
        cf.draw("Closing down; just need to wait for pending commands.")
    count += 1
    if count > MAX_ITERS:
        # If there's a bug, try not to totally crash the client by flooding it
        # with too much stuff.
        cf.draw("Count maxed out; stopping.")
        done = True

cf.dropAllQueuedCommands()
cf.flushCommands()
cf.draw("Okay, all done.")

