#!/usr/bin/python
import time
from decimal import Decimal


# Unit: xxx.xxxx sec
def getStrTime():
    return '%.4f' % (time.time() % 1000)
# Unit: msec
def timeDelta(strTimeA,strTimeB):
    return '%.1f' % ((float(strTimeA)-float(strTimeB))*1000)

def padStr(string,length):
    return string + ' '*(length-len(string))

def sendData(send,data):
    while len(data) != 0:
        nSent = send(data)
        data = data[nSent:]

def recvData(recv):
    strLeft = ''
    while(1):
        bytesRecv = recv(1024)
        if len(bytesRecv) == 0:
            continue
        strRecv = bytesRecv.decode('utf8')
        subStrs = (strLeft + strRecv).split()
        strLeft = ''
        if len(subStrs) == 0:
            continue
        if strRecv[-1] != ' ':
            strLeft = subStrs[-1]
            del subStrs[-1]
        for ss in subStrs:
            yield ss

