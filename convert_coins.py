"""
Convert any coins in player's inventory to at least platinum.

Assumes you are standing somewhere in the Bank of Skud in Scorn. Hardcodes
knowledge about the layout of that building. Also, assumes there's no one else
there.
"""

import client_interfacer

cf = client_interfacer.ClientInterfacer()

# Get to the northeast corner, so we don't have to examine the level to get our
# bearings.
for i in range(4):
    cf.issueCommand("north")
for i in range(12):
    cf.issueCommand("east")

# Silver to gold.
cf.issueCommand("west")
cf.issueCommand("west")
cf.issueCommand("drop silver coin", count=0)
cf.issueCommand("get coin", count=0)

# Gold to platinum.
cf.issueCommand("west")
cf.issueCommand("west")
cf.issueCommand("drop gold coin", count=0)
cf.issueCommand("get coin", count=0)

# If stopping at platinum, here's the commands back to the exit.
# cf.issueCommand("southwest")
# cf.issueCommand("southwest")
# cf.issueCommand("southwest")
# cf.issueCommand("south")

# Platinum to jade.
cf.issueCommand("southeast")
cf.issueCommand("south")
cf.issueCommand("drop platinum coin", count=0)
cf.issueCommand("get coin", count=0)

# Jade to amberium.
cf.issueCommand("east")
cf.issueCommand("east")
cf.issueCommand("drop jade coin", count=0)
cf.issueCommand("get coin", count=0)

# Just to be extra fancy, walk back to approximately the exit.
cf.issueCommand("northwest")
cf.issueCommand("west")
cf.issueCommand("west")
cf.issueCommand("west")
cf.issueCommand("southwest")
cf.issueCommand("southwest")
cf.issueCommand("south")

# Wait until all the commands are actually resolved before exiting, just on
# principle.
cf.flushCommands()

