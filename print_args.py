"""
Print sys.argv for the player to see. To demonstrate that you can pass command
line arguments to crossfire scripts.
"""

import sys

import client_interfacer

cf = client_interfacer.ClientInterfacer()

cf.draw("sys.argv is:")
for i in range(len(sys.argv)):
    cf.draw("-   %s) %r" % (i, sys.argv[i]))

