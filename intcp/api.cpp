#include "./include/api.h"

int chdirProgramDir(){
    int ret = -1;
    string _curPath_s_;
    char _exec_name_ [BUFSIZ];
    ret = readlink ("/proc/self/exe", _exec_name_, BUFSIZ);
    if(ret==-1){
        LOG(ERROR,"get exec file's path failed.");
        return -1;
    }
    string _temp_s_ = _exec_name_;
    int _index_s_ = _temp_s_.find_last_of("/");
    if(_index_s_==string::npos){
        LOG(ERROR,"get exec file's dir path failed.");
        return -2;
    }
    _curPath_s_ = _temp_s_.substr(0, _index_s_);
    LOG(TRACE,"%s",_curPath_s_.c_str());
    ret = chdir(_curPath_s_.c_str());
    if(ret!=0){
        LOG(ERROR,"chdir error.");
        return -3;
    }

    return 0;
}

void *GSonNewSess(void* _sessPtr){
    IntcpSess *sessPtr = (IntcpSess*)_sessPtr;
    char recvBuf[INTCP_MSS];
    IUINT32 start, end, nwrite;
    while(1){
        while (sessPtr->recvData(recvBuf, INTCP_MSS, &start, &end) == 0){
            if (start >= end) {
                LOG(DEBUG,"abnormal range: rangeStart %u rangeEnd %u length %u",start,end,end-start);
            }
            else {
                // send to host
                nwrite = write(sessPtr->tunFd_toHost, recvBuf, end-start);
                if (nwrite == -1)
                {
                    LOG(ERROR, "write to tunFd error: %d.\n", errno);
                }
                LOG(TRACE, "Send %d bytes to host.\n", nwrite);
            }
        }
        usleep(1000);
    }
    return nullptr;
}

void startGSnode(Cache *cachePtr, ByteMap<shared_ptr<IntcpSess>> *sessMapPtr, 
        const char* ipStr, uint16_t PortH,
        const char* ipStrOpp, uint16_t PortHOpp, int tunFd){
    int ret;
    // requester
    Quad quadBack(inet_addr(ipStr), PortH, inet_addr(ipStrOpp), PortHOpp);
    shared_ptr<IntcpSess> sessPtrBack(new IntcpSess(quadBack, cachePtr,
            INTCP_ROLE_REQUESTER, GSonNewSess));
    sessPtrBack->tunFd_toHost = tunFd;
    sessMapPtr->setValue(quadBack.chars, QUAD_STR_LEN, sessPtrBack);
    // responder
    Quad quadGo(inet_addr(ipStrOpp), PortHOpp, inet_addr(ipStr), PortH);
    shared_ptr<IntcpSess> sessPtrGo(new IntcpSess(quadGo, cachePtr,
            INTCP_ROLE_RESPONDER, nullptr));
    sessPtrGo->socketFd_toReq = sessPtrBack->socketFd_toResp;
    sessMapPtr->setValue(quadGo.chars, QUAD_STR_LEN, sessPtrGo);

    struct GSudpRecvLoopArgs args;
    args.sessMapPtr = sessMapPtr;
    args.onNewSess = GSonNewSess;
    args.sessPtrBack = sessPtrBack;
    args.sessPtrGo = sessPtrGo;
    args.listenAddr = sessPtrBack->requesterAddr;
    args.listenFd = sessPtrBack->socketFd_toResp;
    args.cachePtr = cachePtr;
    args.tunFd = tunFd;
    pthread_t listener;
    ret = pthread_create(&listener, NULL, &GSudpRecvLoop, &args);
    // GSudpRecvLoop(&args);

    pthread_join(listener, nullptr);
}

void startRequester(Cache *cachePtr, ByteMap<shared_ptr<IntcpSess>> *sessMapPtr, 
        void *(*onNewSess)(void* _sessPtr),
        const char* ipStrReq, const char* ipStrResp, uint16_t respPortH){
    int ret;
    shared_ptr<IntcpSess> sessPtr(new IntcpSess(inet_addr(ipStrReq), inet_addr(ipStrResp), ntohs(respPortH), 
            cachePtr, onNewSess));
    //NOTE manually add to sessMapPtr
    Quad quad(sessPtr->requesterAddr, sessPtr->responderAddr);
    sessMapPtr->setValue(quad.chars, QUAD_STR_LEN, sessPtr);

    struct udpRecvLoopArgs args;
    args.sessMapPtr = sessMapPtr;
    args.onNewSess = nullptr;
    args.listenAddr = sessPtr->requesterAddr;
    args.listenFd = sessPtr->socketFd_toResp;
    args.cachePtr = cachePtr;
    pthread_t listener;
    ret = pthread_create(&listener, NULL, &udpRecvLoop, &args);

    pthread_join(listener, nullptr);
}

void startResponder(Cache *cachePtr, ByteMap<shared_ptr<IntcpSess>> *sessMapPtr, 
        void *(*onNewSess)(void* _sessPtr), int (*onUnsatInt)(IUINT32 start, IUINT32 end, void *user),
        const char* ipStr, uint16_t respPortH){
    int ret;
    struct udpRecvLoopArgs args;
    args.sessMapPtr = sessMapPtr;
    args.onNewSess = onNewSess;
    args.listenAddr = toAddr(inet_addr(ipStr),htons(respPortH));
    args.cachePtr = cachePtr;
    args.onUnsatInt = onUnsatInt;
    pthread_t listener;
    pthread_create(&listener, NULL, &udpRecvLoop, &args);

    pthread_join(listener, nullptr);
}

void startMidnode(Cache *cachePtr, ByteMap<shared_ptr<IntcpSess>> *sessMapPtr, 
        void *(*onNewSess)(void* _sessPtr),
        uint16_t listenPortH){
    int ret;
    // forward all the passing UDP packets to our listening port.
    // chdirProgramDir();
    // char cmd[50];
    // sprintf(cmd,"./setipt.sh %d", listenPortH);
    // system(cmd);
    system("sudo iptables -t mangle -F");

    system("ip rule add fwmark 1 table 100 ");
    system("ip route add local 0.0.0.0/0 dev lo table 100");

    system("iptables -t mangle -N MID");
    system("iptables -t mangle -A MID -d 127.0.0.1/32 -j RETURN");
    system("iptables -t mangle -A MID -d 224.0.0.0/4 -j RETURN ");
    system("iptables -t mangle -A MID -d 255.255.255.255/32 -j RETURN ");
    string portStr = "iptables -t mangle -A MID -p UDP -j TPROXY --on-port "
            + to_string(listenPortH) + " --tproxy-mark 1";
    system(portStr.c_str());
    system("iptables -t mangle -I MID -m mark --mark 0xff -j RETURN # avoid infinite loop");

    system("iptables -t mangle -A PREROUTING -j MID");
    
    struct udpRecvLoopArgs args;
    args.sessMapPtr = sessMapPtr;
    args.onNewSess = onNewSess;
    args.listenAddr = toAddr(INADDR_ANY, htons(listenPortH));
    args.cachePtr = cachePtr;
    pthread_t listener;
    pthread_create(&listener, NULL, &udpRecvLoop, &args);

    pthread_join(listener, nullptr);
}

void signalHandler( int signum )
{
    cout << "Interrupt signal (" << signum << ") received.\n";
    fflush(stdout);
    exit(signum); 
}
void flushBeforeExit(){
    signal(SIGINT, signalHandler);
    signal(SIGTERM, signalHandler);
}