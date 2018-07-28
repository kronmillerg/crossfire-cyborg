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
    all of them, but a rectangular border is easier to check anyway.)

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
  - Wrong question. The answer to the question as asked is obviously "not yet".
    The real question is, should we reserve characters that are logically for
    PoI to mean "also a PoI, but not passable"? For example, reserve capital
    letters or digits?
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

import collections
import re

# Regular expressions for the various symbols you can use in the "picture" part
# of a map description. These are only permitted to match single characters;
# else the alignment of the picture will get messed up. Basically each one
# needs to either be a single (possibly-escaped) character, or else a character
# class. Also, it is assumed that no two of them will ever match the _same_
# character, except that RE_PORTAL_NAME_DELIM may be the same as one of the
# ones used in the picture. (Technically RE_ANNOT_END can as well, but that's
# discouraged as it seems somewhat more confusing.)
RE_ANNOT_START       = re.compile("\[")       # Start of annotation
RE_ANNOT_END         = re.compile("\]")       # End of annotation
    # The RE_ANNOT_START and RE_ANNOT_END characters nest like parentheses. So
    # for example, "[foo [bar]] [baz]" has 2 annotations, not 3.
RE_PORTAL_NAME_DELIM = re.compile(">")
    # Separates portal name from destination (in annotation).
RE_WALL              = re.compile("[-+|#]")   # Impassable square
RE_FLOOR             = re.compile("[. ]")     # Passable square
RE_POINT_OF_INT      = re.compile("[a-zA-Z]")
    # Point of interest. Must have a corresponding annotation giving its name.
RE_UNKNOWN           = re.compile("\?")
    # Don't have a good way to represent this square; avoid stepping on it.
    # (This is treated the same as a wall by pathfinding, but conceptually it's
    # different.)
RE_PORTAL_APPLY      = re.compile("[><]")     # Portal, apply to use
RE_PORTAL_STEP       = re.compile("\^")       # Portal, step on to use
RE_CUSTOM_ENDPT      = re.compile("!")
    # Endpoint of a custom-defined path. (Not implemented yet.)

# TODO: Can we create a reportError function to replace all these logErrors,
# which does nice things like pointing you to the line and character where the
# error appeared? Might be overkill, though, especially since the map
# descriptions are likely to be hardcoded in scripts in practice. (If the map
# is read from a file, it's kind of hard to know what the names of the
# waypoints are.)

# Take in a ClientInterfacer so we can report errors.
# TODO: Passing a ClientInterfacer around just for error reporting seems like
# an annoying way to do things; can we avoid this somehow?
#   - Maybe just make it global? But Python _really_ doesn't like globals...
def parseMap(desc, cf):
    rooms = {}

    roomName  = None
    roomLines = []

    def makeRoomForPrevLines():
        if roomLines:
            newRoom = parseRoom(roomName, roomLines, cf)
            if newRoom is not None:
                rooms[roomName] = newRoom
        elif roomName is not None:
            cf.logError("No map given for room %s" % roomName)

    # Read through all the lines of the description and parse them into rooms.
    for line in desc.split("\n"):
        if not line.strip():
            # Lines that are empty (except for whitespace) mark the end of a
            # previous Room. Such lines at the start or end of the map are
            # ignored.
            roomName  = None
            roomLines = []
            makeRoomForPrevLines()
        if roomName is None:
            # First nonblank line either at the start of the desc or after a
            # blank line -- this is the name of the next room.
            roomName = line.strip()
        else:
            # If we already have a roomName, then this is a line from the main
            # room description. Just add it to the list; we'll handle parsing
            # these in parseRoom. In this case do _not_ strip() the line,
            # because column alignment is important when parsing the picture.
            roomLines.append(line)
    makeRoomForPrevLines()

    # FIXME 2: Create suite, link rooms.
    NotImplemented

def parseRoom(name, lines, cf):
    assert len(lines) > 0

    # A typical line looks something like:
    #     | p >  | [point-of-interest] [staircase-destination]
    # Split off the part of each line that's the "picture" ("| p >  |") from
    # the annotations listed afterward ("[point-of-interest]
    # [staircase-destination]").
    pictureRows = []
    annotations = []
    for line in lines:
        firstAnnot = RE_ANNOT_START.search(line)
        if firstAnnot is not None:
            startOfAnnot = firstAnnot.start()
            pictureRows.append(line[:startOfAnnot])
            annotations.append(line[startOfAnnot:])
        else:
            pictureRows.append(line)
            annotations.append("")

    assert len(pictureRows) == len(annotations) == len(lines) > 0
    height = len(pictureRows)

    # Convert each element of annotations from a string (all the annotations,
    # unparsed) to a list of individual annotations.
    for i in range(len(annotations)):
        annotStr = annotations[i]
        # If we found an RE_ANNOT_START on this line, then it is the first
        # character of annotStr. Else, annotStr is "".
        if len(annotStr) == 0:
            annotations[i] = []
            continue
        assert RE_ANNOT_START.match(annotStr[0])
        annotList = []
        currAnnot = ""
        nestingDepth = 0
        for c in annotStr:
            # Probably some of this logic could be combined, but I'm not yet
            # convinced it would be easier to read that way.
            if RE_ANNOT_START.match(c):
                if nestingDepth > 0:
                    # Already inside an annotation.
                    currAnnot += c
                else:
                    # Starting a new annotation. currAnnot will already be ""
                    # because we cleared it at the last END_ANNOT.
                    assert currAnnot == ""
                nestingDepth += 1
            elif RE_ANNOT_END.match(c):
                if nestingDepth <= 0:
                    cf.logError("Error parsing %s: unbalanced " \
                        "end-annotation marker." % name)
                    return None
                nestingDepth -= 1
                if nestingDepth == 0:
                    # We just closed the outermost pair of brackets, and
                    # therefore finished the current annotation.
                    annotList.append(currAnnot)
                    currAnnot = ""
                else:
                    currAnnot += c
            elif nestingDepth == 0:
                if not c.isspace():
                    cf.logError("Error parsing %s: non-whitespace " \
                        "character outside of (but among) annotations." % \
                        name)
                    return None
                # Don't add it to currAnnot because we're not in an annotation.
            else:
                # Just a regular character inside an annotation.
                currAnnot += c
        if nestingDepth > 0:
            cf.logError("Error parsing %s: unbalanced start-annotation " \
                "marker." % name)
            return None
        annotations[i] = annotList

    # Strip whitespace from the _right_ side of each row of the picture without
    # regard for alignment. Jagged trailing whitespace won't affect the
    # appearance of the main picture, so doesn't matter. For example, the
    # "picture" portion of this:
    #     +---+   [annotation]
    #     |   |[annotation]
    #     |   |                          [annotation]
    #     +---+ [annotation]
    # still looks like a rectangle.
    for i in range(len(pictureRows)):
        pictureRows[i] = pictureRows[i].rstrip()

    # On the left side, allow all rows to start with the same prefix consisting
    # of only spaces and (horizontal) tabs; strip off that prefix. However,
    # require that after that prefix, each row start with a non-whitespace
    # character. So it's valid to write something like:
    #     +---+
    #     |...|
    #     ....|
    #     +---+
    # or:
    #     +---+
    #     |   |
    #     .   |
    #     +---+
    # but not:
    #     +---+
    #     |   |
    #         |
    #     +---+
    # Do _not_ strip off any other types of whitespace from the left (ex:
    # vertical tab), since they may have weirder effects on alignment.
    commonPrefix = ""
    for c in pictureRows[0]:
        if c in (" ", "\t"):
            commonPrefix += c
        else:
            break
    for i in range(len(pictureRows)):
        if pictureRows[i].startswith(commonPrefix):
            # Strip common prefix
            pictureRows[i] = pictureRows[i][len(commonPrefix):]
        else:
            # Didn't have that prefix
            cf.logError("Error parsing %s: every row must start with " \
                "the same whitespace." % name)
            return None
        if len(picture_rows[i]) == 0:
            # Nothing left after prefix
            cf.logError("Error parsing %s: empty row in picture." % name)
            return None
        if picture_rows[i][0].isspace():
            # More space left after prefix
            if picture_rows[i][0] in (" ", "\t"):
                cf.logError("Error parsing %s: every row must start with " \
                    "the same whitespace." % name)
            else:
                cf.logError("Error parsing %s: invalid whitespace at start " \
                    "of row: %r." % (name, picture_rows[i][0]))
            return None

    # Now check that every row has the same width. Note that since we've
    # stripped out trailing whitespace, the following is invalid:
    #     +---+
    #     |   |
    #     |    
    #     +---+
    # and must instead be written as (for example):
    #     +---+
    #     |   |
    #     |   .
    #     +---+
    width = len(pictureRows[0])
    for row in pictureRows:
        if len(row) != width:
            cf.logError("Error parsing %s: map is not rectangular. (Note: " \
                "trailing whitespace doesn't count.)" % name)
            return None

    # At this point, the picture is known to be rectangular (of size at least
    # 1x1), with non-whitespace characters on the far left and far right of
    # each row. Assert all of this here.
    assert len(pictureRows) == height > 0
    for row in pictureRows:
        assert len(row) == width > 0
        assert not row[ 0].isspace()
        assert not row[-1].isspace()

    # "You're tearing me apart, Lisa!"
    theRoom = Room(name, width, height)
    for y in range(height):
        # Each time we need an annotation, we pop from the start of this.
        rowAnnots = collections.deque(annotations[y])
        for x in range(width):
            c = pictureRows[y][x]
            if RE_WALL.match(c):
                theRoom[x, y] = Room.WALL
            elif RE_FLOOR.match(c):
                theRoom[x, y] = Room.FLOOR
            elif RE_POINT_OF_INT.match(c):
                theRoom[x, y] = Room.FLOOR
                # TODO: There are 3 copies of this check... can we factor it
                # out somehow?
                if not rowAnnots:
                    cf.logError("Error parsing %s: not enough annotations." % \
                        name)
                    return None
                poiName = rowAnnots.popleft()
                theRoom.addPointOfInterest(poiName, x, y)
            elif RE_UNKNOWN.match(c):
                theRoom[x, y] = Room.UNKNOWN
            elif RE_PORTAL_APPLY.match(c):
                theRoom[x, y] = Room.PORTAL_APPLY
                if not rowAnnots:
                    cf.logError("Error parsing %s: not enough annotations." % \
                        name)
                    return None
                if not addPortalToRoom(theRoom, rowAnnots.popleft(), x, y)
                    return None
            elif RE_PORTAL_STEP.match(c):
                theRoom[x, y] = Room.PORTAL_STEP
                if not rowAnnots:
                    cf.logError("Error parsing %s: not enough annotations." % \
                        name)
                    return None
                if not addPortalToRoom(theRoom, rowAnnots.popleft(), x, y):
                    return None
            elif RE_CUSTOM_ENDPT.match(c):
                # TODO
                cf.logError("Custom paths not implemented yet.")
                return None
            else:
                cf.logError("Error parsing %s: unrecognized character in " \
                    "map: %r." % (name, c))
                return None
        if rowAnnots:
            cf.logError("Error parsing %s: too many annotations." % name)
            return None

    return theRoom

def addPortalToRoom(theRoom, annot, x, y):
    "Return True on success, False on failure."
    parts = RE_PORTAL_NAME_DELIM.split(annot)
    assert len(parts) > 0
    name = None
    dest = None
    if len(parts) == 1:
        # Only a dest
        dest = parts[0]
    elif len(parts) == 2:
        theRoom.addPointOfInterest(parts[0], x, y)
        dest = parts[1]
    else:
        cf.logError("Error parsing %s: portal annotation contains multiple " \
            "name-dest delimiters." % theRoom.name)
        return False
    assert dest is not None
    theRoom.setPortalDestName(x, y, dest)

# FIXME 1: Implement Room class.

