import client_interfacer

cf = client_interfacer.ClientInterfacer()

# Maintain a few commands in the queue at all times, so the client is always
# busy.
QUEUE_DEPTH = 10

# TODO: Factor out this whole idiom into a function. Make the scripttell
# handling a little more intelligent; provide some actual commands (pause,
# resume, stop now, stop after current iteration).

done = False
while not done:
    if cf.numQueuedCommands() < QUEUE_DEPTH:
        cf.queueCommand("east")
        cf.queueCommand("east")
        cf.queueCommand("take", count=1)
        cf.queueCommand("west")
        cf.queueCommand("west")
        cf.queueCommand("use_skill thaumaturgy")
        cf.queueCommand("drop wand, staff, rod", count=0)
    cf.idle()
    if cf.hasScripttell():
        done = True
        cf.draw("Closing down; just need to wait for pending commands.")

cf.dropAllQueuedCommands()
cf.flushCommands()
cf.draw("Okay, all done.")

