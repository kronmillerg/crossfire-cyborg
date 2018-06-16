"""
Really basic test of the inventory subsystem. Request the player's inventory
once, block until we get a full response, and then print it out.
"""

from client_interfacer import ClientInterfacer, Color

cf = ClientInterfacer()

inv = cf.getInventory()

# Probably already sorted by clientType, but just to be sure, re-sort it
# ourselves.
inv.sort(key=lambda x: x.clientType)

for item in inv:
    name = item.name
    if item.locked:
        name = "* " + name
    if item.magical:
        name += " (magic)"
    if item.damned:
        name += " (damned)"
    elif item.cursed:
        name += " (cursed)"
    if item.unpaid:
        name += " (unpaid)"
    if item.applied:
        name += " (applied)"
    if item.open:
        name += " (open)"
    if item.num != 1:
        name = name + " <stack of %d>" % item.num
    color = Color.NAVY
    if item.applied:
        color = Color.BLACK
    cf.draw(name, color=color)

