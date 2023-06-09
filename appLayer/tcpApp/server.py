#!/usr/bin/python3

import socket
import Utils
import time

def need_print(owd,prev_owd):
    return True
    if owd>500 and owd>prev_owd:
        return True
    return False
        
if __name__=='__main__':
    tcp_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print('socket created.')

    address = ('',3000)
    tcp_server_socket.bind(address)

    # the created socket is positive by default.
    # use listen() to make it negative, so that it can listen to others' positive socket
    tcp_server_socket.listen(128)

    print('wait for client...')
    # a new socket only for one client will be created.
    client_socket, clientAddr = tcp_server_socket.accept()
    client_socket.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)

    # set CC
    #TCP_CONGESTION = getattr(socket,'TCP_CONGESTION',13)
    #client_socket.setsockopt(socket.IPPROTO_TCP,socket.TCP_CONGESTION,b'bbr')

    # read application-level data
    #recv_data_generator = Utils.recvData(client_socket.recv)
    #idxPkt = 0
    #prev_owd = 0
    last_ts = 0
    start_ts = 0
    thrp = 0
    while(1):
        length = len(client_socket.recv(1024))
        if length>0:
            last_ts = time.time()
            start_ts = last_ts
            thrp += length
            break

    while(1):
        length = len(client_socket.recv(1024))  #unit:byte
        thrp += length
        cur_ts = time.time()
        if cur_ts>last_ts+1:
            print("%.2f-%.2f sec   %d KBytes   %4.2f Mbits/sec"%(last_ts-start_ts,cur_ts-start_ts,thrp/1024,thrp*8/1000000),flush=True)
            last_ts +=1
            thrp = 0
        #data = recv_data_generator.__next__()
        #strTime = Utils.getStrTime()
        #print('idx',data[0:8],'curTime',strTime,flush=True)
        #idxPkt+=1
        #owd_obs = float(Utils.timeDelta(strTime,data[0:8]))
        #if need_print(owd_obs,prev_owd):
        #    print('idx', idxPkt, 'sendTime',data[0:8],'curTime', strTime,'owd_obs',Utils.timeDelta(strTime,data[0:8]),flush=True)
        #prev_owd = owd_obs
        # 24 bytes in all
        # strPadded = Utils.padStr(data + strTime, 26)
        # bytesToSend = strPadded.encode('utf8')
        #Utils.sendData(client_socket.send, bytesToSend)


    client_socket.close()


