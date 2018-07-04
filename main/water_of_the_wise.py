"""
Create water of the wise by alchemy.
"""

import sys

from lib.client_interfacer import ClientInterfacer, Command
from lib.recipe import runCommandSequence

cf = ClientInterfacer()

# Find the cauldron on the ground.
itemsOn   = cf.getItemsOfType("on")
cauldrons = []
for item in itemsOn:
    if item.name == "cauldron":
        cauldrons.append(item)
if len(cauldrons) != 1:
    cf.logError("Expected 1 cauldron on ground, got %d" % len(cauldrons))
    sys.exit(0)
cauldron = cauldrons[0]

# Find the largest pile of waters in the player's inventory.
waters = None
inv = cf.getInventory()
for item in inv:
    if item.name.endswith(" water") or item.name.endswith(" waters"):
        if waters is None or item.num > waters.num:
            waters = item
if waters is None:
    cf.logError("You don't have any water.")
    sys.exit(0)

# TODO: Generator instead of list.
commands = []

# If it's already open, probably we can skip these. But just in case it makes a
# difference, double-apply the cauldron so that it's the most recently opened
# container.
if cauldron.open:
    commands.append(cf.getApplyCommand(cauldron))
commands.append(cf.getApplyCommand(cauldron))

remaining = waters.num
while remaining >= 7:
    commands.append(cf.getMoveCommand(waters, cauldron, count=7))
    commands.append("use_skill alchemy")
    commands.append(Command("get all", count=0))
    remaining -= 7

commands.append(cf.getApplyCommand(cauldron))

runCommandSequence(commands, cf=cf)

