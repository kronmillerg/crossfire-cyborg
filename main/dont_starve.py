"""
Dead-simple proof of concept that I can watch the player's stats. Sits idle
until the player's hunger runs below 200, then summons and eats a waybread.
Useful to leave running while afk.
"""

from lib.client_interfacer import ClientInterfacer

cf = ClientInterfacer()
cf.watchStats()

while True:
    if cf.hasScripttell():
        cf.draw("Exiting.")
        break
    if cf.playerInfo.food < 200:
        cf.issueCommand("cast create food waybread")
        cf.issueCommand("stay fire")
        cf.issueCommand("get waybread", count=0)
        # NOTE: This isn't quite right. If the player is carrying some special
        # sort of waybread, then we'll eat it, which is probably not what they
        # want. But it's the best we can do for now, since (as of when this
        # script was written) we don't support examining the player's
        # inventory.
        cf.issueCommand("apply waybread")
        cf.flushCommands()
    cf.idle()

# Shouldn't matter, but good practice.
cf.flushCommands()

