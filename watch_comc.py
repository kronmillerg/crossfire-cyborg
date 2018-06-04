import client_interfacer

cf = client_interfacer.ClientInterfacer()

cf._sendToClient("watch comc")

while 1:
    s = cf._readLineFromClient()
    if s.startswith("scripttell"):
        break
    cf._sendToConsole(s)

