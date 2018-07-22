"""
Copyright (c) 2018 Greg Kronmiller

Partial port of old/travel.py to the new ClientInterfacer API. Only supports
walking between already-defined waypoints.

For transitional use until I can create a real new travel.py.
"""

import glob
import os
import sys

from lib.client_interfacer import ClientInterfacer

# Use a deeper-than-usual pipeline for this one because we really want to walk
# as fast as possible.
cf = ClientInterfacer(targetPendingCommands=10)

DIR = "data/travel"
SERVER = "metalforge"

def main():
    if len(sys.argv) != 3:
        cf.draw("Usage: python %s SOURCE DEST" % sys.argv[0])
        cf.draw("If there are spaces in the name of a city, replace them with "
            "underscores.")
        cf.draw("If there are underscores in the name, too bad.")
        return

    _, source, dest = sys.argv
    source = source.upper().replace("_", " ")
    dest   = dest  .upper().replace("_", " ")

    graph, walks = buildgraph(SERVER)
    gettodest(graph, walks, source, dest)

    cf.draw("You are now at %s" % dest)


###############################################################################
# Main routines that can be performed by this script
# (put in some debugging-esque statements as part of UI)

def followwalk(walk):
    for cmd in walk:
        cf.issueCommand(cmd)

def gettodest(graph, walks, src, dest):
    cf.debugOut(str(graph))
    path = graph.findShortestPath(src, dest)
    cf.draw("Walking from %s to %s" % (src, dest))
    cf.draw("By path: %s" % str(path))
    for i in range(len(path)-1):
        start = path.getNode(i)
        end = path.getNode(i+1)
        walk = walks[start][end]
        followwalk(walk)
    cf.flushCommands()


###############################################################################
# File I/O and walk manipulations

def loadwalk(fpath):
    walk = []
    with file(fpath, "r") as f:
        for line in f:
            walk.append(line.strip())
    return walk

def savewalk(fpath, walk):
    with file(fpath, "w") as f:
        for step in walk:
            f.write(step + "\n")

def getfname(start, end):
    return str(start) + "-" + str(end) + "-path.txt"

def getstartend(fname):
    parts = fname.split("-")
    start, end = parts[:2]
    # turn it to a tuple instead of a list
    return (start, end)

rsteps = {
    "north" : "south",
    "east" : "west",
    "south" : "north",
    "west" : "east",
    "northeast" : "southwest",
    "southeast" : "northwest",
    "southwest" : "northeast",
    "northwest" : "southeast"
}

def reversestep(step):
    return rsteps.get(step, step)

def reversewalk(walk):
    rwalk = []
    for step in reversed(walk):
        rwalk.append(reversestep(step))
    return rwalk

def getallservers():
    x = os.walk(DIR)
    servers = x.next()[1]
    return servers

# Loads 2 things from the files:
#  (1) The Graph, for multipart walks
#  (2) The table of walks, for individual parts
def buildgraph(server):
    graph = Graph()
    walks = {}
    files = glob.glob(DIR + "/" + server + "/*-path.txt")
    for fpath in files:
        walk = loadwalk(fpath)
        rwalk = reversewalk(walk)
        weight = len(walk)
        # fname = fpath.split("\\")[-1]
        fname = os.path.split(fpath)[-1]
        start, end = getstartend(fname)
        start = start.upper()
        end = end.upper()
        graph.addEdge(start, end, weight)
        if start not in walks:
            walks[start] = {}
        walks[start][end] = walk
        graph.addEdge(end, start, weight)
        if end not in walks:
            walks[end] = {}
        walks[end][start] = rwalk
    graph.finalize()
    return (graph, walks)


###############################################################################
# Graph and related classes
# (used for shortest-path calculations)

class Infinity:
    def __init__(self):
        pass
    def __cmp__(self, other):
        if other is self:
            return 0
        return 1
    def __add__(self, other):
        return self
    def __radd(self, other):
        return self

INFINITY = Infinity()

class Path:
    def __init__(self, g, first):
        self.graph = g
        if g.mutable:
            cf.fatal("Error: can't store paths on a mutable graph.")
        self.nodes = [first]
    
    def getNode(self, i):
        return self.graph.getNodeName(self.nodes[i])
    
    def getTotalWeight(self):
        weight = 0
        for i in range(len(self.nodes) - 1):
            weight += self.graph.getEdgeWeight(self.nodes[i], self.nodes[i+1])
        return weight
    
    def append(self, n):
        self.nodes.append(n)
    
    def copy(self):
        p = Path(self.graph, self.nodes[0])
        if len(self.nodes) > 1:
            for n in self.nodes[1:]:
                p.append(n)
        return p
    
    def reverse(self):
        p = Path(self.graph, self.nodes[-1])
        if len(self.nodes) > 1:
            for n in reversed(self.nodes[:-1]):
                p.append(n)
        return p
    
    def __len__(self):
        return len(self.nodes)
    
    def __str__(self):
        s = ""
        s += self.graph.getNodeName(self.nodes[0])
        for i in range(1, len(self.nodes)):
            s += " -> "
            s += self.graph.getNodeName(self.nodes[i])
        return s

class Graph:
    NOT_CONNECTED = -1
    
    def __init__(self):
        self.nodes = []
        self.edges = []
        self.mutable = True
    
    # public
    def getNodes(self):
        return self.nodes[:]
    
    # public
    def getNumNodes(self):
        return len(self.nodes)
    
    # public
    def getNumEdges(self):
        return len(self.edges)
    
    # public
    def containsNode(self, name):
        return name in self.nodes
    
    def getNodeName(self, i):
        return self.nodes[i]
    
    def getNodeIndex(self, name):
        return self.nodes.index(name)
    
    # public
    def addNode(self, name):
        if not self.mutable:
            cf.fatal("Error: attempt to modify a finalized Graph.")
        self.nodes.append(name)
        for i in range(len(self.edges)):
            self.edges[i].append(Graph.NOT_CONNECTED)
        self.edges.append([Graph.NOT_CONNECTED
                           for i in range(len(self.nodes))])
    
    def containsEdge(self, start, end):
        return self.edges[start][end] != Graph.NOT_CONNECTED
    
    def getEdgeWeight(self, start, end):
        return self.edges[start][end]
    
    def link(self, start, end, weight):
        if not self.mutable:
            cf.fatal("Error: attempt to modify a finalized Graph.")
        if max(start, end) >= self.getNumNodes():
            cf.fatal("Error: no node with index %d" % max(start, end))
        if self.containsEdge(start, end):
            cf.fatal("Error: edge from %s to %s already exists." %
                (self.getNodeName(start), self.getNodeName(end)))
        self.edges[start][end] = weight
    
    # public
    def addEdge(self, start, end, weight):
        if not self.containsNode(start):
            self.addNode(start)
        if not self.containsNode(end):
            self.addNode(end)
        si = self.getNodeIndex(start)
        ei = self.getNodeIndex(end)
        self.link(si, ei, weight)
    
    # public
    def finalize(self):
        self.mutable = False
        self.shortest_paths = [[None for i in r] for r in self.edges]
        for i in range(self.getNumNodes()):
            self.shortest_paths[i][i] = Path(self, i)
    
    # public
    def getTotalWeight(self, start, end):
        if self.mutable:
            cf.fatal("Error: can't perform shortest-path calculations on an "
                "unfinalized Graph.")
        path = self.shortest_paths[start][end]
        if path == None:
            return INFINITY
        return path.getTotalWeight()
    
    def dijkstra(self, src):
        if self.mutable:
            cf.fatal("Error: can't perform shortest-path calculations on an "
                "unfinalized Graph.")
        visited = [False for i in self.nodes]
        curr = src
        done = False
        while not done:
            for i in range(self.getNumNodes()):
                if not visited[i]:
                    if self.containsEdge(curr, i):
                        dist = self.getTotalWeight(src, curr) + \
                            self.getEdgeWeight(curr, i)
                        if dist < self.getTotalWeight(src, i):
                            path = self.shortest_paths[src][curr].copy()
                            path.append(i)
                            self.shortest_paths[src][i] = path
            visited[curr] = True
            closest = -1
            for i in range(self.getNumNodes()):
                if not visited[i]:
                    if closest == -1 or self.getTotalWeight(src, i) < \
                            self.getTotalWeight(src, closest):
                        closest = i
            if closest == -1:
                done = True
            else:
                curr = closest
    
    # public
    def findShortestPath(self, src, dest):
        if self.mutable:
            cf.fatal("Error: can't perform shortest-path calculations on an "
                "unfinalized Graph.")
        if not self.containsNode(src):
            cf.fatal("Error: no node '%s' in Graph." % (src))
        if not self.containsNode(dest):
            cf.fatal("Error: no node '%s' in Graph." % (dest))
        src = self.getNodeIndex(src)
        dest = self.getNodeIndex(dest)
        if self.shortest_paths[src][dest] == None:
            self.dijkstra(src)
        return self.shortest_paths[src][dest]
    
    # for debugging only
    def __str__(self):
        s = ""
        s += "nodes: " + str(self.nodes) + ", edges: ["
        for start in range(len(self.nodes)):
            for end in range(len(self.nodes)):
                if self.containsEdge(start, end):
                    s += "(%s-%s, cost %d), " % (self.nodes[start],
                        self.nodes[end], self.getEdgeWeight(start, end))
        s += "]"
        return s


###############################################################################
# Call main()

if __name__ == "__main__":
    main()

