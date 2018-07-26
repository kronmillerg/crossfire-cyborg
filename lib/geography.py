"""
Copyright (c) 2018 Greg Kronmiller

Plan:
  - Room: an arrangement of tiles, some passable (floors) and some impassable
    (walls). Assumed to obey the obvious, simple geometry -- you can walk
    between adjacent tiles (including diagonally) as long as both are passable.
  - Suite: a collection of Rooms, linked by portals.
      - Question: can a Room have a portal to itself?
  - Portals can be doors, staircases, or actual magic portals. As far as we're
    concerned there are only two types: the ones that you apply to travel
    through, and the ones that automatically trigger when you step on them.
  - Actually, "impassable" tiles also have two types: (1) regular walls, which
    you can safely walk at you simply won't move, and (2) special squares that
    we must not step on.
  - Some tiles may be marked as "points of interest", with names.

I am _not_ going to manually code up every map. We need a format for encoding
them that's easy to parse, but not awful to write.

Here's my current idea. It may still change some before it's finalized.

Have a "picture" of each room, with each character representing one tile and
the characters laid out in the same way as the room itself, and then to the
right of that "picture" provide the names of the points of interest.

For suites, probably give each room a name on a line before the room itself,
and then separate different rooms with blank lines.

For portals, we need to encode the destination. Use the same syntax that we use
for naming points of interest. The destination of a portal should say the name
of the room that it moves you to. Er, and the location within that room...
specified as a point of interest? Actually, in that case why name the rooms at
all?
  - Not entirely sure about this
  - Let's assume for now we're naming the rooms anyway; it'll probably be
    useful for debugging
  - Linking to a PoI seems most logical, though I guess there's a question: do
    we allow different rooms to have PoI with the same name? If so we might
    need a syntax for disambiguating, which might involve specifying a room
    name as well?! But then we'd need a delimiter, and now the parsing is a
    pain. (And what if someone wants to use that delimiter in a name?) Much
    simpler to just make PoI names globally unique. If a mapwriter wants to
    have similarly named PoI in different rooms, _they_ can make up a
    delimiter, and do something like "Bedroom:Closet" vs. "Hall:Closet". The
    parser doesn't need to be aware of it.
  - But still name the rooms? Sure, why not. I still maintain it'll be useful
    for debugging, and come to think of it probably also for the sanity of the
    mapwriters.

Oh.

Crap.

But what if the destination of a portal is itself a portal? For example, what
if the staircase-leading-down in the upstairs room takes you to the
staircase-leading-up in the downstairs room?

Well, for the 2-portal case we could maybe get away with just giving them the
same name as a special case, but suppose there's a 3-cycle? We need a way to
specify both a name and a destination. Sigh. I think we're stuck just bringing
in a delimiter.
  - Or we could make both fields mandatory and then just read 2 names for every
    portal, but (1) that's a pain because some of the time you don't need a
    name, and (2) it'll ruin what little hope we still have left of being able
    to visually see which name corresponds to which PoI.

Alright. Let's just try an example:

    Upstairs
    +---+
    |c s| [cauldron] [stove]
    |   |
    |>  | [stairs:top > stairs:bottom]
    +---+

    Downstairs
    +---+
    |   |
    | <l| [stairs:bottom > stairs:top] [lever]
    |   |
    +---+

The words on their own lines are room names. The parts at the end in square
brackets are the PoI names. The rest are the pictures.

I'm thinking the full set of characters available for pictures is:
    -+|#        walls
    . <space>   floors
    a-zA-Z      points of interest (maybe also allow 0-9?)
    ?           don't step on this square (unknown)
    ><          portals that are used by applying them
    ^           portals that activate when you step on them
    !           reserved for endpoints of custom paths that aren't represented
                in the usual way. An example is the kitchen doorway from the
                old LTAP alchemist script. To get between the handles: [apply,
                sleep(2s), nw, nw, apply].

I'm undecided about whether to use ^ for "activate-on-step portal" or "don't
touch this square". It's a reference to Nethack (and probably Rogue before it),
where it meant "trap"; unfortunately that kind of fits both. But visually, it
looks closer to < and >, so it seems better for "portal".

Names are right of the picture; no picture may follow a name. Each set of
square brackets applies to one portal or PoI, in left-to-right order on the
same line.

Space is used for floor, but I'm also going to rstrip() each line of the
picture, so if you want it to end without a wall, you'll need to use a . for
the last floor. I'll probably lstrip as well, though I'll need to maintain
alignment in the process.
  - Actually, conceptually speaking, can we just strip() each line and then
    fill with walls to infinity in both directions?
  - Or, alternatively, can we just give an _error_ if the room isn't bounded by
    walls? If we're going to silently fill walls anyway, this might be better.
  - Basically the problem is that if the user writes something like:

         #######
         #### ##
          #### #
               #
         #     #
        #### ###
        ########

    then I don't know _what_ they think they mean on the left side. There's no
    use for scripting purposes to leave the edge of a room open like that,
    since we can't walk on it anyway. So just force the user to add either
    walls or "don't step here" markers.
  - Er, not just "bounded" but specifically there's a rectangular border like
    that. Because obviously they could also do

         # ### #
        #### ####
         # ### #
        #### ####
         # ### #
        #### ####
         # ### #

    and leave us wondering _which_ squares are supposed to be bounded. (Answer:
    all of them, but a rectangular border is easier to check anyway.

Oh, also, any sort of whitespace _other_ than space that appears inside or left
of the picture is a fatal error. I am NOT dealing with figuring out how the
picture lays out in your editor. This includes all of the following (and some
others if we ever get fancy enough to take more-than-just-ASCII input):
  - (Horizontal) tab
  - Vertical tab
  - Form feed
  - Either of the newline characters (CR, LF), provided that it didn't get
    interpreted as an actual line ending. (Ex: if we read a CRLF file and
    there's a stray LF somewhere.)
(They would all have been rejected inside the picture anyway as not valid, but
the point is that I don't want to just blindly lstrip() them away from the
start of the line.)
  - Note: as a single, solitary exception, it would be reasonable to allow
    stripping N horizontal tabs from the start of every line, as long as _every
    line of the picture starts with exactly N tabs_.  I'm not going to
    implement that at first because I don't really use tabs, but I could be
    convinced to if I ever get another user who likes tabs.

Points of Interest are normally assumed passable; should we have a way to
override that?
  - Wrong question. Should we reserve characters that are logically for PoI to
    mean "also a PoI, but not passable"? For example, reserve capital letters
    or digits?
  - I guess not. Capital letters would be weird. Digits less so, but I don't
    really like it either. Let's just say we'll hide this information in the
    names, much like the name/dest separation for portals.



Basic plan:
  - Read in a desc.
      - Create several rooms, in a mapping by name.
      - Mark each tile with its type.
      - For PoI, just mark the tile as a floor. Build a mapping of PoI names
        to their locations as we go.
      - For portals, add them to the PoI mapping if they have a name.
        Regardless, mark the destination in a Portal object, which is stored as
        the tile itself.
  - Do a second pass to link portals.
      - For each one, look up its destination in the PoI mapping.
      - If we can't find it, error.
          - Maybe allow "" for a portal that goes outside the Suite? But then
            why not just mark it as either "floor" or "don't touch"?
  - Allow the programmer to manually add paths between the custom endpoints.
  - If any custom endpoints _don't_ have paths to or from them by this point,
    error.
  - Suite is ready! Can now use it for pathfinding.
"""

# This is still in the planning stages.
NotImplemented

