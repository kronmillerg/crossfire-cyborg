import client_interfacer

cf = client_interfacer.ClientInterfacer()

done = False
while not done:
    cf.queueCommand("invoke identify")
    for i in range(30):
        cf.queueCommand("use_skill meditation")
    # TODO: If we get a scripttell during the meditation, we should abort
    # immediately rather than finishing all the meditation. I guess the API
    # doesn't really provide a good way to do this yet... maybe we should have
    # something like waitUntilAllCommandsIssuedOrThereIsInput? Or just
    # hasAnyQueuedCommands and then callers can write their own loops.
    cf.issueAllQueuedCommands()
    while cf.hasInput():
        if cf.getNextInput().startswith("scripttell"):
            done = True
            cf._sendToConsole("Closing down; just need to wait for pending "
                "commands.")

# This doesn't do anything yet, but eventually it'll make the close-down a
# little faster.
cf.dropAllQueuedCommands()

cf.execAllPendingCommands()
cf._sendToConsole("Okay, all done.")

