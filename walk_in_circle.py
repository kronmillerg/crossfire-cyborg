"""
Test script, just to showcase/smoketest some of the simpler features of
ClientInterfacer.
"""

import client_interfacer

cf = client_interfacer.ClientInterfacer()

count = 0
done = False
while not done:
    cf.issueCommand("north")
    cf.issueCommand("east")
    cf.issueCommand("south")
    cf.issueCommand("west")
    while cf.hasInput():
        if cf.getNextInput().startswith("scripttell"):
            done = True
            cf._sendToConsole("Closing down; just need to wait for pending "
                "commands.")
    count += 1
    if count > 100:
        # If there's a bug, try not to totally crash the client by flooding it
        # with too much stuff.
        cf._sendToConsole("Count maxed out; stopping.")
        done = True

cf.dropAllQueuedCommands()
cf.execAllPendingCommands()
cf._sendToConsole("Okay, all done.")

