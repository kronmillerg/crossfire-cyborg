from lib.recipe import loopCommands, Command

# TODO: Detect when we're out of icecubes and stop the script.
NUM_MELTS = 4
loopCommands(["mark icecube"] + NUM_MELTS*["apply flint and steel"])

