from lib.recipe import loopCommands, Command

# Yes, this is basically the same as uf6.py.
loopCommands([
    "east",
    "east",
    Command("take", count=1),
    "west",
    "west",
    "use_skill thaumaturgy",
    Command("drop wand, staff, rod", count=0),
])

