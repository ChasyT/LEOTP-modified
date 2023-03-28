import time
import random
import math

from mininet.log import info

from .TbThread import threadFunc, atomic, sleepWithCaution, latchRunning
from . import Param
from .RealNetwork import setRoute, clearRoute, splitLoss

### thread for dynamic link params control
#TODO K for each link? or independent thread for each link?
K = 0
def generateBw(policy, meanbw,varbw, prd=10):
    if policy=='random':
        new_bw = random.uniform(meanbw-varbw,meanbw+varbw)
        return new_bw
    elif policy=='sin':
        cur_time = time.time()
        return meanbw+varbw*math.sin(2*math.pi*cur_time/prd)
    elif policy == 'square':
        global K
        K = -1*K
        newBw = meanbw + varbw * K
        return newBw
    else:
        raise Exception
    
#TODO make sure that the dynamic network params configuring wil not impact the value of other unchanged params 
def changeLinkConfig(intf,bw=None,delay=None,loss=None):
    cmds = []
   
    #TODO add rtt and loss
    if delay or loss:
        dlcmds, parent = atomic(intf.delayCmds)(is_change=True,delay='%fms'%delay,loss=loss)
        cmds += dlcmds
    if bw:
        bwcmds, parent = atomic(intf.bwCmds)(is_change=True,bw=bw)
        cmds += bwcmds
    for cmd in cmds:
        atomic(intf.tc)(cmd)


@threadFunc(False)
def LinkUpdate(mn, testParam, logPath):
    if testParam.appParam.dynamic:
        return
    global K
    K = 1
    linkNames = []
    sleeptime = 0
    for ln in testParam.topoParam.linkNames():
        if testParam.linksParam.getLP(ln).varBw>0:
            linkNames.append(ln)
            sleeptime = testParam.linksParam.getLP(ln).varIntv#TODO
    if linkNames == []:
        return
    while latchRunning():
        for linkName in linkNames:
            nameA,nameB = linkName.split(Param.LinkNameSep)
            nodeA = mn.getNodeByName(nameA)
            switch = mn.getNodeByName(linkName)
            nodeB = mn.getNodeByName(nameB)
            # if testParam.linkParams[linkName].varMethod in ['squareHighPulse', 'squareLowPulse']:
            #     # newBw = generateBw('random',testParam.bw,testParam.varBw)
            #     newBw = generateBw('square', testParam.linkParams[linkName].bw, testParam.linkParams[linkName].varBw)
            #     for intf in (s2.connectionsTo(pep)[0] + s2.connectionsTo(h2)[0]):
            #         config(intf, bw=newBw)
            #     if testParam.linkParams['pep_h2'].varMethod == 'squareHighPulse':
            #         TbThread.sleep(5)
            #     else:
            #         TbThread.sleep(testParam.linkParams['pep_h2'].varIntv)

            #     # newBw = generateBw('random',testParam.bw,testParam.varBw)
            #     newBw = generateBw('square', testParam.linkParams['pep_h2'].bw, testParam.linkParams['pep-h2'].varBw)
            #     for intf in (s2.connectionsTo(pep)[0] + s2.connectionsTo(h2)[0]):
            #         config(intf, bw=newBw)
            #     if testParam.linkParams['pep_h2'].varMethod == 'squareHighPulse':
            #         TbThread.sleep(testParam.linkParams['pep_h2'].varIntv)
            #     else:
            #         TbThread.sleep(5)
            # else:
            lp = testParam.linksParam.getLP(linkName)
            newBw = generateBw(lp.varMethod, lp.bw, lp.varBw)

            for intf in (nodeA.connectionsTo(switch)[0]+
                    nodeB.connectionsTo(switch)[0]):
                changeLinkConfig(intf,bw=newBw)
        # linkName is the name of last link in linkNames
         #TODO what if the links have different varIntv
        #sleepWithCaution(testParam.linksParam.defaultLP.varIntv)
        sleepWithCaution(sleeptime)



@threadFunc(False)
def DynamicLinkUpdate(mn,testParam,logPath):
    if not testParam.appParam.dynamic:
        return
    __,__,isls,links_params = testParam.topoParam
    prev_topo = links_params[0]["topo"]
    while True:    
        for links_param in links_params:
            topo = links_param["topo"]
            rtts = links_param["rtt"]
            #print(rtts)
            losses = links_param["loss"]
            #print(losses)
            bws = links_param["bw"]

            #set link config
            nodes = ['h1','gs1']+['m%d'%(topo[i]) for i in range(len(topo))] + ['gs2','h2']
            
            for i in range(len(nodes)-1):
                nameA = nodes[i]
                nameB = nodes[i+1]
                name_switch = nameA + Param.LinkNameSep + nameB
                if i>1 and i<len(nodes)-3:
                    if (topo[i-2],topo[i-1]) not in isls:
                        name_switch = nameB + Param.LinkNameSep + nameA
                nodeA = mn.getNodeByName(nameA)
                nodeB = mn.getNodeByName(nameB)
                switch = mn.getNodeByName(name_switch)
                loss = splitLoss(losses[i],2)
                
                for intf in (nodeA.connectionsTo(switch)[0]+
                        (switch.connectionsTo(nodeB)[0][0],)):
                    changeLinkConfig(intf,bw=bws[i],delay=rtts[i]/4,loss=0)
                for intf in (nodeB.connectionsTo(switch)[0][0],):
                    changeLinkConfig(intf,bw=bws[i],delay=rtts[i]/4,loss=losses[i])
                
                '''
                for intf in (nodeA.connectionsTo(switch)[0]+
                             switch.connectionsTo(nodeA)[0]+
                             nodeB.connectionsTo(switch)[0]+
                             switch.connectionsTo(nodeB)[0]):
                        changeLinkConfig(intf,bw=bws[i],delay=rtts[i]/4,loss=loss)
                '''
               
                '''
                for intf in (nodeA.connectionsTo(switch)[0][0],nodeB.connectionsTo(switch)[0][1],nodeA.connectionsTo(switch)[0][1]):
                    changeLinkConfig(intf,bw=bws[i],delay=rtts[i]/4,loss=0)
                for intf in (nodeB.connectionsTo(switch)[0][0],):
                    changeLinkConfig(intf,bw=bws[i],delay=rtts[i]/4,loss=losses[i])
                '''
            #set route
            #print(topo)
            if topo!= prev_topo:
                clearRoute(mn,isls,prev_topo)
                setRoute(mn,isls,topo)
            prev_topo = topo

            #done for this loop
            sleepWithCaution(testParam.appParam.dynamic_intv)
            #sleepWithCaution(120)

def routeReset(mn,testParam):
    nodes = testParam.topoParam.nodes
    for i in range(len(nodes)-1):
        if i == len(nodes)-2:
            seg = 100
        else:
            seg = i+1
        mn.getNodeByName(nodes[i]).cmd('route add default gw 10.0.%d.2'%seg)
    mn.getNodeByName(nodes[-1]).cmd('route add default gw 10.0.%d.1'%100)
    for i in range(2,len(nodes)-1):
        for seg in range(1,i):
            mn.getNodeByName(nodes[i]).cmd(
                    'route add -net 10.0.%d.0 netmask 255.255.255.0 gw 10.0.%d.1'%(seg,i))

@threadFunc(False)
def MakeItm(mn, testParam, logPath):
    if testParam.appParam.dynamic:
        return
    linkNames = []
    for ln in testParam.topoParam.linkNames():
        if testParam.linksParam.getLP(ln).itmDown>0:
            linkNames.append(ln)
    if linkNames == []:
        return
    
    #TODO what if the links have different itmTotal/itmDown
    anyLP = testParam.linksParam.getLP(linkNames[-1])
    while latchRunning():        
        sleepWithCaution(anyLP.itmTotal-anyLP.itmDown)
        #print(anyLP.itmTotal-anyLP.itmDown)
        #print("down")
        for l in linkNames:
            nameA,nameB = l.split(Param.LinkNameSep)
            #print(nameA,nameB,l)
            atomic(mn.getNodeByName(nameA).cmd)('echo')
            atomic(mn.configLinkStatus)(nameA,l,'down')
            atomic(mn.getNodeByName(nameB).cmd)('echo')
            atomic(mn.configLinkStatus)(nameB,l,'down')
        sleepWithCaution(anyLP.itmDown)
        #print(anyLP.itmDown)
        #print("up")
        for l in linkNames:
            nameA,nameB = l.split(Param.LinkNameSep)
            atomic(mn.getNodeByName(nameA).cmd)('echo')
            atomic(mn.configLinkStatus)(nameA,l,'up')
            atomic(mn.getNodeByName(nameB).cmd)('echo')
            atomic(mn.configLinkStatus)(nameB,l,'up')
        
        routeReset(mn,testParam)
        mn.ping([mn['h1'],mn['h2']],outputer=info)
        # for linkName in linkNames:
        #     nameA,nameB = linkName.split(Param.LinkNameSep)
        #     nodeA = mn.getNodeByName(nameA)
        #     switch = mn.getNodeByName(linkName)
        #     nodeB = mn.getNodeByName(nameB)
        #     lp = testParam.linksParam.getLP(linkName)
        #     for intf in (nodeA.connectionsTo(switch)[0]+
        #             nodeB.connectionsTo(switch)[0]):
        #         changeLinkConfig(intf,bw=lp.bw,delay=lp.rtt/4,loss=splitLoss(lp.loss,2))
            
            # if changing s2 - h2
            # mn.getNodeByName('h2').cmd('route add default gw 10.0.2.90 &')
