#!/usr/bin/python3

import struct
import socket
from threading import Thread
import time

import Utils
import argparse

DataLen = 16
DataLen_Flow_Test = 1000
#test
def sendFunc(tcp_socket,data_size):
    lastTsAfterSend = -1
    idxPkt = 0
    while 1:
        # 8 bytes
        strTime = Utils.getStrTime()
        # 1024 bytes in all
        if data_size<0.1:   # rtt test
            strPadded = Utils.padStr(strTime, DataLen)
        else:               #flow test
            strPadded = Utils.padStr(strTime, DataLen_Flow_Test)
        bytesToSend = strPadded.encode('utf8')
        Utils.sendData(tcp_socket.send, bytesToSend)


        # tsBeforeSend = float(strTime)
        # tsAfterSend = float(Utils.getStrTime())
        # if tsAfterSend-tsBeforeSend > 0.002:
        #     if lastTsAfterSend != -1:
        #         print('cur %.4f'%tsAfterSend, 'use %.4f'%(tsAfterSend-tsBeforeSend),'intv %.4f'%(tsBeforeSend-lastTsAfterSend))
        #     lastTsAfterSend = tsAfterSend

        idxPkt += 1

        if data_size > 0.01 and (idxPkt*DataLen_Flow_Test>data_size*1000000):   #flow test and data has been sent
            break

        # print(idxPkt)
        fmt="B"*7+"I"*21
        x = struct.unpack(fmt,tcp_socket.getsockopt(socket.IPPROTO_TCP,socket.TCP_INFO,92))
        #print(x)
        if data_size < 0.01:    # rtt test
            time.sleep(0.005)

def recvFunc(tcp_socket,limit):
    prev_owd_c2s = 0
    idxPkt = 0
    recv_data_generator = Utils.recvData(tcp_socket.recv)
    last = time.time()
    lastIdx = 0
    while 1:
        data = recv_data_generator.__next__()

        curTime = Utils.getStrTime()
        owd_c2s = Utils.timeDelta(data[8:16], data[0:8])
        owd_s2c = Utils.timeDelta(curTime, data[8:16])
        rtt = Utils.timeDelta(curTime, data[0:8])
        #if float(owd_c2s)>net_rtt and prev_owd_c2s<net_rtt:
        #if True:
        #if float(owd_c2s)>limit and prev_owd_c2s<limit:
        if float(owd_c2s)>limit:
            #print(data[8:16],'idx', idxPkt, 'owd_c2s', owd_c2s,'owd_s2c',owd_s2c,'rtt', rtt,'owd_obs',owd_c2s,flush=True)
            print(data[8:16],'idx', idxPkt,'sendTime',data[0:8],'recvTime',data[8:16],'curTime',curTime,'owd_c2s', owd_c2s,'owd_s2c',owd_s2c,'rtt', rtt,'owd_obs',owd_c2s,flush=True)
        if len(data) != 16:
            print(idxPkt, data)
            print()
        idxPkt += 1
        prev_owd_c2s = float(owd_c2s)
        cur = time.time()
        if cur-last>=1:
            #TODO one packet is always 1000Byte?
            print((idxPkt-lastIdx)*8/1000,'Mbps',flush=True)
            lastIdx = idxPkt
            last = cur

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-l',type=float,default=0.0)    # only print owd that larger than l
    parser.add_argument('-f',type=float,default=0.0)    # data size for flow test, unit is MB
    
    args = parser.parse_args()
   
    print("limit:",args.l,"flowtest data size:",args.f)

    # create socket
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # tcp_socket.setblocking(False)
    tcp_socket.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)

    #server_addr = ("10.0.100.2", 3000)
    server_addr = ("10.0.1.1",3000)
    #server_addr = ("127.0.0.1", 3000)
    tcp_socket.connect(server_addr)

    sendThread = Thread(target=sendFunc, args=(tcp_socket,args.f))
    sendThread.start()
    
    #recvThread = Thread(target=recvFunc, args=(tcp_socket,args.l,))
    #recvThread.start()
 
    sendThread.join()
    #recvThread.join()
    tcp_socket.close()
