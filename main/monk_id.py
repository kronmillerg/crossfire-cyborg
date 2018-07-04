from lib.recipe import loopCommands, Command

# TODO: Once we can watch stats, change this to meditate until mana is (almost)
# full.
loopCommands(["invoke identify"] + 30*["use_skill meditation"])

