"""
Copyright (c) 2025 Greg Kronmiller
"""

import time

from lib.client_interfacer import ClientInterfacer
from lib.geography import Navigator, Suite, parseRoom, Direction

cf = ClientInterfacer()

mainFloor = parseRoom("MainFloor", """
        #  #  #  #  #  #  #  #  #  #  #  #  #  #  #  #
        #  ?  ?  .  .  .  .  .  .  .  .  .  .  #  #  #
        #  .  #  .  .  .  .  .  .  .  .  B  .  #  ?  #
        #  F  #  .  .  .  .  .  .  .  .  .  .  #  D  #
        #  .  #  .  .  .  .  .  .  .  .  .  .  #  .  #
        #  .  .  .  .  .  .  .  .  .  .  .  .  #  .  #
        #  .  .  .  .  .  .  .  .  .  .  .  .  .  .  #
        #  .  .  .  .  .  .  .  .  .  .  .  .  #  .  #
        #  P1 P2 P3 P4 P5 .  .  .  .  .  .  .  #  .  #
        #  #  #  #  #  #  #  #  #  #  #  #  #  #  #  #
    """)

# Final version will probably just have 5 strings, but for now they're
# basically all the same so share a string. This means we can't have any POIs
# in the desc, since they have to be unique within the Suite.
pocketDesc = """
        ?  #  #  #  #  #  #  #  #  #  #  #
        #  .  .  .  .  .  .  .  .  .  .  #
        #  .  .  .  .  .  .  .  .  .  .  #
        #  .  .  .  .  .  .  .  .  .  .  #
        #  .  .  .  .  .  .  .  .  .  .  #
        #  .  .  .  .  .  .  .  .  .  .  #
        #  .  .  .  .  .  .  .  .  .  .  #
        #  .  .  .  .  .  .  .  .  .  .  #
        #  .  .  .  .  .  .  .  .  .  .  #
        #  .  .  .  .  .  .  .  .  .  .  #
        #  .  .  .  .  .  .  .  .  .  .  #
        #  #  #  #  #  #  #  #  #  #  #  #
"""

pocket1 = parseRoom("Pocket1", pocketDesc)
mainFloor["P1"].setNeighbor(Direction.APPLY, pocket1[1, 1])
pocket1[1, 1].setNeighbor(Direction.NORTHWEST, mainFloor["P1"])

pocket2 = parseRoom("Pocket2", pocketDesc)
mainFloor["P2"].setNeighbor(Direction.APPLY, pocket2[1, 1])
pocket2[1, 1].setNeighbor(Direction.NORTHWEST, mainFloor["P2"])

pocket3 = parseRoom("Pocket3", pocketDesc)
mainFloor["P3"].setNeighbor(Direction.APPLY, pocket3[1, 1])
pocket3[1, 1].setNeighbor(Direction.NORTHWEST, mainFloor["P3"])

pocket4 = parseRoom("Pocket4", pocketDesc)
mainFloor["P4"].setNeighbor(Direction.APPLY, pocket4[1, 1])
pocket4[1, 1].setNeighbor(Direction.NORTHWEST, mainFloor["P4"])

pocket5 = parseRoom("Pocket5", pocketDesc)
mainFloor["P5"].setNeighbor(Direction.APPLY, pocket5[1, 1])
pocket5[1, 1].setNeighbor(Direction.NORTHWEST, mainFloor["P5"])

scornApartment = Suite(rooms=[mainFloor, pocket1, pocket2, pocket3, pocket4,
        pocket5])


# Turn off autopickup
cf.issueCommand("pickup 0")

### Do a series of steps to canonicalize our position.

# Ensure we're not on the main floor gate
cf.issueCommand("east")
# Get all the way south in the main floor, ensuring we're not in the entry
# hallway.
for i in range(7):
    cf.issueCommand("south")
# If we're in the portal area to the east of the main floor, exit it. In case
# we were exactly on the gate to that area (and the above souths did nothing),
# do a SW after the NW to ensure we're not north of the bed.
cf.issueCommand("north")
cf.issueCommand("northwest")
cf.issueCommand("southwest")
# Get all the way west (in any room)
for i in range(11):
    cf.issueCommand("west")
# If we were on the main floor, we are now probably just south of the bed, or
# if we started exactly 1 tile west of the gate to the portal area then we're
# now on the bed. If we were in a pocket reality, we are now somewhere on the
# west wall. Move one tile east so we can run north (to get out of a pocket
# reality) without possibly running into the entry hallway on the main floor.
# TODO: could optimize this slightly: northeast then 7 or 8 norths.
#     Note that we can safely do this with "northeast" only because we know
#     we're not north of the bed on the main floor; otherwise we might hit the
#     wall that's (2 north, 1 east) of the bed.
cf.issueCommand("east")
for i in range(9):
    cf.issueCommand("north")
# If we were in a pocket reality, exit it.
cf.issueCommand("west")
cf.issueCommand("northwest")
# Get to the southwest corner of the main floor.
for i in range(3):
    cf.issueCommand("south")
for i in range(4):
    cf.issueCommand("west")


### Now walk to a few specific points to show we can pathfind.

nav = Navigator(cf, scornApartment, startPos=mainFloor["P1"])

def pauseAtPoint(msg):
    cf.flushCommands()
    cf.draw(msg)
    time.sleep(2)

pauseAtPoint("At SW corner of main")
nav.travelTo(pocket5[9, 2])
pauseAtPoint("At pocket5 (9, 2)")
nav.travelTo(mainFloor["B"])
pauseAtPoint("At mainFloor (B)")
nav.travelTo(pocket2[2, 10])
pauseAtPoint("At pocket2 (2, 10)")
nav.travelTo(mainFloor["D"])
pauseAtPoint("At mainFloor (D)")
nav.travelTo(pocket3[5, 5])
pauseAtPoint("At pocket3 (5, 5)")
nav.travelTo(mainFloor["F"])
pauseAtPoint("At mainFloor (F)")

nav.travelTo(mainFloor["P1"])
cf.flushCommands()
cf.draw("Back at SW corner of main")

