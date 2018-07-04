from lib.recipe import loopCommands, Command

# Yes, this is basically the same as thaumaturgy.py.
loopCommands([
    "east",
    "east",
    Command("take", count=1),
    "west",
    "west",
    "use_skill alchemy",
    # Note: this works, but seems to grant only a trivial amount of
    # experience
    # "use_skill woodsman",
    Command("drop uranium hexafluoride gas", count=0),
])

