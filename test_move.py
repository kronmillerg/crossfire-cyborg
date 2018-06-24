"""
Repeatedly drop and pick up a selected item, to show that the timing is
reasonable. (Recommend running in DEBUG mode for a better test.)
"""

import sys

from client_interfacer import ClientInterfacer, Command
from recipe import runCommandSequence

cf = ClientInterfacer()

if len(sys.argv) != 2:
    cf.fatal("Usage: %s TAG" % sys.argv[0])

try:
    tag = int(sys.argv[1])
except:
    cf.fatal("%r: invalid tag (must be an integer)." % (sys.argv[1]))

# Search inventory for matching tag.
itemToMove = None
inv = cf.getInventory()
for item in inv:
    if item.tag == tag:
        itemToMove = item
        break
if itemToMove is None:
    cf.fatal("Could not find item in inventory with tag %d." % (tag))

commands = [cf.getDropCommand(itemToMove),
            cf.getPickupCommand(itemToMove)] * 50
runCommandSequence(commands, cf=cf)

