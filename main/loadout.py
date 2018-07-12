"""
Plan:

    python loadout.py save <name> --
        Define a new loadout for the current player with the given name.
        Overwrites an existing one of the same name.

    python loadout.py equip <name> --
        Equip the specified loadout, or print an error if it doesn't exist.

    python loadout.py <name> --
        Shortcut for "equip <name>".


Data is stored in subdir "loadout", with a separate file per player.
(Uniquified by the first word in the name, as gotten by "request player".
Whitespace isn't allowed in names, so that should be fine.)

Structure of each data file is:

{
    loadouts: {
        "default" : {
            "worn" : [
                "ring of War",
                "ring of Strife",
                ...
            ],
            "stashed" : [
                "girdle of Valriel of the Crusade"
            ]
            "unstashed" : [
                "holy symbol of Valriel"
            ]
        },
        "magic" : {
            ...
        }
        ...
    },
    stashable: [
        "girdle of Valriel of the Crusade",
        "holy symbol of Valriel",
        "Valriel's Holy Scepter of daylight (lvl 100)"
    ]
}

"stashed" and "unstashed" could have the same thing; we should warn on both
"save" and "equip" if that happens. (It would only happen on save if you have
two of the item.)


Note: a complication is that unequipped items may stack, in which case they'll
display using their plural name, which might not match the name we have in the
loadout. Unfortunately, scripts don't seem to have access to singular and
plural names of items -- only display names. In fact, I'm not even sure the
client has separate access to singular and plural names. I am _not_ going to
try to unpluralize display names of arbitrary items.


To equip a loadout:
  - Sanity checks. Warn if any of these is not satisfied.
      - No duplicates between "stashed" and "unstashed".
      - Nothing is both "stashed" and "worn".
  - Create lists of items to stash and unstash, subtracting out from both lists
    any items that are listed in both. Also subtract from the stash list
    anything that is to be worn.
  - Request items inv.
  - Find all locked* containers. For each one, open it, check the contents,
    pull out and lock anything that is to be unstashed, then close it. Add
    those to the inventory list.
        * In the sense of "guarded against dropping", not "need a key to open".
  - Go through the inventory list to figure out which ones are currently
    equipped. Two-way subtract with the list of items we want equipped to come
    up with the lists of (1) items to unequip and (2) items to equip.
  - Unequip any items that should be unequipped.
  - Equipping, pass 1: for each item that we want to equip, if there's an item
    in the inventory whose name is an exact match, equip it. Don't equip the
    same item twice. Keep track of which items we still need to equip.
      - Favor locked items, but allow equipping items that aren't locked.
  - Equipping, pass 2: for each item that we still want to equip, check the
    inventory list to see if its name is a substring of the name of any item.
    If so, print a warning and give up on that item. If its name is not a
    substring of the name of any item in the inventory, then try an
    "apply -a <name>".
  - If there are any items to be stashed: arbitrarily pick one of the locked
    containers (or print a warning if there aren't any). Get it open, then for
    each item to be stashed, unlock it and put it in the container. Close the
    container.
  - Request items actv. Check if the resulting list actually matches what we
    wanted to equip. Print errors for any mismatches.


To save a loadout:
  - Request items inv.
  - Make a list of all that are active.
  - Make a list of all that are locked and on the "stashable" list.
  - Find all locked containers. For each one, open it, check the contents, then
    close it. Make a list of all items that are in locked containers and that
    appear on the "stashable" list.
  - TODO: Restore containers to the way they originally were?
  - Sanity check: if there's any stashable item that appears both in a locked
    container and outside of any container

TODO: I think container states are going to be recorded with loadouts; should
we keep track of "active" vs. "open"?
  - I vote that we activate any containers that were active, but we don't open
    any when equipping a loadout. The goal isn't to get the player's inventory
    into an identical state; the goal is to equip those things that were
    equipped last time (or equivalent things).
  - Also, we're only going by name. So if the player has 2 containers of the
    same name, we wouldn't know which one to open anyway.

TODO: Sigh. The plural-name thing is probably an issue for stashed items. If
you're carrying two Holy Rings of Valriel, do we just fail to stash them in
your stealth loadout?
"""

import sys

from lib.client_interfacer import ClientInterfacer
from lib.datafile import readFile
from lib.datafile import writeFile

FILE_SKELETON = {
        "loadouts"  : {},
        "stashable" : [],
    }

def main():
    cf = ClientInterfacer()
    loadoutData = readFile("loadout", getLoadoutFilename(cf),
                           default=FILE_SKELETON)

    args = sys.argv[1:]

    if args[0] == "help":
        cf.draw("Usage: %s <cmd> <arguments>" % sys.argv[0])
        cf.draw("Available commands:")
        cf.draw("- current          show current loadout")
        cf.draw("- list             list available loadouts")
        cf.draw("- show  <name>     show a loadout")
        # cf.draw("- set-stashable    edit stashable items")
        cf.draw("- save  <name>     save current loadout")
        # cf.draw("- equip <name>     equip specified loadout") # TODO
    elif len(args) == 1 and args[0] == "list":
        cf.draw("Available loadouts:")
        for name in sorted(loadoutData["loadouts"].keys()):
            cf.draw("- %s" % name)
    elif len(args) == 1 and args[0] == "current":
        currentLoadout = getCurrentLoadout(cf, loadoutData["stashable"])
        cf.draw("Your current loadout is:")
        showLoadout(cf, currentLoadout)
    elif len(args) == 2 and args[0] == "show":
        name = args[1]
        if name in loadoutData["loadouts"]:
            loadout = loadoutData["loadouts"][name]
            cf.draw("Loadout %r consists of wearing:" % name)
            showLoadout(cf, loadout)
        else:
            cf.drawError("No such loadout %r" % name)
    elif len(args) == 1 and args[0] == "set-stashable":
        cf.fatal("Not implemented.") # TODO: Interactively edit stashable list
    elif len(args) == 2 and args[0] == "save":
        saveLoadout(cf, args[1], loadoutData)
    elif len(args) == 2 and args[0] == "equip":
        cf.fatal("Not implemented.") # TODO: Equip a loadout
    elif len(args) == 1:
        # Assume "equip".
        cf.fatal("Not implemented.") # TODO: Equip a loadout
    else:
        cf.fatal("Unable to parse command line. Try 'help'.")

def showLoadout(cf, loadout):
    for itemName in loadout["worn"]:
        cf.draw("- %s" % itemName)
    if loadout["stashed"]:
        cf.draw("The following items are stashed:")
        for itemName in loadout["stashed"]:
            cf.draw("- %s" % itemName)
    if loadout["unstashed"]:
        cf.draw("The following items are NOT stashed:")
        for itemName in loadout["unstashed"]:
            cf.draw("- %s" % itemName)

def saveLoadout(cf, name, loadoutData):
    newLoadout = getCurrentLoadout(cf, loadoutData["stashable"])
    cf.debugOut(repr(newLoadout))
    loadoutData["loadouts"][name] = newLoadout
    writeFile("loadout", getLoadoutFilename(cf), loadoutData)

def getCurrentLoadout(cf, stashable):
    inv = cf.getInventory()

    # Get lists of some types of items that we're interested in.
    # Note: for activeItems, we could "get items actv". But we need go through
    # the whole inventory anyway, so we might as well save an extra client
    # request and compute that one ourselves.
    activeItems = []
    unstashedItems = []
    lockedContainers = []
    openContainer = None
    for item in inv:
        if item.applied:
            activeItems.append(item)
        if item.locked and item.name in stashable:
            unstashedItems.append(item)
        if item.locked and isAContainer(item):
            lockedContainers.append(item)
        if item.open:
            assert openContainer is None
            openContainer = item

    # Now check the contents of every locked container, to determine which
    # items are stashed. This part is more complicated than you would hope,
    # because the logic for how containers cycle through "(active)" and
    # "(active) (open)" is somewhat complicated. This means that it's not
    # trivial to figure out what state a given container is in after we've
    # applied some containers, so it's not trivial to figure out how many times
    # we need to apply that container to get it open. A simpler solution would
    # be to just sync and do another "request items inv" after every time we
    # apply a container, but if there are a lot of items in the inventory then
    # that gets pretty inefficient. I decided to go with the more complicated
    # solution, but if there are bugs, then we can rethink it. Note that the
    # worst case for a bug is that we miss some containers and therefore don't
    # mark some stashed items in the loadout.
    #
    # The logic when applying a container seems to be:
    #   - If the container was not active:
    #       - Activate it
    #   - Elif the container was active:
    #       - Open it
    #       - If another container was already open:
    #            - Change that other container to closed and inactive
    #   - Elif the container was open:
    #       - Close it
    #       - Deactivate it
    stashedItems = []

    # To save us from reasoning about one container closing when we open
    # another one, start by getting the already-open container down to merely
    # active.
    if openContainer is not None:
        assert openContainer.applied
        # Active and open
        cf.issueCommand(cf.getApplyCommand(openContainer))
        # Inactive and closed
        cf.issueCommand(cf.getApplyCommand(openContainer))
        # Active but closed
        openContainer.open = False

    # Open each locked container and check its contents. One of these may be
    # the open container, but we reset each one to the state it was in at the
    # start of this loop, so this doesn't affect the below logic to reopen that
    # container at the end.
    for container in lockedContainers:
        applyCommand = cf.getApplyCommand(container)
        if container.applied:
            appliesToOpen  = 1
            appliesToReset = 2
        else:
            appliesToOpen  = 2
            appliesToReset = 1

        # Open the container.
        for i in range(appliesToOpen):
            cf.issueCommand(applyCommand)
        cf.flushCommands()

        # Get a list of items in it that are stashable.
        contents = cf.getItemsOfType("cont")
        for item in contents:
            if item.name in stashable:
                stashedItems.append(item)

        # Return the container to its original state.
        for i in range(appliesToReset):
            cf.issueCommand(applyCommand)

    # Now reopen the container that was originally open, to get things back to
    # the way they originally were.
    if openContainer is not None:
        # We made a point of leaving the openContainer as active but closed at
        # the start, so it takes one more apply to reopen it.
        cf.issueCommand(cf.getApplyCommand(openContainer))

    # The wornNames allow repeats, because the player could be wearing two of
    # the same ring. The others do not. If an item is all stashed or all
    # unstashed, then it doesn't matter how _many_ of them were
    # stashed/unstashed; when equipping the loadout, we're going to
    # stash/unstash them all. If some of an item are stashed and others are
    # unstashed, then I don't know what to do anyway, so it still doesn't
    # matter how many are in each category.
    wornNames      = sorted([item.name for item in activeItems])
    stashedNames   = set(   [item.name for item in stashedItems])
    unstashedNames = set(   [item.name for item in unstashedItems])

    for name in stashedNames.intersection(unstashedNames):
        cf.logWarning("Item %r is both stashed and unstashed." % name)

    return {
            "worn"      : wornNames,
            "stashed"   : sorted(stashedNames),
            "unstashed" : sorted(unstashedNames),
        }

def getLoadoutFilename(cf):
    assert cf.playerInfo.name is not None
    return str(cf.playerInfo.name).lower() + ".json"

# TODO: Create a lib/ file for known clientTypes.
def isAContainer(item):
    return item.clientType == 51

if __name__ == "__main__":
    main()

