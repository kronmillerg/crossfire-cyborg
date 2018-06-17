"""
A collection of commonly-used / simple script recipes. No relation to in-game
crafting recipes.

In all cases, the argument called "cf" takes in a ClientInterfacer instance. If
none is specified, then the function will create one automatically. It is not
allowed to create two ClientInterfacers, so only do this if the function you're
calling is the entirety of your script.
"""

from client_interfacer import ClientInterfacer, Command

def loopCommands(commandList, **kwargs):
    def generateCommands():
        while True:
            for cmd in commandList:
                yield cmd
    runCommandSequence(generateCommands(), **kwargs)

def runCommandSequence(commands, cf=None, queueDepth=10):
    if cf is None:
        cf = ClientInterfacer()
    if queueDepth < 1:
        queueDepth = 1
    iterator   = iter(commands)
    done       = False
    atEndOfSeq = False
    while not done:
        while not atEndOfSeq and cf.numQueuedCommands() < queueDepth:
            try:
                cf.queueCommand(iterator.next())
            except StopIteration:
                atEndOfSeq = True
                break
        if atEndOfSeq and cf.numQueuedCommands() == 0:
            break
        cf.idle()
        if cf.hasScripttell():
            # TODO: Add more sophisticated parsing of scripttell commands.
            done = True
            cf.dropAllQueuedCommands()
            cf.draw("Closing down once pending commands resolve.")

    cf.flushCommands()
    cf.draw("Done.")

