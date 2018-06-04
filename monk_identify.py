import client_interfacer

cf = client_interfacer.ClientInterfacer()

# Maintain a few commands in the queue at all times, so the client is always
# busy.
QUEUE_DEPTH = 10

done = False
while not done:
    if cf.numQueuedCommands() < QUEUE_DEPTH:
        cf.queueCommand("invoke identify")
        for i in range(30):
            cf.queueCommand("use_skill meditation")
    cf.idle()
    # TODO: hasInput/getNextInput are deprecated.
    while cf.hasInput():
        if cf.getNextInput().startswith("scripttell"):
            done = True
            cf.draw("Closing down; just need to wait for pending commands.")

# If we have a couple dozen meditations queued, cancel them.
cf.dropAllQueuedCommands()

cf.flushCommands()
cf.draw("Okay, all done.")

