import os
import time

from mininet.clean import cleanup

from . import TbThread
from . import RealNetwork
from . import linkDnmcThreads # for threadFunc execution
from autoTest import get_trace
from autoTest.MyParam import gen_linear_topo


# logPath: where to write the logs
# isManual: open the command line intereface, or wait until the latchThreads end
def run(testParam, logPath, isManual):
    print("cleanup mininet...")
    clear()

    #static
    if not testParam.appParam.dynamic:
        if testParam.topoParam.nodes is None:
            testParam.topoParam = gen_linear_topo(testParam.topoParam.numMidNode)
        mn = RealNetwork.createNet(testParam)
    #dynamic
    else:
        if testParam.appParam.dynamic_complete: # for topo designed by user
            dynamic_trace = testParam.topoParam
        else:                                   # for real starlink topo
            if testParam.appParam.src==-1 or testParam.appParam.dst==-1:
                origin_trace = testParam.topoParam
            else:
                origin_trace = get_trace.get_trace(testParam.appParam.src,testParam.appParam.dst,route_algorithm=testParam.appParam.route_algorithm)
            if testParam.appParam.route_algorithm=="with_isl":
                dynamic_trace = get_trace.get_complete_trace(origin_trace=origin_trace,
                                                    isl_loss=testParam.appParam.dynamic_isl_loss,
                                                    uplink_loss=testParam.appParam.dynamic_gsl_loss,
                                                    downlink_loss=testParam.appParam.dynamic_gsl_loss,
                                                    ground_link_loss = testParam.appParam.dynamic_ground_link_loss, 
                                                    ground_link_rtt = testParam.appParam.dynamic_ground_link_rtt,
                                                    uplink_bw = testParam.appParam.dynamic_uplink_bw,
                                                    downlink_bw = testParam.appParam.dynamic_downlink_bw,
                                                    ground_link_bw = testParam.appParam.dynamic_ground_link_bw,
                                                    isl_bw = testParam.appParam.dynamic_isl_bw,
                                                    bw_fluctuation=testParam.appParam.dynamic_bw_fluct)
                #print(dynamic_trace)
            elif testParam.appParam.route_algorithm=="relay_only":
                dynamic_trace = get_trace.get_complete_relay_only_trace(origin_trace=origin_trace,
                                                                        uplink_bw = testParam.appParam.dynamic_uplink_bw,
                                                                        downlink_bw = testParam.appParam.dynamic_downlink_bw,
                                                                        ground_link_bw = testParam.appParam.dynamic_ground_link_bw,
                                                                        uplink_loss = testParam.appParam.dynamic_isl_loss,
                                                                        downlink_loss = testParam.appParam.dynamic_isl_loss,
                                                                        ground_link_loss = testParam.appParam.dynamic_ground_link_loss,
                                                                        ground_link_rtt = testParam.appParam.dynamic_ground_link_rtt,
                                                                        bw_fluctuation = testParam.appParam.dynamic_bw_fluct)
        mn = RealNetwork.create_dynamic_net(dynamic_trace)
        testParam.topoParam = dynamic_trace
    time.sleep(0.5)

    threads = [t for t in TbThread.Threads
            if not(t.isLatchThread and isManual)]

    if isManual:
        TbThread.latchNumInc()
    for thread in threads:
        #static
        thread.start(mn, testParam, logPath)

        #dynamic
        #thread.start(mn,links_params,isls,logPath)
    if isManual:
        time.sleep(1)
        #mn.openXterm()
        mn.enterCli()
        TbThread.latchNumDec()
    for thread in threads:
        thread.join()
    
    return

def clear():
    # os.system('sudo mn -c >/dev/null 2>&1')
    cleanup()

    os.system('sudo killall -9 xterm >/dev/null 2>&1')

    # os.system('kill -9 `jobs -ps`')
    # os.system('kill -9 $(jobs -p)')
    # os.system('kill $(jobs -l | grep Stopped | cut -d\' \' -f3)')
    os.system("for x in `ps -aux | awk {\'if ($8 == \"Tl\") print $2\'}`; do kill -9 $x; done")

    TbThread.latchNumReset()
