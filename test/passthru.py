from lib.client_interfacer import ClientInterfacer, Color

cf = ClientInterfacer()

while 1:
    s = cf._readLineFromClient()
    cf.draw("recv: '%s'" % (s))
    if s.startswith( "scripttell "):
        rest = s[len("scripttell "):]
        cf.draw("send: %s" % (rest), color=Color.DARK_ORANGE)
        cf._sendToClient(rest)

