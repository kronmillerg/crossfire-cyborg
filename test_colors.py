import client_interfacer
import time

cf = client_interfacer.ClientInterfacer()

for i in range(50+1):
    cf.draw("draw %s hello world" % i, color=i)
    # For some reason the script seems to hang if we send too many at once?
    time.sleep(0.1)

