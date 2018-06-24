"""
Identify items using rods of identify.
"""

import re
import sys

from client_interfacer import ClientInterfacer, Command
from recipe import loopCommands

cf = ClientInterfacer()

# To be safe, first unready any rod that may be readied.
cf.execCommand("apply -u rod")

# This regex is used to check which items are rods of identify. The expected
# name is "Rod of Knowledge of identify (lvl 20)", but this should match
# anything that's a rod of identify.
identRodRE = re.compile(r"(heavy )?rod.* of identify \(.*",
                        flags=re.IGNORECASE)

# Now make a list of all the rods of identify in the player's inventory.
identRods = []
inv = cf.getInventory()
for item in inv:
    if identRodRE.match(item.name):
        if item.applied:
            cf.fatal("Item %r already applied." % item.name)
        identRods.append(item)

commands = []
for identRod in identRods:
    commands.append(cf.getApplyCommand(identRod))
    commands.append("stay fire")

# TODO: Add support to ClientInterfacer for keeping track of inputs matching
# arbitrary prefixes. Watch drawinfo. Write our own loop, which (in addition to
# watching for scripttells) watches for a line like:
#     watch drawinfo ___ You can't reach anything unidentified.
# Once we see that, drop queued commands, flush pending commands, then exit.
loopCommands(commands, cf=cf)

