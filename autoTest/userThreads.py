from asyncio import protocols
import time
import random
from testbed import Param
from testbed.TbThread import *
from FileUtils import delFile


@threadFunc(False)
def Init(mn, testParam, logPath):
    #todo : dynamic
    link_names = [] 
    if not testParam.appParam.dynamic:
        link_names = testParam.topoParam.linkNames()
    else:
        max_midnodes,total_midnodes,isls,links_params = testParam.topoParam
        for i,isl in enumerate(isls):
            numA,numB = isl
            nameA = 'gs1' if numA==0 else 'm%d'%(numA)
            nameB = 'gs2' if numB==-1 else 'm%d'%(numB)
            linkName = nameA + Param.LinkNameSep + nameB
            link_names.append(linkName)
        link_names += ['h1_gs1','gs2_h2']
    #print(link_names)
    for l in link_names:
        nameA,nameB = l.split(Param.LinkNameSep)
        nodeA = mn.getNodeByName(nameA)
        switch = mn.getNodeByName(l)
        nodeB = mn.getNodeByName(nameB)

        atomic(nodeA.cmd)("ifconfig %s txqueuelen %d"%(l,testParam.appParam.txqueuelen))
        atomic(nodeB.cmd)("ifconfig %s txqueuelen %d"%(nameB+Param.LinkNameSep+nameA,testParam.appParam.txqueuelen))
        
        ### max_queue_size
        # tc -s -d qdisc show dev pep_eth2
        # print(testParam.max_queue_size)
        
        intf = nodeA.connectionsTo(switch)[0][0]
        cmds, parent = atomic(intf.delayCmds)(max_queue_size=testParam.appParam.max_queue_size,is_change=True)
        for cmd in cmds:
            atomic(intf.tc)(cmd)
        intf = nodeB.connectionsTo(switch)[0][0]
        cmds, parent = atomic(intf.delayCmds)(max_queue_size=testParam.appParam.max_queue_size,is_change=True)
        for cmd in cmds:
            atomic(intf.tc)(cmd)
        

def kill_intcp_processes(mn,testParam):
    atomic(mn.getNodeByName('h2').cmd)('killall intcps')
    atomic(mn.getNodeByName('h1').cmd)('killall intcpc')
    if testParam.appParam.midCC != 'nopep':
        if not testParam.appParam.dynamic:     #static topo
            for node in testParam.topoParam.nodes:
                if node not in ['h1','h2']:
                    atomic(mn.getNodeByName(node).cmd)('killall intcpm')
        else:   #dynamic topo
            max_midnodes,total_midnodes,isls,links_params = testParam.topoParam
            nodes = ['m%d'%(i+1) for i in range(total_midnodes)]+['gs1','gs2']
            for node in nodes:
                atomic(mn.getNodeByName(node).cmd)('killall intcpm')

def kill_pep_processes(mn,testParam):
    atomic(mn.getNodeByName('h2').cmd)('killall iperf3')
    atomic(mn.getNodeByName('h1').cmd)('killall iperf3')
    if testParam.appParam.midCC != 'nopep':
        if not testParam.appParam.dynamic:  #static topo
            for node in testParam.topoParam.nodes:
                if node not in ['h1','h2']:
                    atomic(mn.getNodeByName(node).cmd)('killall pepsal')
        else:   #dynamic topo
            for node in ['gs1','gs2']:
                atomic(mn.getNodeByName(node).cmd)('killall pepsal')

def start_midnode_processes(mn,testParam,logPath,useTCP,pep_nodelay=0):
    if testParam.appParam.midCC != 'nopep':
        '''
        if useTCP:      # tcp => open pepsal on gs1 and gs2 
            proxy_nodes =  ['gs1','gs2']
            proxy_nodes += ['m%d'%(i+1) for i in range(testParam.topoParam.numMidNode)]
            #print(proxy_nodes)
            for node in proxy_nodes:
                atomic(mn.getNodeByName(node).cmd)(f'../pepsal_min/bash/runpep {testParam.appParam.midCC} {pep_nodelay} >/dev/null 2>&1 &')
                time.sleep(2)
        else:           # intcp => open intcpm on ground station and satellites
            if not testParam.appParam.dynamic:      #static topo
                for node in testParam.topoParam.nodes:
                    if node not in ['h1','h2','dummy']: #dummy node for flow test
                        if testParam.appParam.test_type=="cpuTest" and node=="m1":
                            atomic(mn.getNodeByName(node).cmd)('../appLayer/intcpApp/intcpm > %s/%s.txt &'%(logPath,testParam.name))
                        else:
                            atomic(mn.getNodeByName(node).cmd)('../appLayer/intcpApp/intcpm >/dev/null 2>&1 &')
                        #atomic(mn.getNodeByName(node).cmd)('../appLayer/intcpApp/intcpm > %s/%s_%s &'%(logPath,testParam.name,node))
                        time.sleep(1)
            else:   #dynamic topo
                max_midnodes,total_midnodes,isls,links_params = testParam.topoParam
                midnodes = ['m%d'%(i+1) for i in range(total_midnodes)]
                if testParam.appParam.coverage == 1:
                    active_midnodes = midnodes
                else:
                    active_midnodes = random.sample(midnodes,int(testParam.appParam.coverage*total_midnodes))
                nodes = ['gs1','gs2']+active_midnodes
                #print(nodes)
                for node in nodes:
                    atomic(mn.getNodeByName(node).cmd)('../appLayer/intcpApp/intcpm > /dev/null 2>&1 &')
                    #atomic(mn.getNodeByName(node).cmd)('../appLayer/intcpApp/intcpm > %s/%s_%s &'%(logPath,testParam.name,node))
                    time.sleep(0.1)
                #if testParam.appParam.dynamic_intv > total_midnodes:
                #    time.sleep(testParam.appParam.dynamic_intv-total_midnodes)  #avoid the first link change
        '''
        atomic(mn.getNodeByName('gs1').cmd)('../appLayer/intcpApp/intcptc >/dev/null 2>&1 &')
        time.sleep(0.1)
        atomic(mn.getNodeByName('gs2').cmd)('../appLayer/intcpApp/intcpts >/dev/null 2>&1 &')
        time.sleep(0.1)
    else:
        '''
        for node in ['m%d'%(10*i+9) for i in range(1)]:
            atomic(mn.getNodeByName(node).cmd)('../appLayer/intcpApp/intcpm >/dev/null 2>&1 &')
            time.sleep(1)
        '''
        if testParam.appParam.dynamic:
            time.sleep(2)   #wait the dynamic update thread to set route

@threadFunc(True)
def ThroughputTest(mn,testParam,logPath):
    if testParam.appParam.test_type not in ["throughputTest","throughputWithTraffic"]:
        return
    logFilePath = '%s/%s.txt'%(logPath, testParam.name)
    delFile(logFilePath)
    
    useTCP = testParam.appParam.get('protocol')=="TCP"
    for i in range(testParam.appParam.sendRound): #TODO log is overwritten now
        #NOTE open pep; cleaript
        start_midnode_processes(mn,testParam,logPath,useTCP)
        if testParam.appParam.test_type=="throughputWithTraffic":
            if not testParam.appParam.dynamic and 'dummy' in testParam.topoParam.nodes:
                atomic(mn.getNodeByName('h2').cmd)('echo -e "\nsend bytes before test:\c" > %s'%(logFilePath))
                atomic(mn.getNodeByName('h2').cmd)('cat /sys/class/net/h2_dummy/statistics/tx_bytes >> %s'%(logFilePath))
            else:
                atomic(mn.getNodeByName('h1').cmd)('echo -e "\nreceive bytes before test:\c" > %s'%(logFilePath))
                atomic(mn.getNodeByName('h1').cmd)('cat /sys/class/net/h1_gs1/statistics/rx_bytes >> %s'%(logFilePath))
                atomic(mn.getNodeByName('h1').cmd)('echo -e "\nreceive packets before test:\c" >> %s'%(logFilePath))
                atomic(mn.getNodeByName('h1').cmd)('cat /sys/class/net/h1_gs1/statistics/rx_packets >> %s'%(logFilePath))
        if useTCP:      #only support e2e TCP1
            atomic(mn.getNodeByName('h1').cmd)('iperf3 -s -f k -i 1 --logfile %s &'%logFilePath)
            time.sleep(1)
            atomic(mn.getNodeByName('h2').cmd)('iperf3 -c 10.0.1.1 -f k -C %s -t %d &'%(testParam.appParam.e2eCC,testParam.appParam.sendTime) )
        elif testParam.appParam.protocol=="udt":
            atomic(mn.getNodeByName('h2').cmd)('../../bbr/app/appserver 8765 >/dev/null 2>&1 &')
            time.sleep(1)
            atomic(mn.getNodeByName('h1').cmd)('../../bbr/app/appclient 10.0.100.2 8765 >> %s &'%(logFilePath) )
        else:
            atomic(mn.getNodeByName('h2').cmd)('../appLayer/intcpApp/intcps >/dev/null 2>&1 &')
            time.sleep(1)
            atomic(mn.getNodeByName('h1').cmd)('../appLayer/intcpApp/intcpc >> %s &'%logFilePath)
        #time.sleep(testParam.appParam.sendTime + 5)
        time.sleep(testParam.appParam.sendTime + 10)
        if testParam.appParam.test_type=="throughputWithTraffic":
            if not testParam.appParam.dynamic and 'dummy' in testParam.topoParam.nodes:
                atomic(mn.getNodeByName('h2').cmd)('echo -e "\nsend bytes after test:\c" >> %s'%(logFilePath))
                atomic(mn.getNodeByName('h2').cmd)('cat /sys/class/net/h2_dummy/statistics/tx_bytes >> %s'%(logFilePath))
            else:
                atomic(mn.getNodeByName('h1').cmd)('echo -e "\nreceive bytes after test:\c" >> %s'%(logFilePath))
                atomic(mn.getNodeByName('h1').cmd)('cat /sys/class/net/h1_gs1/statistics/rx_bytes >> %s'%(logFilePath))
                atomic(mn.getNodeByName('h1').cmd)('echo -e "\nreceive packets after test:\c" >> %s'%(logFilePath))
                atomic(mn.getNodeByName('h1').cmd)('cat /sys/class/net/h1_gs1/statistics/rx_packets >> %s'%(logFilePath))
        if testParam.appParam.sendRound>1:
            if useTCP:
                kill_pep_processes(mn,testParam)
            else:
                kill_intcp_processes(mn,testParam)
        time.sleep(1)
            
    return
        
#thread for test rtt
@threadFunc(True)
def OwdTest(mn, testParam, logPath):
    if not testParam.appParam.test_type=="owdTest":
        return
    logFilePath = '%s/%s.txt'%(logPath, testParam.name)
    senderLogFilePath = '%s/%s_%s.txt'%(logPath, testParam.name,"send")
    receiverLogFilePath = '%s/%s_%s.txt'%(logPath, testParam.name,"recv")
    clientLogFilePath = '%s/%s_%s.txt'%(logPath, testParam.name,"client")
    
    delFile(logFilePath)
    delFile(senderLogFilePath)
    delFile(receiverLogFilePath)
    
    #RttTestPacketNum = 1000
    #atomic(mn.getNodeByName('h2').cmd)('python ../tcp_test/server.py -c %d -rt %d > %s &'%(RttTestPacketNum,testParam.rttTotal,logFilePath))
    useTCP = testParam.appParam.get('protocol')=="TCP"
    start_midnode_processes(mn,testParam,logPath,useTCP,pep_nodelay=1)
                
    # h2 -> h1 for both TCP and INTCP test
    if useTCP:
        if False:   # transport layer owd, which can not support pep now
            atomic(mn.getNodeByName('h1').cmd)('python3 ./sniff.py --t > %s &'%(receiverLogFilePath))
            atomic(mn.getNodeByName('h2').cmd)('python3 ./sniff.py --t > %s &'%(senderLogFilePath))
            time.sleep(1)
            atomic(mn.getNodeByName('h1').cmd)('python3 ../appLayer/tcpApp/server.py >/dev/null 2>&1 &')
            atomic(mn.getNodeByName('h2').cmd)('python3 ../appLayer/tcpApp/client.py -l %f >/dev/null 2>&1 &'%(0))
        else:       # app layer owd
            atomic(mn.getNodeByName('h1').cmd)('python3 ../appLayer/tcpApp/server.py > %s &'%(logFilePath))
            atomic(mn.getNodeByName('h2').cmd)('python3 ../appLayer/tcpApp/client.py -l %f >/dev/null 2>&1 &'%(0))
    else:
        atomic(mn.getNodeByName('h2').cmd)('python3 ./sniff.py > %s &'%(senderLogFilePath))
        atomic(mn.getNodeByName('h1').cmd)('python3 ./sniff.py > %s &'%(receiverLogFilePath))
        time.sleep(1)
        atomic(mn.getNodeByName('h2').cmd)('../appLayer/intcpApp/intcps >/dev/null 2>&1 &')
        atomic(mn.getNodeByName('h1').cmd)('../appLayer/intcpApp/intcpc >/dev/null 2>&1 &')
    #atomic(mn.getNodeByName('h1').cmd)('../appLayer/intcpApp/intcpc > %s &'%(clientLogFilePath))
    time.sleep(testParam.appParam.sendTime + 5)
    return

@threadFunc(True)
def TrafficTest(mn, testParam, logPath):
    if not testParam.appParam.test_type=="trafficTest":
        return
    logFilePath = '%s/%s.txt'%(logPath, testParam.name)
    delFile(logFilePath)
    useTCP = testParam.appParam.get('protocol')=="TCP"
    start_midnode_processes(mn,testParam,logPath,useTCP,pep_nodelay=1)
    data_size = testParam.appParam.data_size
    atomic(mn.getNodeByName('h2').cmd)('cat /sys/class/net/h2_dummy/statistics/tx_bytes > %s'%(logFilePath))
    if useTCP:
        atomic(mn.getNodeByName('h1').cmd)('python3 ../appLayer/tcpApp/server.py >/dev/null 2>&1 &')
        atomic(mn.getNodeByName('h2').cmd)('python3 ../appLayer/tcpApp/client.py -f %f >/dev/null 2>&1 &'%(data_size))
    else:
        atomic(mn.getNodeByName('h2').cmd)('../appLayer/intcpApp/intcps >/dev/null 2>&1 &')
        atomic(mn.getNodeByName('h1').cmd)('../appLayer/intcpApp/intcpc >/dev/null 2>&1 &') 
    time.sleep(testParam.appParam.sendTime)
    atomic(mn.getNodeByName('h2').cmd)('cat /sys/class/net/h2_dummy/statistics/tx_bytes >> %s'%(logFilePath))
    return
'''
@threadFunc(True)
def ThrpWithOwdTest(mn, testParam, logPath):
    if not testParam.appParam.test_type in ["owdThroughputBalance","throughputWithOwd"]:
        return
    logFilePath = '%s/%s.txt'%(logPath, testParam.name)
    thrpLogFilePath = '%s/%s_%s.txt'%(logPath, testParam.name,"thrp")
    senderLogFilePath = '%s/%s_%s.txt'%(logPath, testParam.name,"send")
    receiverLogFilePath = '%s/%s_%s.txt'%(logPath, testParam.name,"recv")

    delFile(logFilePath)
    delFile(thrpLogFilePath)
    delFile(senderLogFilePath)
    delFile(receiverLogFilePath)

    useTCP = testParam.appParam.get('protocol')=="TCP"
    start_midnode_processes(mn,testParam,logPath,useTCP,pep_nodelay=1)
    
    # discard: owdThrpBalance -l 100000
    
    atomic(mn.getNodeByName('h2').cmd)('python3 ./sniff.py -t %d -i %s > %s &'%(useTCP,"h2_gs2",senderLogFilePath))
    atomic(mn.getNodeByName('h1').cmd)('python3 ./sniff.py -t %d -i %s > %s &'%(useTCP,"h1_gs1",receiverLogFilePath))
    #atomic(mn.getNodeByName('gs2').cmd)('python3 ./sniff.py -t %d -i %s > %s &'%(useTCP,"gs2_h2",senderLogFilePath))
    #atomic(mn.getNodeByName('gs2').cmd)('python3 ./sniff.py -t %d -i %s > %s &'%(useTCP,"gs2_m1",receiverLogFilePath))

    time.sleep(1)

    if useTCP:
        atomic(mn.getNodeByName('h1').cmd)('iperf3 -s -f k -i 1 --logfile %s &'%(thrpLogFilePath))
        time.sleep(1)
        atomic(mn.getNodeByName('h2').cmd)('iperf3 -c 10.0.1.1 -f k -C %s -t %d &'%(testParam.appParam.e2eCC,testParam.appParam.sendTime) )
    else:
        atomic(mn.getNodeByName('h2').cmd)('../appLayer/intcpApp/intcps >/dev/null 2>&1 &')
        #atomic(mn.getNodeByName('h2').cmd)('../appLayer/intcpApp/intcps > %s/%s_%s &'%(logPath,testParam.name,"h2"))
        time.sleep(1)
        atomic(mn.getNodeByName('h1').cmd)('../appLayer/intcpApp/intcpc > %s &'%(thrpLogFilePath))

    time.sleep(testParam.appParam.sendTime+5)
    return
'''

@threadFunc(True)
def ThrpWithOwdTest(mn, testParam, logPath):
    if not testParam.appParam.test_type in ["owdThroughputBalance","throughputWithOwd","all"]:
        return
    logFilePath = '%s/%s.txt'%(logPath, testParam.name)
    thrpLogFilePath = '%s/%s_%s.txt'%(logPath, testParam.name,"thrp")
    senderSummaryFilePath = '%s/%s_%s.txt'%(logPath, testParam.name,"sendSummary")
    senderLogFilePath = '%s/%s_%s.txt'%(logPath, testParam.name,"send")     #per packet
    receiverLogFilePath = '%s/%s_%s.txt'%(logPath, testParam.name,"recv")   #per packet

    delFile(logFilePath)
    delFile(thrpLogFilePath)
    delFile(senderLogFilePath)
    delFile(receiverLogFilePath)
    delFile(senderSummaryFilePath)
    
    useTCP = testParam.appParam.get('protocol')=="TCP"
    
    start_midnode_processes(mn,testParam,logPath,useTCP,pep_nodelay=1)
    
    # discard: owdThrpBalance -l 100000
    # -i can specific a interface
    if not useTCP:
        mode = 0
    elif testParam.appParam.midCC=="nopep":
        mode =1
    else:
        mode =2

    atomic(mn.getNodeByName('h2').cmd)('python3 ./sniff.py -t %d  > %s &'%(mode,senderLogFilePath))
    atomic(mn.getNodeByName('h1').cmd)('python3 ./sniff.py -t %d  > %s &'%(mode,receiverLogFilePath))
    #atomic(mn.getNodeByName('h2').cmd)('python3 ./sniff.py -t %d -i %s > %s &'%(useTCP,"h2_gs2",senderLogFilePath))
    #atomic(mn.getNodeByName('h1').cmd)('python3 ./sniff.py -t %d -i %s > %s &'%(useTCP,"h1_gs1",receiverLogFilePath))
    

    time.sleep(1)

    if useTCP:
        if testParam.appParam.midCC=="nopep":#testParam.appParam.midCC=="nopep"
            atomic(mn.getNodeByName('h1').cmd)('iperf3 -s -f k -i 1 --logfile %s &'%(thrpLogFilePath))
            time.sleep(1)
            #atomic(mn.getNodeByName('h2').cmd)('iperf3 -c 10.0.1.1 -f k -C %s -t %d &'%(testParam.appParam.e2eCC,testParam.appParam.sendTime) )
            atomic(mn.getNodeByName('h2').cmd)('iperf3 -c 10.0.1.1 -f k -C %s -t %d --logfile %s &'%(testParam.appParam.e2eCC,testParam.appParam.sendTime,senderSummaryFilePath) )
        else:
            atomic(mn.getNodeByName('h1').cmd)('python3 ../appLayer/tcpApp/server.py > %s &'%(thrpLogFilePath))
            time.sleep(1)
            atomic(mn.getNodeByName('h2').cmd)('python3 ../appLayer/tcpApp/client.py -C %s -f 1 >/dev/null 2>&1 &'%(testParam.appParam.e2eCC,))
    else:
        atomic(mn.getNodeByName('h2').cmd)('../appLayer/intcpApp/intcps >/dev/null 2>&1 &')
        time.sleep(1)
        atomic(mn.getNodeByName('h1').cmd)('../appLayer/intcpApp/intcpc > %s &'%(thrpLogFilePath))

    time.sleep(testParam.appParam.sendTime+5)
    return

@threadFunc(True)
def FairnessTest(mn,testParam,logPath):
    if not testParam.appParam.test_type=="fairnessTest":
        return
    flowNum = testParam.appParam.flowNum
    flowIntv = testParam.appParam.flowIntv
    singlePath = testParam.appParam.singlePath
    logFilePathes = []
    for i in range(flowNum):
        logFilePath = '%s/%s_%d.txt'%(logPath, testParam.name,i+1)
        logFilePathes.append(logFilePath)
        delFile(logFilePath)
        
    useTCP = testParam.appParam.get('protocol')=="TCP"
    start_midnode_processes(mn,testParam,logPath,useTCP,pep_nodelay=1)
    if singlePath:  # h1
        if useTCP:
            for i in range(flowNum):
                atomic(mn.getNodeByName('h1').cmd)('iperf3 -s -f k -i 1 -p %d --logfile %s &'%(5201+i,logFilePathes[i]))
            time.sleep(1)
            for i in range(flowNum):
                atomic(mn.getNodeByName('h2').cmd)('iperf3 -c 10.0.1.1 -f k -C %s -t %d -p %d &'%(testParam.appParam.e2eCC,testParam.appParam.sendTime,5201+i) )
                time.sleep(flowIntv-1)
        else:
            atomic(mn.getNodeByName('h2').cmd)('../appLayer/intcpApp/intcps >/dev/null 2>&1 &')
            time.sleep(1)
            for i in range(flowNum):
                atomic(mn.getNodeByName('h1').cmd)('../appLayer/intcpApp/intcpc > %s &'%(logFilePathes[i]))
                time.sleep(flowIntv-1)
        time.sleep(testParam.appParam.sendTime-flowIntv+5)
    else:
        pass

@threadFunc(True)
def cpuTest(mn,testParam,logPath):
    if not testParam.appParam.test_type=="cpuTest":
        return
    
    logFilePath = '%s/%s.txt'%(logPath, testParam.name)
    delFile(logFilePath)
        
    useTCP = testParam.appParam.get('protocol')=="TCP"
    if useTCP:
        return
    start_midnode_processes(mn,testParam,logPath,useTCP,pep_nodelay=1)
    time.sleep(1)
    atomic(mn.getNodeByName('h2').cmd)('../appLayer/intcpApp/intcps >/dev/null 2>&1 &')
    time.sleep(1)
    atomic(mn.getNodeByName('h1').cmd)('../appLayer/intcpApp/intcpc >/dev/null 2>&1 &')
    time.sleep(testParam.appParam.sendTime+5)
    return
'''
@threadFunc(True)
def DynamicTrafficTest(mn, testParam, logPath):
    if not testParam.appParam.test_type=="dynamicTrafficTest":
        return
    logFilePath = '%s/%s_%s.txt'%(logPath, testParam.name,"traffic")
    delFile(logFilePath)
    useTCP = testParam.appParam.get('protocol')=="TCP"
    start_midnode_processes(mn,testParam,useTCP,pep_nodelay=1)
    data_size = testParam.appParam.data_size
    atomic(mn.getNodeByName('h2').cmd)('cat /sys/class/net/h2_dummy/statistics/tx_bytes > %s'%(logFilePath))
    if useTCP:
        atomic(mn.getNodeByName('h1').cmd)('python3 ../appLayer/tcpApp/server.py >/dev/null 2>&1 &')
        atomic(mn.getNodeByName('h2').cmd)('python3 ../appLayer/tcpApp/client.py -f %f >/dev/null 2>&1 &'%(data_size))
    else:
        atomic(mn.getNodeByName('h2').cmd)('../appLayer/intcpApp/intcps >/dev/null 2>&1 &')
        atomic(mn.getNodeByName('h1').cmd)('../appLayer/intcpApp/intcpc >/dev/null 2>&1 &') 
    time.sleep(testParam.appParam.sendTime)
    atomic(mn.getNodeByName('h2').cmd)('cat /sys/class/net/h2_dummy/statistics/tx_bytes >> %s'%(logFilePath))
    return
'''
