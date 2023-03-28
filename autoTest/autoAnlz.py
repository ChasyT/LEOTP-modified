#!/usr/bin/python3

#BUG
#import matplotlib
import matplotlib.font_manager as font_manager

#font_manager._rebuild()
#footpath='/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf'
#prop=font_manager.FontProperties(fname=footpath)
#matplotlib.rcParams['font.family']=prop.get_name()
#for font in font_manager.FontManager.ttflist:
#    print(font)
#font_manager.findfont('Times New Roman')

import time
import matplotlib.pyplot as plt
import os
import sys
import functools
import argparse
import seaborn as sns
import numpy as np 
from scipy.stats import scoreatpercentile
import statsmodels.api as sm
from get_trace import get_city_distance

sys.path.append(os.path.dirname(os.sys.path[0]))
from FileUtils import createFolder, fixOwnership, writeText
import MyParam


plt.rc('font',family='Times New Roman')
tick_size = 20
label_size = 24
legend_size = 24
line_width = 2.5
marker_size = 10

# for all graph
borderpad = 0.1
labelspacing = 0
borderaxespad = 0.05

# for cdf,plot and seq
handletextpad = 0.5
handlelength = 1.5

# plt.rcParams['font.sans-serif'] = 'Times New Roman'


def timestamp():
    return time.strftime('%m-%d-%H-%M-%S', time.localtime())

def mean(values, method='all'):
    if method=='all':
        return sum(values)/len(values)
    elif method == 'noMaxMin':
        if len(values)<=2:
            raise Exception('the amount of data is too small.')
        else:
 
            del values[values.index(max(values))]
            del values[values.index(min(values))]
            return sum(values)/len(values)
    elif method == "median":
        rm = int((len(values)-1)/2)
        for i in range(rm):
            del values[values.index(max(values))]
            del values[values.index(min(values))]
        return sum(values)/len(values)

def getOwdTotal(tp):
    rttTotal = 0
    rttMin = 999999
    for ln in tp.topoParam.linkNames():
        lp = tp.linksParam.getLP(ln)
        rttTotal += lp.rtt
        rttMin = min(rttMin,lp.rtt)
    owdTotal = rttTotal*0.5
    first_hop_rtt = tp.linksParam.getLP(tp.topoParam.linkNames()[0]).rtt
    last_hop_rtt = tp.linksParam.getLP(tp.topoParam.linkNames()[-1]).rtt
    if tp.appParam.protocol=="INTCP" and not tp.appParam.midCC=="nopep":    # hop INTCP 
        retranThreshold = rttTotal*0.5 + rttMin
    elif tp.appParam.protocol=="TCP" and not tp.appParam.midCC=="nopep":    # split tcp
        #retranThreshold = rttTotal*0.5 + min(first_hop_rtt,last_hop_rtt,rttTotal-first_hop_rtt-last_hop_rtt)
        retranThreshold = rttTotal*0.5 +(rttTotal-first_hop_rtt-last_hop_rtt)
    else:
        retranThreshold = rttTotal*1.5
    return owdTotal,retranThreshold
    
def getTCDelay(tp):
    #sender = "h1" if tp.appParam.protocol=="TCP" else "h2"
    if not tp.appParam.dynamic:
        sender = "h2"
        for linkName in tp.topoParam.linkNames():
            if sender in linkName:
                return tp.linksParam.getLP(linkName).rtt/4
        raise Exception("sender link not found")
    else:
        return tp.appParam.dynamic_ground_link_rtt/4

def parseLine(line,protocol):
    if protocol=="TCP":
        p1 = line.find("length")
        p2 = line.find("time")
        seq = int(line[4:p1-1])
        length = int(line[p1+7:p2-1])
        time = float(line[p2+5:])
        return seq,length,time
    elif protocol=="INTCP":
        p1 = line.find("rangeStart")
        p3 = line.find("time")
        if "rangeEnd" in line:
            p2 = line.find("rangeEnd")
        else:
            p2 = p3
        rs = int(line[p1+11:p2-1])
        re = int(line[p2+9:p3-1])
        time = float(line[p3+5:])
        return rs,re-rs,time
        
def generateLog(logPath,tpSet):
    for tp in tpSet.testParams:
        if tp.appParam.protocol == "TCP" and tp.appParam.test_type == "owdTest":   # record app layer owd for tcp
            continue
        if tp.appParam.protocol == "TCP" and tp.appParam.test_type == "owdThroughputBalance" and tp.appParam.sendq_length!=0:
            continue
        if tp.appParam.protocol == "INTCP" and tp.appParam.test_type == "owdThroughputBalance" and tp.appParam.sendq_length==0:
            continue
        senderLogFilePath = '%s/%s_%s.txt'%(logPath,tp.name,"send")
        receiverLogFilePath = '%s/%s_%s.txt'%(logPath,tp.name,"recv")
        logFilePath = '%s/%s.txt'%(logPath,tp.name)
        sendTimeDict = {}
        recvTimeDict = {}
        owdDict = {}
        tcDelay = getTCDelay(tp)
        repeated_packets =  0
        #load sender
        with open(senderLogFilePath,"r") as f:
            lines = f.readlines()
            for idx,line in enumerate(lines):
                #if tp.appParam.dynamic and idx<1000:    #no order
                #    continue
                try:
                    if "time" in line:
                        seq,__,time = parseLine(line,tp.appParam.protocol)
                        if not seq in sendTimeDict.keys():
                            sendTimeDict[seq] = time
                except:
                    continue
                    
        #load receiver
        with open(receiverLogFilePath,"r") as f:
            lines = f.readlines()
            for line in lines:
                try:
                    if "time" in line:
                        seq,__,time = parseLine(line,tp.appParam.protocol)
                        if not seq in recvTimeDict.keys():
                            recvTimeDict[seq] = time
                        else:
                            #print("repeated receive",seq)
                            repeated_packets+=1
                except:
                    continue
                    
        for seq in sendTimeDict.keys():
            if seq in recvTimeDict.keys():
                owd_s = recvTimeDict[seq]-sendTimeDict[seq]
                if owd_s > -10 and owd_s <0:    # abnormal owd
                    continue
                if owd_s < 0: # only occur when recvtime exceed 1000
                    owd_s = owd_s + 1000
                owdDict[seq] = 1000*owd_s + tcDelay
            else:
                a = 1
                #print(seq,end=',')  
        #print("\n----%s------"%(tp.name))
        #print("repeated packets",repeated_packets)
        with open(logFilePath,"w") as f:
            for seq,owd in owdDict.items():
                f.write("seq %d owd_obs %f\n"%(seq,owd)) 
        #print(sendTimeDict.keys())
        #print(recvTimeDict.keys())

def screen_owd(thrps,retranPacketOnly,owd_total,retran_threshold):
    res = []
    if not retranPacketOnly:
        for owd in thrps:
            if owd > owd_total-2:
                res.append(owd)
    else:   # only retran packet
        if False:    #tp.appParam.protocol=="INTCP"
            for owd in thrps:
                if owd > retran_threshold:
                    res.append(owd)
        else:
            prev_owd = 0
            for owd in thrps:
                if owd > retran_threshold and owd > prev_owd:
                    res.append(owd)
                prev_owd = owd
    return res

# return a list
def loadOwd(filePath):
    owds = []
    with open(filePath,'r') as f:
        lines = f.readlines()
        for line in lines:
            if "owd_obs" in line:
                pos_obs = line.find("owd_obs")
                try:
                    owd = float(line[pos_obs+8:])
                    owds.append(owd)
                except:
                    continue
    return owds

def thrpAggr(thrps,interval):
    res = []
    start = 0
    end = 0
    while start<len(thrps):
        end = start+interval
        if end>len(thrps):
            end = len(thrps)
        sum = 0
        for i in range(start,end):
            sum += thrps[i]
        sum /= (end-start)
        res.append(sum)
        start = end
    return res

#return a list
def loadThrp(filePath):
    thrps = []
    traffic_before_send = 0
    traffic_after_send = 0
    with open(filePath,'r') as f:
        lines = f.readlines()
        for line in lines:
            #if 'bits/sec' in line and not ('receiver' in line and '0.00-' in line): #and 'receiver' not in line:
            if 'bits/sec' in line and 'receiver' in line:
                numString = line.split('bits/sec')[0][-7:-2]
                num = float(numString)/(1 if line.split('bits/sec')[0][-1]=='M' else 1000)
                thrps.append(num)
                #print(num)
            if 'bytes before test' in line:
                pos = line.find(":")
                traffic_before_send = float(line[pos+2:])
            if 'bytes after test' in line:
                pos = line.find(":")
                traffic_after_send = float(line[pos+2:])
    #thrps = thrpAggr(thrps,30)
    return thrps,traffic_before_send,traffic_after_send

#return a list
def loadINTCPLoss(filePath):
    loss = []
    rangeStarts = []
    rangeStartMax = 0
    with open(filePath,'r') as f:
        lines = f.readlines()
        for line in lines:
            #if 'bits/sec' in line and not ('receiver' in line and '0.00-' in line): #and 'receiver' not in line:
            if 'rangeStart' in line and 'rangeEnd' in line:
                pos1 = line.find("rangeStart")
                pos2 = line.find("rangeEnd")
                rs = int(line[pos1+11:pos2-1])
                rangeStarts.append(rs)
        pl = 0
        for i,rs in enumerate(rangeStarts):
            if i>=1 and rangeStarts[i]<rangeStartMax:
                pl += 1
            rangeStartMax = max(rangeStartMax, rangeStarts[i])
        loss.append(100*pl/len(lines))
    return loss

def loadCpu(filePath):
    cpu = []
    with open(filePath,'r') as f:
        lines = f.readlines()
        cnt = 0
        for line in lines:
            #if 'bits/sec' in line and not ('receiver' in line and '0.00-' in line): #and 'receiver' not in line:
            if 'udp_recv_time' in line and 'input_time' in line:
                #print('fuck')
                try:
                    pos1 = line.find('udp_recv_time')
                    pos2 = line.find('update_time')
                    pos3 = line.find('input_time')
                    #print(pos1, pos2,pos3)
                    #print(line[pos1+14:pos2-2],line[pos2+12:pos3-2],line[pos3+11:-2])
                    wait = float(line[pos1+14:pos2-2])
                    update = float(line[pos2+12:pos3-2])
                    input = float(line[pos3+11:-2])
                    #print(wait,update,input)
                    #print((input+update)/(input+update+wait))
                    cnt += 1
                    cpu.append((input+update)/cnt)
                except:
                    continue
        #print(cpu)
        cpu = [100*cpu[-1]]
    return cpu

def loadTCPLoss(filePath):
    if False:
        loss = []
        with open(filePath,'r') as f:
            lines = f.readlines()
            for line in lines:
                #if 'bits/sec' in line and not ('receiver' in line and '0.00-' in line): #and 'receiver' not in line:
                if 'bits/sec' in line and 'sender' in line:
                    pos1 = line.find(" sec")
                    pos2 = line.find("Bytes")
                    pos3 = line.find("/sec")
                    pos4 = line.find("sender")
                    total = float(line[pos1+6:pos2-2])//(1 if line.split('Bytes')[0][-1]=='M' else 1000)
                    retran = float(line[pos3+6:pos4].strip())
                    print(total, retran)
                    loss = [100*retran*1448/(total*1000000)]
    else:
        loss = []
        seqs = []
        seqMax = 0
        data_start = False
        with open(filePath,'r') as f:
            lines = f.readlines()
            for line in lines:
                #if 'bits/sec' in line and not ('receiver' in line and '0.00-' in line): #and 'receiver' not in line:
                if 'seq' in line and 'length' in line and 'time' in line:
                    pos1 = line.find("seq")
                    pos2 = line.find("length")
                    pos3 = line.find("time")
                    seq = int(line[pos1+4:pos2-1])
                    length = int(line[pos2+7:pos3-1])
                    if length==0 or (data_start==False and length<1448):
                        continue
                    else:
                        seqs.append(seq)
                        data_start = True
            pl = 0
            for i,seq in enumerate(seqs):
                if i>=1 and seq<seqMax:
                    pl += 1
                seqMax = max(seqMax, seq)
            loss.append(100*pl/len(lines))
    return loss

def loadLinkLayerThrp(filePath):
    prev_ts = -1
    seqs = {}
    thrps = []
    current_thrp_bytes = 0
    with open(filePath,'r') as f:
        lines = f.readlines()
        for line in lines:
            try:
                seq,length,time = parseLine(line,"TCP")
                if prev_ts == -1:
                    prev_ts = time
                if seq not in seqs.keys():     #ignore repeated packets
                    seqs[seq] = 1
                    if time>prev_ts+1 or (prev_ts+1>1000 and time<prev_ts and time+1000>prev_ts+1):# or (prev_ts+1>1000 and time+1000>prev_ts+1):
                        thrps.append(float(current_thrp_bytes)*8/1000000)
                        #print(time,float(current_thrp_bytes)*8/1000000)
                        current_thrp_bytes = 0
                        prev_ts = time
                        
                    current_thrp_bytes += length
            except:
                continue
    #print(thrps)
    return thrps

def loadLog(logPath, tpSet, isDetail=False,retranPacketOnly=False,metric="thrp"):
    result = {}
    for tp in tpSet.testParams:
        print('-----\n'+tp.name)
        logFilePath = '%s/%s.txt'%(logPath,tp.name)
        #print(tp.name)
        thrps = []
        result[tp] = thrps
        if tp.appParam.test_type=="throughputTest":
            thrps , __ , __ = loadThrp(logFilePath)

        elif tp.appParam.test_type=="throughputWithTraffic":
            thrps , traffic_before_send , traffic_after_send = loadThrp(logFilePath)
            if tp.appParam.protocol=="INTCP":
                intf_thrp = (traffic_after_send-traffic_before_send)*8/(1024*1024*(tp.appParam.sendTime+5))
            else:
                intf_thrp = (traffic_after_send-traffic_before_send)*8/(1024*1024*(tp.appParam.sendTime))
            thrps = [mean(thrps,method='all'),intf_thrp]
            print(thrps)

        elif tp.appParam.test_type=="trafficTest":
            with open(logFilePath,'r') as f:
                lines = f.readlines()
                for idx,line in enumerate(lines):
                    if idx==0:
                        flow1 = float(line)
                    elif idx==1:
                        flow2 = float(line)
                        thrps.append((flow2-flow1)/1000000)

        elif tp.appParam.test_type=="owdTest":
            owd_total,retran_threshold = getOwdTotal(tp)
            owds = loadOwd(logFilePath)
            thrps = screen_owd(owds,retranPacketOnly,owd_total,retran_threshold)

        elif tp.appParam.test_type=="owdThroughputBalance":
            if tp.appParam.protocol=="TCP" and not tp.appParam.sendq_length==0:
                continue
            if tp.appParam.protocol=="INTCP" and tp.appParam.sendq_length==0:
                continue

            owds = loadOwd(logFilePath)
            #owd_total,retran_threshold = getOwdTotal(tp)
            #owds = screen_owd(owds,False,owd_total,retran_threshold)

            thrpLogFilePath = '%s/%s_%s.txt'%(logPath,tp.name,"thrp")
            if tp.appParam.protocol=="INTCP":
                thrps,__,__ = loadThrp(thrpLogFilePath)
            else:
                thrpLogFilePath = '%s/%s_%s.txt'%(logPath,tp.name,"recv")
                thrps = loadLinkLayerThrp(thrpLogFilePath)

            thrps = [mean(owds,method='all'),mean(thrps,method='all')]
            print(thrps)

        elif tp.appParam.test_type=="cpuTest":
            logFilePath = '%s/%s.txt'%(logPath, tp.name)
            thrps = loadCpu(logFilePath)
            
        elif tp.appParam.test_type=="throughputWithOwd":
            logFilePath = '%s/%s.txt'%(logPath, tp.name)
            thrpLogFilePath = '%s/%s_%s.txt'%(logPath, tp.name,"thrp")
            senderSummaryFilePath = '%s/%s_%s.txt'%(logPath, tp.name,"sendSummary")
            senderLogFilePath = '%s/%s_%s.txt'%(logPath, tp.name,"send")     #per packet
            receiverLogFilePath = '%s/%s_%s.txt'%(logPath, tp.name,"recv")   #per packet
            if metric=="thrp":
                if tp.appParam.protocol=="INTCP": #tp.appParam.protocol=="INTCP"
                    #thrpLogFilePath = '%s/%s_%s.txt'%(logPath,tp.name,"thrp")
                    thrps,__,__ = loadThrp(thrpLogFilePath)
                else:
                   thrpLogFilePath = '%s/%s_%s.txt'%(logPath,tp.name,"recv")
                   thrps = loadLinkLayerThrp(thrpLogFilePath)
                #thrps = thrps[5:]
            elif metric=="owd":
                thrps = loadOwd(logFilePath)
                #print(max(thrps),min(thrps))
                #print(scoreatpercentile(thrps,10),scoreatpercentile(thrps,90))
                #owd_total,retran_threshold = getOwdTotal(tp)
                #thrps = screen_owd(thrps,False,owd_total,retran_threshold)
            elif metric=="loss":
                if tp.appParam.protocol=="TCP":
                    #thrps = loadTCPLoss(senderSummaryFilePath)
                    thrps = loadTCPLoss(senderLogFilePath)
                else:
                    thrps = loadINTCPLoss(receiverLogFilePath)

        elif tp.appParam.test_type=="fairnessTest":
            for i in range(tp.appParam.flowNum):
                thrpLogFilePath = '%s/%s_%d.txt'%(logPath,tp.name,i+1)
                total_len = tp.appParam.sendTime + tp.appParam.flowIntv*(tp.appParam.flowNum-1)
                thrp,__,__ = loadThrp(thrpLogFilePath)
                thrp = [0]*tp.appParam.flowIntv*i + thrp + [0]*tp.appParam.flowIntv*(tp.appParam.flowNum-i-1)
                thrp = thrp[:total_len] if len(thrp)>total_len else [0]*(total_len-len(thrp))+thrp
                #thrp = thrpAggr(thrp,2)
                thrps.append(thrp)
        else:
            pass

        if isDetail or tp.appParam.test_type in ["throughputWithTraffic","owdThroughputBalance"]:
            result[tp] = thrps
            #print(thrps)
        else:
            if metric=="thrp" and len(thrps)>tp.appParam.sendTime*tp.appParam.sendRound:
                thrps = thrps[:tp.appParam.sendTime*tp.appParam.sendRound]
            thrps.sort()
            p_95 = thrps[int(0.95*len(thrps))]
            p_99 = thrps[int(0.99*len(thrps))]
            result[tp] = mean(thrps,method='all')
            print('len=',len(thrps),'average =%.2f'%result[tp],'95th=%.2f'%(p_95),'99th=%.2f'%(p_99))
    return result

def getPlotParam(tp):
    test_type = tp.appParam.test_type
    if test_type=="owdTest":    #cdf
        if tp.appParam.protocol=='INTCP':
            linestyle = "--"
        else:
            linestyle = "-"
        loss_to_color = {0.2:'orangered',1:'royalblue',2:'green'}
        color = loss_to_color[tp.linksParam.defaultLP.loss]
        marker = 's'
    elif test_type == "cpuTest":
        loss_to_params = {
            0: ('orangered','s','-'),
            1: ('royalblue','o','--'),
            2:('green','v',':')
        }
        color, marker, linestyle = loss_to_params[tp.linksParam.defaultLP.loss]
    else:
        linestyle = '-'
        if tp.appParam.analyse_callback == "cdf":
            if tp.appParam.protocol == "TCP":
                cc_to_linestyle = {
                                        'bbr':"--",
                                        'pcc':"-.",
                                        'hybla':":"
                                   }
                try:
                    linestyle = cc_to_linestyle[tp.appParam.e2eCC]
                except:
                    a = 1
        if tp.appParam.protocol=="INTCP":
            color = '#ff5b00'  #orangered fd8d49
            marker = 'o'
        elif tp.appParam.e2eCC=="cubic" and tp.appParam.midCC=="cubic":
            color,marker = 'orange','^'
        else:
            cc_to_param={'pcc':('cornflowerblue','x'),
                         'bbr':('#2ca02c','s'),
                         'westwood':('orange','^'),
                         'vegas':('crimson','P'),
                         'cubic':('brown','v'),
                         'hybla':('mediumorchid','D'),}    #'darkviolet'
            color,marker = cc_to_param[tp.appParam.e2eCC]
    if tp.appParam.analyse_callback == "bar" and tp.appParam.coverage == 0.25:
        color = "sandybrown"
    return color,marker,linestyle

def getScatterParam(tp):
    linestyle = '-'
    if tp.appParam.protocol=="INTCP":
        color = '#ff5b00'  #orangered fd8d49
        marker = 'o'
        edge_color = color
        if tp.appParam.midCC == 'nopep':
            color = "white"
    #elif tp.appParam.e2eCC=="cubic" and tp.appParam.midCC=="cubic":
    #    color,marker = 'orange','^'
    else:
        cc_to_param={'pcc':('cornflowerblue','X'),
                        'bbr':('#2ca02c','s'),
                        'westwood':('crimson','P'),
                        'cubic':('brown','v'),
                        'hybla':('mediumorchid','D')}    #'darkviolet'
        color,marker = cc_to_param[tp.appParam.e2eCC]
        edge_color = color
        if tp.appParam.protocol=="TCP" and tp.appParam.midCC!="nopep":
            if tp.appParam.e2eCC=="pcc":
                marker = "x"
            else:
                color = "white"
    return color,marker,edge_color

def drawCondfidenceCurve(group,result,keyX,label,color,marker,alpha=0.3,mode=2):
    if mode==1:
        x=[]
        y=[]
        for testParam in group:
            cnt = len(result[testParam])
            x += cnt*[testParam.get(keyX)]
            y += result[testParam]
        #sns.regplot(x=x,y=y,scatter_kws={'s':10},line_kws={'linewidth':1,'label':label},ci=95,x_estimator=np.mean)
        sns.regplot(x=x,y=y,scatter_kws={'s':2,'color':color,},line_kws={'linewidth':1,'label':label,'color':color},ci=95)

    elif mode==2:
        x = []
        y_mean=[]
        y_lower = []
        y_upper = []

        for testParam in group:
            y = result[testParam]
            if len(y)==0:
                continue
            cur_x = testParam.get(keyX)
            cur_y_lower = scoreatpercentile(y,5)
            cur_y_upper = scoreatpercentile(y,95)
            x.append(testParam.get(keyX))
            y_mean.append(mean(y,method='all'))
            y_lower.append(cur_y_lower)
            y_upper.append(cur_y_upper)
            plt.plot([cur_x,cur_x],[cur_y_lower,cur_y_upper],color=color)

        plt.plot(x,y_mean,label=label,color=color,marker=marker)
        plt.fill_between(x,y_mean,y_lower,color=color,alpha=alpha)
        plt.fill_between(x,y_mean,y_upper,color=color,alpha=alpha)

def plotOneFig(resultPath, result, keyX, groups, title, legends=[],test_type="throughputTest",metric="thrp"):
    plt.figure(figsize=(8,5),dpi = 320)
    if test_type in ["throughputTest","throughputWithTraffic"]:
        plt.ylim((0,20))
    elif test_type=="trafficTest":
        plt.ylim((100,120))
    elif test_type=="owdTest":
        plt.ylim((0,1000))
    elif test_type=="cpuTest":
        plt.ylim((10,25))
    elif test_type=="throughputWithOwd":
        if metric=="thrp":
            #print("thrp")
            plt.ylim((0,10))
        elif metric=="owd":
            #print("owd")
            plt.ylim((0,200))
        else:
            #print("loss")
            plt.ylim((0,5))
    else:
        pass
    
    analyse_callback = groups[0][0].appParam.analyse_callback
    #legend_font = {'size':12}#"family" : "Times New Roman",
    if len(groups)==1:
        group = groups[0]
        #print(metric)
        #print([testParam.get(keyX) for testParam in group])
        #print([result[testParam] for testParam in group])
        plt.plot([testParam.get(keyX) for testParam in group],
                 [result[testParam] for testParam in group])
    else:
        for i,group in enumerate(groups):

            color,marker,linestyle = getPlotParam(group[0])

            if test_type in ["throughputTest","trafficTest","throughputWithOwd","cpuTest"]:
                if keyX=="numMidNode":
                    plt.plot([testParam.get(keyX)+1 for testParam in group],
                            [result[testParam] for testParam in group], label=legends[i],marker=marker,linestyle=linestyle,color=color,markersize=marker_size,linewidth=line_width)
                elif group[0].appParam.dynamic==0 and test_type=="throughputWithOwd" and metric=="owd" and analyse_callback=="lineChart_with_loss":
                    #ggetOwdTotal(tp):
                    if "rtt" in keyX:
                        plt.plot([getOwdTotal(testParam)[0] for testParam in group],
                            [result[testParam]-getOwdTotal(testParam)[0] for testParam in group], label=legends[i],marker=marker,linestyle=linestyle,color=color,markersize=marker_size,linewidth=line_width)
                    else:
                        plt.plot([testParam.get(keyX) for testParam in group],
                            [result[testParam]-getOwdTotal(testParam)[0] for testParam in group], label=legends[i],marker=marker,linestyle=linestyle,color=color,markersize=marker_size,linewidth=line_width)
                else:
                    if "rtt" in keyX:
                        plt.plot([getOwdTotal(testParam)[0] for testParam in group],
                            [result[testParam] for testParam in group], label=legends[i],marker=marker,linestyle=linestyle,color=color,markersize=marker_size,linewidth=line_width)
                    else:
                        #print([result[testParam] for testParam in group])
                        plt.plot([testParam.get(keyX) for testParam in group],
                                [result[testParam] for testParam in group], label=legends[i],marker=marker,linestyle=linestyle,color=color,markersize=marker_size,linewidth=line_width)
            elif test_type=="throughputWithTraffic":
                plt.plot([testParam.get(keyX) for testParam in group],
                            [result[testParam][0] for testParam in group], label=legends[2*i],marker=marker,linestyle='-',color=color,markersize=marker_size,linewidth=line_width)
                plt.plot([testParam.get(keyX) for testParam in group],
                            [result[testParam][1] for testParam in group], label=legends[2*i+1],marker=marker,linestyle='--',color=color,markersize=marker_size,linewidth=line_width)
            #elif test_type=="throughputWithOwd":    #distance->thrp/owd
            #    vals = []
            #    for tp in group:
            #        distance = get_city_distance(tp.appParam.src,tp.appParam.dst)
            #        vals.append((distance,result[tp]))
            #    vals = sorted(vals,key=lambda x:x[0])
            #    plt.plot([val[0] for val in vals],[val[1] for val in vals],label=legends[i],marker=marker,linestyle=linestyle,color=color,markersize=marker_size,linewidth=line_width)
            else:
                drawCondfidenceCurve(group,result,keyX,legends[i],color,marker,mode=2)
        plt.legend(frameon=True,fontsize=legend_size,borderpad=borderpad,labelspacing=labelspacing,borderaxespad=borderaxespad,handlelength=handlelength,handletextpad=handletextpad)   #,handlelength=1,handletextpad=0.2,borderpad=0.2,borderaxespad=0.2

    # xlabel
    if False:#test_type=="throughputWithOwd":
        plt.xlabel("geodesic distance(km)",size=label_size)
    else:
        string = groups[0][0].keyToStr(keyX)
        string = simplify_name(None,string)
        plt.xlabel(string,size=label_size) #family="Times New Roman",

    # ylabel
    if metric=="loss":
        plt.ylabel('Congestion loss(%)',size=label_size)
    elif test_type == "cpuTest":
        plt.ylabel('CPU utilization(%)',size=label_size)
    elif test_type=="throughputWithOwd" and metric=="owd" and analyse_callback=="lineChart_with_loss":
        plt.ylabel('Queuing delay(ms)',size=label_size)
    elif test_type=="owdTest" or (test_type=="throughputWithOwd" and metric=="owd"):
        plt.ylabel('OWD(ms)',size=label_size)#family="Times New Roman",
    elif test_type=="trafficTest":
        plt.ylabel('Traffic(Mbyte)',size=label_size)
    else:       #throughput test
        plt.ylabel('Throughput(Mbps)',size=label_size)#family="Times New Roman",
    

    plt.grid(True)
    plt.tick_params(labelsize=tick_size)
    plt.tight_layout()
    plt.savefig('%s/%s.png' % (resultPath, title))
    plt.savefig('%s/%s.pdf' % (resultPath, title))
    return

def drawBarChart(resultPath, result, keyX, groups, title, legends=[],test_type="throughputTest",metric="thrp"):
    plt.figure(figsize=(8,5),dpi = 320)
    if metric=="thrp":
        plt.ylim((0,10))
    else:
        plt.ylim((0,320))
    
    x = np.arange(len(groups[0]))
    total_width,n = 0.8,6   #0.6
    width = total_width/n
    plt.xlim((-0.2,3.5))
    #print(len(groups))
    hatches = ['//','||','--','\\','+','o']
    for i,group in enumerate(groups):
        color,__,__ = getPlotParam(group[0])
        label = legends[i]
        #print("legend_len",len(label),"*"+label+"*")
        y = [result[testParam] for testParam in group]
        if i==(len(groups)-1)/2 or i==len(groups)/2:
            tick_label = [simplify_name(None,tp.segToStr(keyX)) for tp in group]
            plt.bar(x+i*width,y,width=width,label=label,tick_label=tick_label,color=color,hatch=hatches[i],alpha=.99)
        else:
            plt.bar(x+i*width,y,width=width,label=label,color=color,hatch=hatches[i],alpha=.99)
    ylabel = "Throughput(Mbps)" if metric=="thrp" else "OWD(ms)"
    #plt.xticks(rotation=5)
    plt.ylabel(ylabel,size=label_size)
    plt.legend(fontsize=legend_size-6,loc='best',labelspacing=labelspacing,handlelength=1,handletextpad=0.2,borderpad=borderpad,borderaxespad=borderaxespad)#borderpad=0.01
    plt.grid(True)
    #plt.tick_params(labelsize=tick_size)
    plt.tick_params(labelsize=label_size)
    plt.tight_layout()
    title = "city_pairs - %s"%(metric)
    plt.savefig('%s/%s.png' % (resultPath, title))
    plt.savefig('%s/%s.pdf' % (resultPath, title))
    return

def simplify_name(tp,string):
    # labels
    if tp is None:
        if 'gs1_m1.itmDown' in string:
            string = "Intermittence time(s)"
        if 'varBw' in string:
            string = "Bandwidth variance(Mbps)"
        if 'numMidNode' in string:
            string = "Hop count"
        if 'defaultLP.bw' in string:
            string = 'Bandwidth(Mbps)'
        if 'defaultLP.loss' in string:
            string = "PLR(%)"
        if 'dynamic_intv' in string:
            string = "Link change interval(s)"
        if 'dst=45' in string:
            #string = "Beijing-HongKong"
            string = "BJ-HK"
        if 'dst=63' in string:
            string = "Beijing-Singapore"
        if 'dst=24' in string:
            #string = "Beijing-Paris"
            string = "BJ-PR"
        if 'dst=9' in string:
            #string = 'Bejing-NewYork'
            string = "BJ-NY"
        if "rtt" in string:
            string = "Propagation delay(ms)"
    # legend
    else:
        if "protocol=INTCP" in string:
            string = string.replace("e2eCC=cubic","")
            string = string.replace("protocol=INTCP","")
            if "midCC=pep" in string:
                string = string.replace("midCC=pep","")
                string = "LEOTP"+ string
            elif "midCC=nopep" in string:
                string = string.replace("midCC=nopep","")
                string = "LEOTP(e2e)"+ string
            else:
                string = "e2e INTCP"+ string
        if "protocol=TCP" in string:
            string = string.replace("protocol=TCP","")
        for tcpCC in ["cubic","reno","hybla","westwood","bbr","pcc","vegas"]:
            if "e2eCC=%s"%tcpCC in string and "midCC=%s"%tcpCC in string:
                string = string.replace("e2eCC=%s"%tcpCC,"")
                string = string.replace("midCC=%s"%tcpCC,"")
                string = tcpCC+ " split " + string
            elif "e2eCC=%s"%tcpCC in string and "midCC=nopep" in string:
                string = string.replace("e2eCC=%s"%tcpCC,"")
                string = string.replace("midCC=nopep","")
                string = tcpCC + string
        if "dynamic_isl_loss=0.05" in string:
            string = string.replace("dynamic_isl_loss=0.05","")
        if "dynamic_isl_loss=1" in string:
            string = string.replace("dynamic_isl_loss=1","")
        if "defaultLP.loss" in string:
            if "LEOTP" in string:
                string = string.replace("defaultLP.loss","PLR")
            else:
                string = string.replace("defaultLP.loss","    PLR")

        if "westwood" in string:
            string = string.replace("westwood","Westwood")
        if "cubic" in string:
            string = string.replace("cubic","Cubic")
        if "hybla" in string:
            string = string.replace("hybla","Hybla")
        if "pcc" in string:
            string = string.replace("pcc","PCC")
        if "bbr" in string:
            string = string.replace("bbr","BBR")
        if "vegas" in string:
            string = string.replace("vegas","Vegas")
        if "coverage=1" in string:
            string = string.replace("coverage=1","")
        if "coverage=0.25" in string:
            string = string.replace("coverage=0.25","").strip()+"(0.25)"
        #if "Cubic split" in string:
        #    string = string.replace("Cubic split","Split TCP")
        '''
        if "PER=0.2%" in string:
            #string = string.replace("PER=0.2%","BER=2x10$^{-7}$")
            string = string.replace("PER=0.2%","BER=%.1E"%(0.2/100/10000))
        if "PER=1%" in string:
            #string = string.replace("PER=0.2%","BER=2x10$^{-7}$")
            string = string.replace("PER=1%","BER=%.1E"%(1/100/10000))
        if "PER=2%" in string:
            #string = string.replace("PER=0.2%","BER=2x10$^{-7}$")
            string = string.replace("PER=2%","BER=%.1E"%(2/100/10000))
        '''
        string = string.strip()
    return string

def plotByGroup(tpSet, mapNeToResult, resultPath,metric="thrp"):
    pointGroups = []
    for tp in tpSet.testParams:
        found = False
        for group in pointGroups:

            if tp.compareKeys(group[0], tpSet.keysCurveDiff+tpSet.keysPlotDiff):

                found = True
                group.append(tp)
                break
        if not found:
            pointGroups.append([tp])
    print(len(pointGroups))
    curves = []
    
    for group in pointGroups:
        if len(group)>=2:
            # sort
            if tpSet.tpTemplate.appParam.analyse_callback not in ["bar","scatter"]:
                group = sorted(group, key=functools.cmp_to_key(lambda a1,a2: a1.get(tpSet.keyX) - a2.get(tpSet.keyX)))
        curves.append(group)
    print('curves num:',len(curves))

    curveGroups = []
    for curve in curves:
        found = False
        for group in curveGroups:
            if curve[0].compareKeys(group[0][0], tpSet.keysPlotDiff):
                found = True
                group.append(curve)
                break
        if not found:
            curveGroups.append([curve])
    print('plots num:',len(curveGroups))

    for curveGroup in curveGroups:
        legends = []
        for curve in curveGroup:
            keys = tpSet.keysCurveDiff
            keyMidCC = 'appParam.midCC'
            keyE2eCC = 'appParam.e2eCC'
            if keyMidCC in keys and keyE2eCC in keys:
                keys.remove(keyMidCC)
                keys.remove(keyE2eCC)
                midCC = curve[0].get(keyMidCC)
                stringCC = e2eCC = curve[0].get(keyE2eCC)
                if midCC == 'nopep':
                    stringCC += ' e2e'
                elif midCC == e2eCC:
                    stringCC += 'split'
                else:
                    stringCC += ' + '+midCC
            else:
                stringCC = ''
            string = stringCC + ' ' + ' '.join([curve[0].segToStr(key) for key in keys])
            string = simplify_name(curve[0],string)
            if not tpSet.tpTemplate.appParam.test_type=="throughputWithTraffic":
                legends.append(string)
            else:
                legends.append(string)
                legends.append(string+" intf")
        keyX = tpSet.keyX
        
        test_type = tpSet.tpTemplate.appParam.test_type
        
        if test_type=="owdTest":
            title = '%s - OneWayDelay' % (keyX)
        elif test_type=="trafficTest":
            #print("fuck")
            title = '%s - Traffic' % (keyX)
            #print(title)
        elif test_type in ["throughputTest","throughputWithTraffic"]:
            title = '%s - throughput' % (keyX)
            print(title)
        elif test_type=="throughputWithOwd":
            if metric=="thrp":
                title = '%s - throughput' % (keyX)
            elif metric=="owd":
                title = '%s - OneWayDelay' % (keyX)
            else:
                title = '%s - loss' % (keyX)
        elif test_type=="cpuTest":
            title = '%s - CPU' % (keyX)
        else:
            title = ""
        if tpSet.keysPlotDiff != []:
            title += '(%s)' % (' '.join([curve[0].segToStr(seg) for seg in tpSet.keysPlotDiff]))
        if tpSet.tpTemplate.appParam.analyse_callback=="bar":
            drawBarChart(resultPath, mapNeToResult, keyX, curveGroup, title=title, legends=legends,test_type=test_type,metric=metric)
        elif tpSet.tpTemplate.appParam.analyse_callback=="scatter":
            drawScatterGraph(resultPath, mapNeToResult, keyX, curveGroup, title=title, legends=legends,test_type=test_type,metric=metric)
        else:
            plotOneFig(resultPath, mapNeToResult, keyX, curveGroup, title=title, legends=legends,test_type=test_type,metric=metric)


def drawCDF(tpSet, mapNeToResult, resultPath,retranPacketOnly=False,metric="thrp"):
    plt.figure(figsize=(8,5),dpi = 320)
    if metric == "owd":
        x_max = 500 if tpSet.tpTemplate.appParam.test_type=="owdTest" else 200
        x_min,y_min,y_max = 0,0,1.01
        xlabel = 'OWD(ms)'
        title = "cdf_owd_retran" if retranPacketOnly else "cdf_owd_all"
        
    elif metric=="thrp":
        xlabel = 'Throughput(Mbps)'
        title = "cdf_throughput"
        x_min,x_max,y_min,y_max = 0,10.5,0,1.01

    x = np.linspace(x_min,x_max,num=500)
    plt.xlim((x_min,x_max))
    plt.ylim((y_min,y_max))
    
    keys = tpSet.keysCurveDiff
    legends = []
    for tp in tpSet.testParams:
        print(tp.name,"avg",mean(mapNeToResult[tp]))
        if len(mapNeToResult[tp]) >0:
            color,__,linestyle = getPlotParam(tp)
            ecdf = sm.distributions.ECDF(mapNeToResult[tp])
            y = ecdf(x)
            #plt.step(x,y)
            plt.step(x,y,linestyle=linestyle,color=color,linewidth=line_width)
            string = ' '.join([tp.segToStr(key) for key in keys])
            string = simplify_name(tp,string)
            legends.append(string)
    
    plt.legend(legends,fontsize=legend_size,borderpad=borderpad,labelspacing=labelspacing,borderaxespad=borderaxespad,handletextpad=handletextpad,handlelength=handlelength)
    #labelspacing=0.2,handlelength=1,handletextpad=0.2,borderpad=0.2,borderaxespad=0.2
    #plt.title(title)
    plt.xlabel(xlabel,size=label_size)
    plt.ylabel("CDF",size=label_size)
    plt.tick_params(labelsize=tick_size)
    plt.tight_layout()
    plt.grid()
    plt.savefig('%s/%s.png' % (resultPath, title))
    plt.savefig('%s/%s.pdf' % (resultPath, title))
    #plt.show()

def drawSeqGraph(tpSet, mapNeToResult, resultPath):
    for tp in tpSet.testParams:
        total_len = tp.appParam.sendTime+(tp.appParam.flowNum-1)*tp.appParam.flowIntv
        plt.figure(figsize=(8,5),dpi = 320)
        plt.ylim((0,tpSet.tpTemplate.linksParam.defaultLP.bw))
        plt.xlim((0,total_len))
        #legends = []
        for i in range(tp.appParam.flowNum):
            string = ' '.join([tp.segToStr(key) for key in tpSet.keysCurveDiff])
            string = simplify_name(tp,string) + " Flow%d"%(i+1)
            print(string)
            plt.plot([j for j in range(len(mapNeToResult[tp][i]))],mapNeToResult[tp][i],label=string,linewidth=2)
            #legends.append(string)
        title = 'seq'
        #plt.title(title)
        plt.legend(frameon=True,fontsize=legend_size,borderpad=borderpad,labelspacing=labelspacing,borderaxespad=borderaxespad)#,handlelength=handlelength,handletextpad=handletextpad)
        plt.xlabel('Time(s)',size=label_size)
        plt.ylabel('Throughput(Mbps)',size=label_size)
        plt.tick_params(labelsize=tick_size)
        plt.tight_layout()
        plt.grid()
        plt.savefig('%s/%s_%s.png' % (resultPath,title,tp.name))
        plt.savefig('%s/%s_%s.pdf' % (resultPath,title,tp.name))
        plt.cla()


# for owd-thrp balance test
#plotOneFig(resultPath, mapNeToResult, keyX, curveGroup, title=title, legends=legends,test_type=test_type,metric=metric)
def drawScatterGraph(resultPath, mapNeToResult, keyX, groups, title, legends,test_type,metric):
    plt.figure(figsize=(8,5),dpi = 320)
    #plt.xlim((100,300))
    plt.ylim((0,20))
    point_size = 200
    for i,group in enumerate(groups):
        #color,marker,__ = getPlotParam(group[0])
        color,marker, edge_color= getScatterParam(group[0])
        print(color,marker,edge_color)
        owd = []
        thrp = []
        # draw INTCP
        for tp in group:
            if mapNeToResult[tp]==[]:
                continue
            owd.append(mapNeToResult[tp][0])
            thrp.append(mapNeToResult[tp][1])
        plt.scatter(x=owd,y=thrp,color=color,edgecolors=edge_color,marker=marker,label=legends[i],s=point_size)

    #draw bbr
    '''
    owd = []
    thrp = []
    for tp in tpSet.testParams:
        if tp.appParam.protocol=="TCP" and tp.appParam.e2eCC=="bbr" and tp.appParam.sendq_length==0:
            owd.append(mapNeToResult[tp][0])
            thrp.append(mapNeToResult[tp][1])
            #break
    plt.scatter(x=owd,y=thrp,color="green",marker='^',label="BBR",s=point_size)

    # draw pcc
    owd = []
    thrp = []
    for tp in tpSet.testParams:
        if tp.appParam.protocol=="TCP" and tp.appParam.e2eCC=="pcc" and tp.appParam.sendq_length==0:
            owd.append(mapNeToResult[tp][0])
            thrp.append(mapNeToResult[tp][1])
            #break
    plt.scatter(x=owd,y=thrp,color="royalblue",marker='s',label="PCC",s=point_size)
    '''
    plt.legend(loc='best',fontsize=legend_size,borderpad=borderpad,labelspacing=labelspacing,handlelength=1,handletextpad=0.3,borderaxespad=borderaxespad)
    title = "owd-thrp balance"
    #plt.title(title)
    plt.xlabel("OWD(ms)",size=label_size)
    plt.ylabel("Throughput(Mbps)",size=label_size)

    plt.tick_params(labelsize=tick_size)
    plt.tight_layout()
    plt.grid()
    plt.savefig('%s/%s.png' % (resultPath, title))
    plt.savefig('%s/%s.pdf' % (resultPath, title))

def anlz(tpSet, logPath, resultPath):
    os.chdir(sys.path[0])
    
    createFolder(resultPath)

    #mapNeToResult = loadLog(logPath, neSet, isDetail=False)
    #print('-----')
    #plotByGroup(tpSet, mapTpToResult, resultPath)
    if tpSet.tpTemplate.appParam.test_type in ["throughputTest","trafficTest","throughputWithTraffic"]:
        print('-----')
        if tpSet.tpTemplate.appParam.analyse_callback=="lineChart":
            mapTpToResult = loadLog(logPath, tpSet, isDetail=False)
            if tpSet.keyX == 'nokeyx':
                print('tpSet no keyX')
            else:
                plotByGroup(tpSet, mapTpToResult, resultPath)
            summaryString = '\n'.join(['%s   \t%.3f'%(tp.name,mapTpToResult[tp]) for tp in mapTpToResult])
            print(summaryString)
            writeText('%s/summary.txt'%(resultPath), summaryString)
            writeText('%s/template.txt'%(resultPath), tpSet.tpTemplate.serialize())
        elif tpSet.tpTemplate.appParam.analyse_callback=="cdf":
            mapTpToResult = loadLog(logPath, tpSet, isDetail=True)
            drawCDF(tpSet,mapTpToResult,resultPath,metric="thrp")

    elif tpSet.tpTemplate.appParam.test_type=="owdTest":
        #print('entering rtt analyse')
        
        generateLog(logPath,tpSet)
        
        # all packets cdf
        #mapTpToResult = loadLog(logPath, tpSet,isDetail=False)
        #drawCDF(tpSet,mapTpToResult,resultPath)
        #drawSeqGraph(tpSet,mapTpToResult, resultPath)
        
        # retranPacketOnly cdf
        mapTpToResult = loadLog(logPath, tpSet,isDetail=True,retranPacketOnly=True)
        drawCDF(tpSet,mapTpToResult,resultPath,retranPacketOnly = True,metric="owd")
        mapTpToResult = loadLog(logPath, tpSet,isDetail=True,retranPacketOnly=True)
        for tp in mapTpToResult:
            owds = mapTpToResult[tp]
            #owds.sort()
            print(tp.name,mean(owds)-50)

    elif tpSet.tpTemplate.appParam.test_type=="owdThroughputBalance":
        generateLog(logPath,tpSet)
        mapTpToResult = loadLog(logPath, tpSet)
        #drawScatterGraph(tpSet, mapTpToResult, resultPath)
        plotByGroup(tpSet, mapTpToResult,resultPath)
        #pass
    elif tpSet.tpTemplate.appParam.test_type=="cpuTest":
        mapTpToResult = loadLog(logPath, tpSet)
        plotByGroup(tpSet, mapTpToResult,resultPath)

    elif tpSet.tpTemplate.appParam.test_type=="throughputWithOwd":
        generateLog(logPath,tpSet)
        if tpSet.tpTemplate.appParam.analyse_callback=="cdf":
            for metric in ["thrp","owd"]:
                mapTpToResult = loadLog(logPath, tpSet, isDetail=True,metric=metric)
                drawCDF(tpSet,mapTpToResult,resultPath,metric=metric,retranPacketOnly=False)
        elif tpSet.tpTemplate.appParam.analyse_callback=="lineChart":
            for metric in ["thrp","owd"]:
                mapTpToResult = loadLog(logPath, tpSet, isDetail=False,metric=metric)
                plotByGroup(tpSet, mapTpToResult,resultPath,metric=metric)
                summaryString = '\n'.join(['%s   \t%.3f'%(tp.name,mapTpToResult[tp]) for tp in mapTpToResult])
                print(summaryString)
                writeText('%s/summary_%s.txt'%(resultPath,metric), summaryString)
                writeText('%s/template.txt'%(resultPath), tpSet.tpTemplate.serialize())
        elif tpSet.tpTemplate.appParam.analyse_callback=="lineChart_with_loss":
            for metric in ["thrp","owd","loss"]:
                mapTpToResult = loadLog(logPath, tpSet, isDetail=False,metric=metric)
                plotByGroup(tpSet, mapTpToResult,resultPath,metric=metric)
                summaryString = '\n'.join(['%s   \t%.3f'%(tp.name,mapTpToResult[tp]) for tp in mapTpToResult])
                print(summaryString)
                writeText('%s/summary_%s.txt'%(resultPath,metric), summaryString)
                writeText('%s/template.txt'%(resultPath), tpSet.tpTemplate.serialize())
        elif tpSet.tpTemplate.appParam.analyse_callback=="bar":
            for metric in ["thrp","owd"]:
                mapTpToResult = loadLog(logPath, tpSet, isDetail=False,metric=metric)
                plotByGroup(tpSet, mapTpToResult,resultPath,metric=metric)
        elif tpSet.tpTemplate.appParam.analyse_callback=="seq":
            pass
    elif tpSet.tpTemplate.appParam.test_type=="fairnessTest":
        mapTpToResult = loadLog(logPath, tpSet, isDetail=True)
        drawSeqGraph(tpSet,mapTpToResult,resultPath)
    fixOwnership(resultPath,'r')

"""
if __name__=='__main__':
    tpSetNames = ['expr']
    for sno,tpSetName in enumerate(tpSetNames):
        print('Analyzing TestParamSet (%d/%d)\n' % (sno+1,len(tpSetNames)))
        tpSet = MyParam.getTestParamSet(tpSetName)
        # netTopo = NetTopo.netTopos[neSet.neTemplate.netName]

        logPath = '%s/%s' % ('./logs', tpSetName)
        resultPath = '%s/%s' % ('./result', tpSetName)
        anlz(tpSet, logPath, resultPath)
"""
