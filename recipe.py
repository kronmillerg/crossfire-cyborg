"""
A collection of commonly-used / simple script recipes. No relation to in-game
crafting recipes.

In all cases, the argument called "cf" takes in a ClientInterfacer instance. If
none is specified, then the function will create one automatically. It is not
allowed to create two ClientInterfacers, so only do this if the function you're
calling is the entirety of your script.
"""

from client_interfacer import ClientInterfacer, Command

def loopCommands(commandList, cf=None, queueDepth=10):
    if cf is None:
        cf = ClientInterfacer()
    done = False
    while not done:
        while cf.numQueuedCommands() < queueDepth:
            for cmd in commandList:
                cf.queueCommand(cmd)
        cf.idle()
        if cf.hasScripttell():
            # TODO: Add more sophisticated parsing of scripttell commands.
            done = True
            cf.draw("Closing down once pending commands resolve.")

    cf.dropAllQueuedCommands()
    cf.flushCommands()
    cf.draw("Done.")

