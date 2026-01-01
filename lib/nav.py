"""
Copyright (c) 2025 Greg Kronmiller
"""

# auto not in py3.5
#from enum import Enum, auto
from enum import Enum
from queue import PriorityQueue

# Notes:
#     request map pos -> request map pos X Y
# where:
#   - X increases eastward, Y increases southward (so computer-style rather
#     than math-style)
#   - the 0 point is arbitrary and quite possibly off the edge of the map
#       - ...but the pos seems to stay roughly continuous when moving between
#         rooms. Probably shouldn't depend on that, but at least don't depend
#         on NOT-that; i.e., don't expect a discontinuity in map pos to tell us
#         whether we've changed rooms.

class Navigator:
    def __init__(self, cf, suite, startPos=None):
        self.cf = cf
        self.suite = suite
        self.pos = startPos

    def setPos(self, pos):
        self.pos = pos

    def travelTo(self, dest):
        assert self.pos is not None
        self.travelBetween(self.pos, dest)
        self.pos = dest

    def travelBetween(self, start, end):
        # Do a BFS from start to end
        frontier = PriorityQueue()
        self.suite.resetVisited()
        start.visitFrom(None)
        frontier.put(PathNode(start))
        while not frontier.empty():
            pos = frontier.get().pos
            if pos == end:
                break
            # TODO prioritize non-diagonals so we don't "wiggle" unnecessarily
            for neighbor in pos.neighbors():
                if neighbor.passability == Passability.FREE and \
                        not neighbor.visited():
                    neighbor.visitFrom(pos)
                    frontier.put(PathNode(neighbor))

        # Follow visited links to construct the path
        if not end.visited():
            raise RuntimeError("No path from {0} to {1}".format(start, end))
        path = [end]
        pos = end
        while pos is not start:
            # Each step makes progress, can't infinite-loop
            assert pos.visitedFrom.visitedDepth < pos.visitedDepth
            pos = pos.visitedFrom
            path.append(pos)
        path.reverse()

        # Now actually walk the path
        for i in range(len(path) - 1):
            direc = path[i].getDirectionTo(path[i+1])
            self.cf.issueCommand(DIR_COMMAND[direc])

class PathNode:
    def __init__(self, pos):
        self.pos = pos

    def __lt__(self, rhs):
        return self.pos.visitedDepth < rhs.pos.visitedDepth

# I was originally going to call this class Map, but that's one capitalization
# off from being a Python builtin.
class Suite:
    """
    A collection of rooms that are handled together, presumably all connected
    though this is not strictly required.
    """

    def __init__(self, rooms=[]):
        self.rooms = rooms[:]
        # Points of Interest. Maps names to which Room the POI is in.
        # No two Rooms in a Suite can have POIs with the same name, and
        # suite.poi.keys() is the union of rooms[:].keys(). These are enforced
        # in both Suite.addRoom (if the Room has POIs from before it was added
        # to the Suite) and Room.addPOI (if POIs are added to the Room after
        # it's added to the Suite).
        self.poi = {}

    def addRoom(self, room):
        assert room.suite is None
        self.rooms.append(room)
        room.suite = self

        # Add all of its POIs to our map
        for poiName in room.poi.keys():
            if poiName in self.poi:
                raise ValueError("Suite already has a POI named {!r}"
                        .format(poiName))
            self.poi[poiName] = room

    def resetVisited(self):
        for room in self.rooms:
            room.resetVisited()

class Room:
    def __init__(self, name, width, height):
        self.name  = name
        self.suite = None
        self.tiles = [[Tile(self, x, y) for x in range(width)]
                                        for y in range(height)]
        # Points of Interest. Maps names to (x, y) pair.
        self.poi = {}

        # Link all tiles to their neighbors
        for tile in self:
            for direc, delta in DIR_DISPLACEMENT.items():
                dx, dy = delta
                x2 = tile.x + dx
                y2 = tile.y + dy
                if self.inBounds(x2, y2):
                    tile.setNeighbor(direc, self[x2, y2])

    def inBounds(self, x, y):
        return 0 <= y < len(self.tiles) and \
               0 <= x < len(self.tiles[y])

    # TODO take in a Tile so we can do something like this?
    #     room.addPOI("X", room["Y"].neighbor(Direction.SOUTHEAST))
    # And then have self.poi map to the Tile directly.
    def addPOI(self, name, x, y):
        if name in self.poi:
            raise ValueError("Room {} already has a POI named {!r}" \
                    .format(self, name))
        self.poi[name] = (x, y)

        # Also add it to our Suite, if we have one.
        if self.suite is not None:
            if name in self.suite.poi:
                raise ValueError("Suite already has a POI named {!r}" \
                        .format(name))
            self.suite.poi[name] = self

    def resetVisited(self):
        for tile in self:
            tile.resetVisited()

    def __iter__(self):
        for row in self.tiles:
            # Not in Python 3.5
            #yield from row
            for tile in row:
                yield tile

    def __getitem__(self, pos):
        if isinstance(pos, str):
            pos = self.poi[pos]
        x, y = pos
        return self.tiles[y][x]

    def __str__(self):
        return self.name

def parseRoom(name, desc):
    tiles = []
    lines = desc.strip().split("\n")
    for line in lines:
        tiles.append(line.split())

    if not tiles:
        # Avoid indexing empty lists below
        return Room(name, 0, 0)

    height = len(tiles)
    widths = [len(r) for r in tiles]
    if len(set(widths)) != 1:
        raise ValueError("Room desc is not rectangular")
    width = widths[0]
    room = Room(name, width, height)

    for y in range(height):
        for x in range(width):
            tileDesc = tiles[y][x]
            if tileDesc == ".":
                room[x, y].passability = Passability.FREE # Already the default
            elif tileDesc == "#":
                room[x, y].passability = Passability.BLOCKED
            elif tileDesc == "?":
                room[x, y].passability = Passability.UNKNOWN
            else:
                # If it's anything else, it's a named POI.
                room.addPOI(tileDesc, x, y)

    return room

class Tile:
    def __init__(self, room, x, y):
        self.room = room
        self.x = x
        self.y = y
        self.passability = Passability.FREE

        # Maps Direction : Tile
        self.edges = {}

        # For BFS
        self.visitedDepth = -1
        self.visitedFrom  = None

    def neighbors(self):
        return self.edges.values()

    #def neighbor(self, direction):
    #    # TODO who handles the error if no neighbor?
    #    #return self.edges.get(direction, None)
    #    return self.edges[direction]

    def setNeighbor(self, direction, otherTile):
        self.edges[direction] = otherTile

    def getDirectionTo(self, other):
        for direction, neighbor in self.edges.items():
            if neighbor == other:
                return direction
        raise ValueError("pos {} not adjacent to {}".format(self, other))

    def resetVisited(self):
        self.visitedDepth = -1
        self.visitedFrom  = None

    def visitFrom(self, other):
        assert not self.visited()
        self.visitedFrom  = other
        if other is None:
            self.visitedDepth = 0
        else:
            self.visitedDepth = other.visitedDepth + 1

    def visited(self):
        if self.visitedDepth == -1:
            assert self.visitedFrom is None
            return False
        else:
            return True

    def __str__(self):
        return "{}({}, {})".format(self.room, self.x, self.y)

class Passability(Enum):
    # auto not in py3.5
    FREE    = 1 # auto()
    BLOCKED = 2 # auto()
    UNKNOWN = 3 # auto()

class Direction(Enum):
    # 8 compass directions...
    NORTH     = 1 # auto()
    SOUTH     = 2 # auto()
    EAST      = 3 # auto()
    WEST      = 4 # auto()
    NORTHEAST = 5 # auto()
    SOUTHEAST = 6 # auto()
    NORTHWEST = 7 # auto()
    SOUTHWEST = 8 # auto()
    # ...and one special case for "use this door/portal to travel to another
    # room"
    APPLY     = 9 # auto()

DIR_DISPLACEMENT = {
    Direction.NORTH     : ( 0, -1),
    Direction.SOUTH     : ( 0,  1),
    Direction.WEST      : (-1,  0),
    Direction.EAST      : ( 1,  0),
    Direction.NORTHWEST : (-1, -1),
    Direction.SOUTHWEST : (-1,  1),
    Direction.NORTHEAST : ( 1, -1),
    Direction.SOUTHEAST : ( 1,  1),
}

DIR_COMMAND = {
    Direction.NORTH     : "north",
    Direction.SOUTH     : "south",
    Direction.WEST      : "west",
    Direction.EAST      : "east",
    Direction.NORTHWEST : "northwest",
    Direction.SOUTHWEST : "southwest",
    Direction.NORTHEAST : "northeast",
    Direction.SOUTHEAST : "southeast",
    Direction.APPLY     : "apply",
}

