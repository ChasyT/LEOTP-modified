#!/usr/bin/python3

import sys
import os
import argparse
from scapy.all import *

sys.path.append(os.path.dirname(os.sys.path[0]))
from appLayer.tcpApp import Utils

timeFilter = 0
packet_limit = 0
packet_cnt = 0
sumUdpLen = 0
lastSniffTime =0

def getArgsFromCli():
    parser = argparse.ArgumentParser()
    parser.add_argument('-t',type=int, default=0, help='sniffer for tcp packets')
    parser.add_argument('-f',type=int, default=0)
    parser.add_argument('-l',type=int, default=0,help="number limit for packet")
    parser.add_argument('-i',type=str, default=None)

    args = parser.parse_args()
    return args

#start in the pos
def unpack(bytePayload,pos):
    cmd = int.from_bytes(bytePayload[pos:pos+1],byteorder='little')
    wnd = int.from_bytes(bytePayload[pos+1:pos+3],byteorder='little')
    ts = int.from_bytes(bytePayload[pos+3:pos+7],byteorder='little')
    sn = int.from_bytes(bytePayload[pos+7:pos+11],byteorder='little')
    length = int.from_bytes(bytePayload[pos+11:pos+15],byteorder='little')
    rangeStart = int.from_bytes(bytePayload[pos+15:pos+19],byteorder='little')
    rangeEnd = int.from_bytes(bytePayload[pos+19:pos+23],byteorder='little')
    return  cmd,wnd,ts,sn,length,rangeStart,rangeEnd

def simple_unpack(bytePayload):
    cmd = int.from_bytes(bytePayload[0:1],byteorder='little')
    rangeStart = int.from_bytes(bytePayload[15:19],byteorder='little')
    return cmd,rangeStart

def Callback_udp(packet):
    global packet_cnt
    global packet_limit
    global lastSniffTime
    try:
        #udp packet
        if not packet[IP].proto==17:
            return
        bytePayload =packet.payload.payload.payload.original
        '''
        cmd,rangeStart = simple_unpack(bytePayload)
        if cmd==81 and rangeStart%5==0:
            print("rangeStart",rangeStart,"time",Utils.getStrTime())
            
        '''
        udpLength = len(bytePayload)
        global sumUdpLen
        #sumUdpLen += udpLength
        #print(sumUdpLen/1024/1024)
        pos = 0
        while True:
            if pos+23>udpLength:
                break
            cmd,wnd,ts,sn,length,rangeStart,rangeEnd = unpack(bytePayload,pos)
            pos += (23+length)

            cur = int(time.time()*1000)%2**32
            if cmd==81: #data only
                if length>0:    #skip header
                    print("sn",sn,"length",length,"rangeStart",rangeStart,"rangeEnd",rangeEnd,"time",Utils.getStrTime(),flush=True)
                packet_cnt += 1
            #if cmd==81:
                #print('cur',int(time.time()*1000)%2**32,'ts',ts)
                #if cur - ts > timeFilter:
                #print(f"{cur} ({sn}) time - ts {cur - ts}")
            # if cmd==80:
            #     # print('cur',int(time.time()*1000)%2**32,'ts',ts)
            #     if int(time.time()*1000)%2**32 - ts > timeFilter:
            #         print(f"({sn})int time - ts {int(time.time()*1000)%2**32 - ts}")
        
    except:
        return

def Callback_tcp(packet):
    #TCP packet
    global packet_cnt
    global packet_limit
    try:
        if not packet[IP].proto==6:
            return
        length = len(packet[TCP].payload.original)
        print('seq',packet[TCP].seq,'length',length,'time',Utils.getStrTime())
        #print(packet[IP].src,":",packet[TCP].sport,'-->',packet[IP].dst,":",packet[TCP].dport)
    except:
        return

if __name__=="__main__":
    print('begin to catch packets..',flush=True)
    args = getArgsFromCli()
    timeFilter = args.f
    packet_limit = args.l
    iface = args.i
    packet_cnt = 0
    
    if packet_limit>0:
        if args.t:
            #sniff(filter='src host 10.0.1.1', prn=Callback_tcp) #tcp packet from client to server
            sniff(count=packet_limit,filter='dst host 10.0.1.1',iface=iface, prn=Callback_tcp) #tcp packet from client to server
        else:#DEBUG dst
            sniff(count=packet_limit,filter='dst host 10.0.1.1',iface=iface,prn=Callback_udp) #udp packet from server to client
    else:
        max_cnt = 20000
        if args.t:
            while True:
                sniff(count=max_cnt,filter='dst host 10.0.1.1',iface=iface, prn=Callback_tcp) #tcp packet from client to server
                time.sleep(2)
        else:#DEBUG dst
            while True:
                sniff(count=max_cnt,filter='dst host 10.0.1.1',iface=iface,prn=Callback_udp) #udp packet from server to client
                time.sleep(2)
    
