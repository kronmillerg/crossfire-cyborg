from client_interfacer import ClientInterfacer, Color

cf = ClientInterfacer(maxPendingCommands=100)

cf.draw("scripttell me the tag of an item to use for the test.")
cf.waitForScripttell()
s = cf.getNextScripttell()
tag = int(s)

testItem = None
for item in cf.getInventory():
    if item.tag == tag:
        testItem = item
        break

if testItem is None:
    cf.fatal("Couldn't find item with tag %d" % tag)

dropCmd   = cf.getDropCommand(testItem)
pickupCmd = cf.getPickupCommand(testItem)
for i in range(20):
    # We set maxPendingCommands high enough that these will all dispatch
    # immediately.
    cf.queueCommand(dropCmd)
    cf.queueCommand(pickupCmd)
cf.queueCommand("east")
cf._sendToClient("sync 6")

# Fall back to passthru.py.
while 1:
    s = cf._readLineFromClient()
    cf.draw("recv: '%s'" % (s))
    if s.startswith( "scripttell "):
        rest = s[len("scripttell "):]
        cf.draw("send: %s" % (rest), color=Color.DARK_ORANGE)
        cf._sendToClient(rest)

