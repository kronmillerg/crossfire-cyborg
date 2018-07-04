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
loadout. I am _not_ going to try to unpluralize names of arbitrary items.


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
"""

print "draw 3 Not implemented."

