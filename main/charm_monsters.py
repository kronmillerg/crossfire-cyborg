from lib.client_interfacer import ClientInterfacer

cf = ClientInterfacer()
cf.watchStats()

MIN_MED_PER_CAST = 4

while True:
    if cf.hasScripttell():
        cf.draw("Exiting.")
        break
    if cf.playerInfo.sp >= 0.8 * cf.playerInfo.maxsp:
        cf.queueCommand("invoke charm monsters")
        cf.queueCommand("killpets")
        for i in range(MIN_MED_PER_CAST):
            cf.queueCommand("use_skill meditation")
        cf.issueQueuedCommands(maxQueueSize = max(MIN_MED_PER_CAST - 1, 0))
    else:
        cf.issueCommand("use_skill meditation")
    cf.idle()

cf.flushCommands()

