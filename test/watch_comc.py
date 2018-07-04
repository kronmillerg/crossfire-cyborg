from lib.client_interfacer import ClientInterfacer

cf = ClientInterfacer()

cf._sendToClient("watch comc")

while 1:
    s = cf._readLineFromClient()
    if s.startswith("scripttell"):
        break
    cf._sendToConsole(s)

