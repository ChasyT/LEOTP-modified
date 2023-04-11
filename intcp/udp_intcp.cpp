#include "./include/udp_intcp.h"
#include <iostream>
#include <netinet/ip.h>
#include <netinet/udp.h>
#include <arpa/inet.h>
#include <string.h>
#include <sys/time.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#undef LOG_LEVEL
#define LOG_LEVEL DEBUG

// for debug
double udp_recv_time = 0;
double update_time = 0;
double input_time = 0;

/***************** util functions *****************/

struct sockaddr_in toAddr(in_addr_t IP, uint16_t port)
{
    struct sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = IP;
    addr.sin_port = port;
    return addr;
}

void writeIPstr(char *ret, in_addr_t IP)
{
    int a, b, c, d;

    a = (0x000000FF & IP);
    b = (0x0000FF00 & IP) >> 8;
    c = (0x00FF0000 & IP) >> 16;
    d = (0xFF000000 & IP) >> 24;

    snprintf(ret, 16, "%d.%d.%d.%d", a, b, c, d);
}

/***************** Quad *****************/
// numbers stored in Quad is in type for network ( hton() )
// quadruple for end2end communication
Quad::Quad(in_addr_t _reqAddrIP, uint16_t _reqAddrPort, in_addr_t _respAddrIP, uint16_t _respAddrPort) : reqAddrIP(_reqAddrIP),
                                                                                                         reqAddrPort(_reqAddrPort),
                                                                                                         respAddrIP(_respAddrIP),
                                                                                                         respAddrPort(_respAddrPort)
{
    toChars();
}
Quad::Quad(struct sockaddr_in requesterAddr, struct sockaddr_in responderAddr) : reqAddrIP(requesterAddr.sin_addr.s_addr), reqAddrPort(requesterAddr.sin_port), respAddrIP(responderAddr.sin_addr.s_addr), respAddrPort(responderAddr.sin_port)
{
    toChars();
}

Quad Quad::reverse()
{
    return Quad(respAddrIP, respAddrPort, reqAddrIP, reqAddrPort);
}
void Quad::toChars()
{
    int offset = 0;

    memcpy(this->chars + offset, &this->reqAddrIP, sizeof(this->reqAddrIP));
    offset += sizeof(this->reqAddrIP);
    memcpy(this->chars + offset, &this->reqAddrPort, sizeof(this->reqAddrPort));
    offset += sizeof(this->reqAddrPort);
    memcpy(this->chars + offset, &this->respAddrIP, sizeof(this->respAddrIP));
    offset += sizeof(this->respAddrIP);
    memcpy(this->chars + offset, &this->respAddrPort, sizeof(this->respAddrPort));

    // int check=0;
    // for(int i=0;i<QUAD_STR_LEN;i++) {
    //     cout<<(int)chars[i]<<' ';
    //     check+=chars[i];
    // }
    // cout<<endl;
    // cout<<"toChars() "<<check<<' '<<reqAddrIP<<' '<<reqAddrPort<<' '<<respAddrIP<<' '<<respAddrPort<<endl;
}

struct sockaddr_in Quad::getReqAddr()
{
    struct sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = reqAddrIP;
    addr.sin_port = reqAddrPort;
    return addr;
}
struct sockaddr_in Quad::getRespAddr()
{
    struct sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = respAddrIP;
    addr.sin_port = respAddrPort;
    return addr;
}
bool Quad::operator==(Quad const &quad2) const
{
    // if (reqAddrIP == quad2.reqAddrIP
    //     && reqAddrPort == quad2.reqAddrPort
    //     && respAddrIP == quad2.respAddrIP
    //     && respAddrPort == quad2.respAddrPort )
    //     return true;
    // return false;
    return memcmp(this->chars, quad2.chars, QUAD_STR_LEN) == 0 ? true : false;
}

/***************** INTCP session *****************/

int createSocket(in_addr_t IP, uint16_t port, bool reusePort, uint16_t *finalPort)
{
    int socketFd = -1;
    if ((socketFd = socket(AF_INET, SOCK_DGRAM, 0)) < 0)
    {
        LOG(ERROR, "create socket fail");
        return -1;
    }
    int optval = 1;
    if (reusePort)
    {
        setsockopt(socketFd, SOL_SOCKET, SO_REUSEADDR, &optval, sizeof(int));
    }
    setsockopt(socketFd, SOL_IP, IP_TRANSPARENT, &optval, sizeof(int));
    setsockopt(socketFd, SOL_IP, IP_RECVORIGDSTADDR, &optval, sizeof(int));
    sockaddr_in selfAddr;
    selfAddr.sin_family = AF_INET;
    selfAddr.sin_addr.s_addr = IP;
    uint16_t realPortH = ntohs(port);
    for (; realPortH < ntohs(port) + REUSE_PORT_RANGE; realPortH++)
    {
        selfAddr.sin_port = htons(realPortH);
        if (bind(socketFd, (struct sockaddr *)&selfAddr, AddrLen) != -1)
        {
            LOG(TRACE, "%d", realPortH);
            break;
        }
    }
    // which means all the ports in portRange bind fail
    if (realPortH == ntohs(port) + REUSE_PORT_RANGE)
    {
        LOG(ERROR, "bind fail");
        abort();
    }

    if (finalPort != nullptr)
        *finalPort = htons(realPortH);
    return socketFd;
}

// this is for [requester]
// explicitly called by app-layer
IntcpSess::IntcpSess(in_addr_t reqAddrIP, in_addr_t respAddrIP,
                     uint16_t respAddrPort, Cache *_cachePtr,
                     void *(*onNewSess)(void *_sessPtr)) : nodeRole(INTCP_ROLE_REQUESTER),
                                                           cachePtr(_cachePtr)
{
    packetId = rand() % 100;
    uint16_t reqAddrPort;
    socketFd_toResp = createSocket(reqAddrIP, htons(DEFAULT_CLIENT_PORT), false, &reqAddrPort);
    if (socketFd_toResp == -1)
    {
        abort();
    }
    socketFd_toReq = -1;

    requesterAddr = toAddr(reqAddrIP, reqAddrPort);
    responderAddr = toAddr(respAddrIP, respAddrPort);

    // general
    Quad quad(requesterAddr, responderAddr);
    memcpy(nameChars, quad.chars, QUAD_STR_LEN);
    lock.lock();
    transCB = createTransCB(this, nodeRole, nullptr);
    lock.unlock();
    // pthread_create(&transUpdaterThread, NULL, TransUpdateLoop, this);
    // pthread_create(&onNewSessThread, NULL, onNewSess, this);
    return;
}

// this is for [responder]
// this is called when receiving a new Quad
IntcpSess::IntcpSess(Quad quad, int listenFd, Cache *_cachePtr,
                     void *(*onNewSess)(void *_sessPtr), int (*onUnsatInt)(IUINT32 start, IUINT32 end, void *user)) : nodeRole(INTCP_ROLE_RESPONDER),
                                                                                                                      cachePtr(_cachePtr)
{
    packetId = rand() % 100;
    requesterAddr = quad.getReqAddr();
    responderAddr = quad.getRespAddr();

    socketFd_toReq = listenFd;
    socketFd_toResp = -1;

    memcpy(nameChars, quad.chars, QUAD_STR_LEN);
    lock.lock();
    transCB = createTransCB(this, nodeRole, onUnsatInt);
    lock.unlock();
    // pthread_create(&transUpdaterThread, NULL, TransUpdateLoop, this);
    // pthread_create(&onNewSessThread, NULL, onNewSess, this);
    return;
}

// this is for [midnode]
// this is called when receiving a new Quad
IntcpSess::IntcpSess(Quad quad, Cache *_cachePtr,
                     void *(*onNewSess)(void *_sessPtr)) : nodeRole(INTCP_ROLE_MIDNODE),
                                                           cachePtr(_cachePtr)
{
    packetId = rand() % 100;
    requesterAddr = quad.getReqAddr();
    responderAddr = quad.getRespAddr();

    socketFd_toReq = createSocket(responderAddr.sin_addr.s_addr, responderAddr.sin_port, true, nullptr);
    socketFd_toResp = createSocket(requesterAddr.sin_addr.s_addr, requesterAddr.sin_port, true, nullptr);
    if (socketFd_toReq == -1 || socketFd_toResp)
        memcpy(nameChars, quad.chars, QUAD_STR_LEN);
    lock.lock();
    transCB = createTransCB(this, nodeRole, nullptr);
    lock.unlock();
    pthread_create(&transUpdaterThread, NULL, TransUpdateLoop, this);
    pthread_create(&onNewSessThread, NULL, onNewSess, this);
    return;
}

// this is for [GSnode]
// this is called when receiving a new Quad
IntcpSess::IntcpSess(Quad quad, int _nodeRole, Cache *_cachePtr,
                     void *(*onNewSess)(void *_sessPtr)) : nodeRole(_nodeRole),
                                                           cachePtr(_cachePtr)
{
    packetId = rand() % 100;
    requesterAddr = quad.getReqAddr();
    responderAddr = quad.getRespAddr();
    socketFd_toReq = -1;
    socketFd_toResp = -1;

    if (nodeRole == INTCP_ROLE_REQUESTER)
    {
        socketFd_toResp = createSocket(requesterAddr.sin_addr.s_addr, requesterAddr.sin_port, true, nullptr);
    }
    else if (nodeRole == INTCP_ROLE_REQUESTER)
    {
        socketFd_toReq = createSocket(responderAddr.sin_addr.s_addr, responderAddr.sin_port, true, nullptr);
    }

    memcpy(nameChars, quad.chars, QUAD_STR_LEN);
    lock.lock();
    transCB = createTransCB(this, nodeRole, nullptr);
    lock.unlock();
    // pthread_create(&transUpdaterThread, NULL, TransUpdateLoop, this);
    // pthread_create(&onNewSessThread, NULL, onNewSess, this);
    return;
}

int IntcpSess::inputUDP(char *recvBuf, int recvLen)
{
    IUINT32 bf = _getMillisec();
    lock.lock();
    IUINT32 af = _getMillisec();
    if (af - bf > 10)
    {
        LOG(TRACE, "input wait %d", af - bf);
    }
    IUINT32 cf = _getUsec();
    int ret = transCB->input(recvBuf, recvLen);
    IUINT32 df = _getUsec();
    input_time += ((double)(df - cf)) / 1000000;
    if (df - cf > 500)
    {
        LOG(TRACE, "input use %d", df - cf);
    }

    lock.unlock();
    sleep(0);
    return ret;
}

int IntcpSess::input2Host(char *recvBuf, int recvLen)
{
    IUINT32 bf = _getMillisec();
    lock.lock();
    IUINT32 af = _getMillisec();
    if (af - bf > 10)
    {
        LOG(TRACE, "input wait %d", af - bf);
    }
    IUINT32 cf = _getUsec();
    int ret = transCB->inputForHost(recvBuf, recvLen);
    IUINT32 df = _getUsec();
    input_time += ((double)(df - cf)) / 1000000;
    if (df - cf > 500)
    {
        LOG(TRACE, "input use %d", df - cf);
    }

    lock.unlock();
    sleep(0);
    return ret;
}

int IntcpSess::request(int rangeStart, int rangeEnd)
{
    lock.lock();
#ifdef HBH_CC
    int ret = transCB->request(rangeStart, rangeEnd);
#else
    int ret = transCB->request(rangeStart, rangeEnd, 0, 0);
#endif
    lock.unlock();
    return ret;
}

int IntcpSess::recvData(char *recvBuf, int maxBufSize, IUINT32 *startPtr, IUINT32 *endPtr)
{
    IUINT32 bf = _getMillisec();
    lock.lock();
    IUINT32 af = _getMillisec();
    if (af - bf > 10)
    {
        LOG(TRACE, "recv wait %d", af - bf);
    }
    IUINT32 cf = _getMillisec();
    int ret = transCB->recv(recvBuf, maxBufSize, startPtr, endPtr);
    IUINT32 df = _getMillisec();
    if (df - cf > 3)
    {
        LOG(DEBUG, "recv use %d", df - cf);
    }
    lock.unlock();
    return ret;
}

void IntcpSess::insertData(const char *sendBuf, int start, int end)
{
    // transCB->send(sendBuf,end-start);
    int ret = cachePtr->insert(nameChars, start, end, sendBuf);
    assert(ret == 0);
    // WARNING: input -> parseInt -> onUnsatInt -> insertData, lock is occupied by input()
    //  lock.lock();
    transCB->notifyNewData(sendBuf, start, end);
    // lock.unlock();
}

void *TransUpdateLoop(void *args)
{
    IntcpSess *sessPtr = (IntcpSess *)args;

    IUINT32 now, updateTime;

    while (1)
    {
        IUINT32 bf = _getMillisec();
        sessPtr->lock.lock();
        IUINT32 af = _getMillisec();
        if (af - bf > 10)
        {
            LOG(DEBUG, "update wait %d", af - bf);
        }
        updateTime = sessPtr->transCB->check();
        now = _getMillisec();
        if (updateTime <= now)
        {
            IUINT32 cf = _getUsec();
            sessPtr->transCB->update();
            IUINT32 df = _getUsec();
            if (df - cf > 3000)
            {
                LOG(TRACE, "update use %d", df - cf);
            }
            update_time += ((double)(df - cf)) / 1000000;
            sessPtr->lock.unlock();
            sleep(0);
        }
        else
        {
            sessPtr->lock.unlock();
            usleep((updateTime - now) * 1000);
        }
    }
    return nullptr;
}
shared_ptr<IntcpTransCB> createTransCB(const IntcpSess *sessPtr, int nodeRole, int (*onUnsatInt)(IUINT32 start, IUINT32 end, void *user))
{

    // set transCB paramaters
    //  transCB->setNoDelay(1, 5, 2, 1);
    //  transCB->setWndSize(10,128);
    //  transCB->setMtu(20);
    return shared_ptr<IntcpTransCB>(new IntcpTransCB((void *)sessPtr, udpSend, send2host, fetchData, onUnsatInt, nodeRole));
}

int udpSend(const char *buf, int len, void *user, int dstRole)
{
    IntcpSess *sess = (IntcpSess *)user;
    if (sess->nodeRole == dstRole)
    {
        LOG(ERROR, "sess->nodeRole == dstRole");
        abort();
        return -1;
    }
    struct sockaddr_in *dstAddrPtr;
    int outputFd;
    if (dstRole == INTCP_ROLE_RESPONDER)
    {
        dstAddrPtr = &sess->responderAddr;
        outputFd = sess->socketFd_toResp;
    }
    else if (dstRole == INTCP_ROLE_REQUESTER)
    {
        // in midnode, udpSend_default send to requester and udpSend_toResp send to responder
        dstAddrPtr = &sess->requesterAddr;
        outputFd = sess->socketFd_toReq;
    }
    else
    {
        LOG(ERROR, "dstRole must be an endpoint");
        abort();
        return -1;
    }
    if (outputFd == -1)
    {
        LOG(ERROR, "outputFd == -1");
        return -1;
    }
    int sendbyte = sendto(outputFd, buf, len, 0,
                          (struct sockaddr *)dstAddrPtr, AddrLen);

    char recvIP[25];
    writeIPstr(recvIP, dstAddrPtr->sin_addr.s_addr);
    LOG(TRACE, "send %d bytes to %s:%d", len, recvIP, ntohs(dstAddrPtr->sin_port));
    return sendbyte;
}

int send2host(const char *buf, int len, void *user)
{
    IntcpSess *sess = (IntcpSess *)user;
    if (sess->tunFd_toHost == -1)
    {
        LOG(ERROR, "sess->tunFd_toHost == -1");
        return -1;
    }
    struct IntcpSeg *seg = (struct IntcpSeg *)buf;
    // remove kcp header (ip package)
    int nwrite = write(sess->tunFd_toHost, seg->data, seg->len);

    LOG(TRACE, "send %d bytes to Host(tunFd: %d)", seg->len, sess->tunFd_toHost);
    return nwrite;
}

int fetchData(char *buf, IUINT32 start, IUINT32 end, void *user)
{
    IntcpSess *sess = (IntcpSess *)user;
    int readlen = sess->cachePtr->read(sess->nameChars, start, end, buf);
    return readlen;
}

/***************** multi-session management *****************/

bool addrCmp(struct sockaddr_in addr1, struct sockaddr_in addr2)
{
    return (addr1.sin_addr.s_addr == addr2.sin_addr.s_addr) && (addr1.sin_port == addr2.sin_port);
}

void *udpRecvLoop(void *_args)
{
    struct udpRecvLoopArgs *args = (struct udpRecvLoopArgs *)_args;
    char recvBuf[1500]; // for UDP, 1500 is proper
    int recvLen;

    // first, create a socket for listening
    int listenFd;
    if (args->listenFd == -1)
    {
        listenFd = createSocket(
            args->listenAddr.sin_addr.s_addr, args->listenAddr.sin_port, false, nullptr);
    }
    else
    {
        listenFd = args->listenFd;
    }

    // prepare for udp recv
    struct sockaddr_in sendAddr, recvAddr;
    struct sockaddr_in requesterAddr;
    struct sockaddr_in responderAddr;
    // struct sockaddr_in &requesterAddr= sendAddr;
    // struct sockaddr_in &responderAddr= recvAddr;
    char cmbuf[100];

    struct iovec iov;
    iov.iov_base = recvBuf;
    iov.iov_len = sizeof(recvBuf) - 1;
    struct msghdr mhdr;
    mhdr.msg_name = &sendAddr;
    mhdr.msg_namelen = AddrLen;
    mhdr.msg_control = cmbuf;
    mhdr.msg_controllen = 100;
    mhdr.msg_iovlen = 1;
    mhdr.msg_iov = &iov;

    shared_ptr<IntcpSess> sessPtr;
    IUINT32 lastLoop = -1, timeSum1 = 0, timeSum2 = 0, timeSum3 = 0, timeTmp;

    int recvedUDPlen = 0;
    while (1)
    {
        // timeTmp = _getMillisec();
        // if(timeTmp-lastLoop > 1000){
        //     LOG(DEBUG,"udp %d",recvedUDPlen/1024/1024);
        //     lastLoop = timeTmp;
        // }

        // int recvLen = recvfrom(
        //     listenFd,
        //     recvBuf,sizeof(recvBuf),
        //     MSG_DONTWAIT,
        //     (struct sockaddr*)&recvAddr, // for server, get remote addr here
        //     nullptr
        // );
        IUINT32 cf = _getUsec();
        recvLen = recvmsg(listenFd, &mhdr, 0);
        IUINT32 df = _getUsec();
        udp_recv_time += ((double)(df - cf)) / 1000000;
        for (struct cmsghdr *cmsg = CMSG_FIRSTHDR(&mhdr); cmsg != NULL; cmsg = CMSG_NXTHDR(&mhdr, cmsg))
        {
            if (cmsg->cmsg_level != SOL_IP || cmsg->cmsg_type != IP_ORIGDSTADDR)
                continue;
            memcpy(&recvAddr, CMSG_DATA(cmsg), sizeof(struct sockaddr_in));
        }
        LOG(TRACE, "recv udp len=%d", recvLen);
        recvedUDPlen += recvLen;

        // DEBUG
        //  IUINT8 cmd;
        //  decode8u(recvBuf, &cmd);
        //  if(cmd == INTCP_CMD_HOP_RTT_TELL){
        //      IUINT32 tsInPkt;
        //      decode32u(recvBuf+3, &tsInPkt);
        //      LOG(DEBUG,"delta: %u",_getMillisec()-tsInPkt);
        //  }

        // now we get: data in recvBuf, recvLen, sendAddr, recvAddr
        //
        bool isEndp = addrCmp(recvAddr, args->listenAddr);
        int segDstRole = IntcpTransCB::judgeSegDst(recvBuf, recvLen);
        if (segDstRole == INTCP_ROLE_RESPONDER)
        {
            requesterAddr = sendAddr;
            responderAddr = recvAddr;
        }
        else if (segDstRole == INTCP_ROLE_REQUESTER)
        {
            requesterAddr = recvAddr;
            responderAddr = sendAddr;
        }
        else
        {
            LOG(WARN, "recv not-INTCP packet");
            // TODO dst of some pkts can be midnode in future.
            continue;
        }

        Quad quad(requesterAddr, responderAddr);

        int ret = args->sessMapPtr->readValue(quad.chars, QUAD_STR_LEN, &sessPtr);
        if (ret == -1)
        {
            // if the endpoint receives a intcp DATA packet from unknown session, ignores it.
            if (isEndp && segDstRole == INTCP_ROLE_REQUESTER)
            {

                LOG(WARN, "requester recvs an unknown packet");
                continue;
            }
            // if not exist, create one.
            char sendIPstr[25];
            writeIPstr(sendIPstr, sendAddr.sin_addr.s_addr);
            LOG(TRACE, "establish: %s:%d", sendIPstr, ntohs(sendAddr.sin_port));
            if (isEndp)
            {
                // new responder session
                // TODO when to release session?
                sessPtr = shared_ptr<IntcpSess>(new IntcpSess(quad, listenFd, args->cachePtr, args->onNewSess, args->onUnsatInt));
            }
            else
            {
                // new midnode session
                sessPtr = shared_ptr<IntcpSess>(new IntcpSess(quad, args->cachePtr, args->onNewSess));
            }
            // nodeRole=server
            args->sessMapPtr->setValue(quad.chars, QUAD_STR_LEN, sessPtr);
        }
        sessPtr->inputUDP(recvBuf, recvLen);
        lastLoop = _getUsec();
        if (lastLoop - timeTmp > 1000000)
        {
            LOG(SILENT, "udp_recv_time %.2fs update_time %.2fs input_time %.2fs", udp_recv_time, update_time, input_time);
            timeTmp = _getUsec();
        }
        // lastLoop = _getUsec();
    }

    return nullptr;
}

int GSsendFunc(shared_ptr<IntcpSess> sess, char *buffer, int buflen, int listenFd)
{
    int len = buflen, tot = 0, nwrite;
    char *pt = buffer;
    while (len > 0)
    {
        int size = len > (int)INTCP_MSS ? (int)INTCP_MSS : len;
        shared_ptr<IntcpSeg> seg = IntcpTransCB::createSeg(size);
        assert(seg);
        if (seg == NULL)
        {
            printf("create seg error.\n");
            return -1;
        }
        if (pt && len > 0)
        {
            // LOG(DEBUG,"memcpy size %d",size);
            memcpy(seg->data, pt, size);
        }
        seg->cmd = INTCP_CMD_PUSH;
        seg->len = size;
        seg->rangeStart = sess->packetId;
        seg->rangeEnd = sess->packetId + size;
        seg->wnd = 0;
        seg->ts = 0;
        // TODO: influenced by interest
        // sessPtr->inputUDP((char *)segbuf, size + INTCP_OVERHEAD);
        char sndbuftmp[INTCP_MTU];
        memcpy(sndbuftmp, seg.get(), INTCP_OVERHEAD);
        memcpy(sndbuftmp + INTCP_OVERHEAD, seg->data, seg->len);
        // nwrite = write(listenFd, sndbuftmp, INTCP_OVERHEAD+seg->len);
        struct sockaddr_in *dstAddrPtr = &sess->requesterAddr;
        nwrite = sendto(listenFd, sndbuftmp, INTCP_OVERHEAD + seg->len, 0,
                        (struct sockaddr *)dstAddrPtr, AddrLen);
        if (nwrite == -1)
        {
            LOG(ERROR, "write to listenFd error: %d.\n", errno);
            return tot;
        }
        sess->packetId += size;
        pt += size;
        len -= size;
        tot += nwrite;
    }
    return tot;
}

int GSrecvFunc(char *data, int buflen, int tunFd)
{
    int tot = 0, nwrite;
    IUINT32 ts, sn, len;
    IUINT32 rangeStart, rangeEnd; // intcp
    IINT16 wnd;
    IUINT8 cmd;
    shared_ptr<IntcpSeg> seg;
    char *dataOrg = data;
    int size = buflen;
    while (1)
    {
        if (size < (int)INTCP_OVERHEAD)
            break;
        data = decode8u(data, &cmd);
        data = decode16(data, &wnd);
        data = decode32u(data, &ts);
        data = decode32u(data, &sn);
        data = decode32u(data, &len);
        // if(len+INTCP_OVERHEAD<size){
        //     LOG(WARN, "input size %d > seg size %d",size,len+INTCP_OVERHEAD);
        // }
        data = decode32u(data, &rangeStart);
        data = decode32u(data, &rangeEnd);
        size -= INTCP_OVERHEAD;

        if ((long)size < (long)len || (int)len < 0)
        {
            printf("ERROR: GS recv wrong package.\n");
            return tot;
        }

        if (cmd != INTCP_CMD_PUSH && cmd != INTCP_CMD_INT)
        {
            printf("ERROR: GS recv wrong package.\n");
            return tot;
        }

        seg = IntcpTransCB::createSeg(len);
        seg->cmd = cmd;
        seg->wnd = wnd;
        seg->ts = ts;
        seg->sn = sn;
        seg->len = len;
        seg->rangeStart = rangeStart;
        seg->rangeEnd = rangeEnd;
        if (len > 0)
        {
            memcpy(seg->data, data, len);
            size -= len;

            nwrite = write(tunFd, seg->data, seg->len);
            if (nwrite == -1)
            {
                LOG(ERROR, "write to tunFd error: %d.\n", errno);
                return -1;
            }
            tot += len;
        }
    }
    return tot;
}

void *GSudpRecvLoop(void *_args)
{
    struct GSudpRecvLoopArgs *args = (struct GSudpRecvLoopArgs *)_args;
    char recvBuf[1500]; // for UDP, 1500 is proper
    int nread, nwrite;
    int recvLen;
    unsigned long int tun_count = 0, nic_count = 0;
    char buffer[BUFSIZE];

    // first, check tunFd & listenFd
    int tunFd = args->tunFd, listenFd = args->listenFd, maxFd;
    if (tunFd == -1 || listenFd == -1)
    {
        LOG(ERROR, "Fd error.\n");
        return nullptr;
    }

    // prepare for udp recv
    struct sockaddr_in sendAddr, recvAddr;
    struct sockaddr_in requesterAddr;
    struct sockaddr_in responderAddr;
    // struct sockaddr_in &requesterAddr= sendAddr;
    // struct sockaddr_in &responderAddr= recvAddr;
    char cmbuf[100];

    struct iovec iov;
    iov.iov_base = recvBuf;
    iov.iov_len = sizeof(recvBuf) - 1;
    struct msghdr mhdr;
    mhdr.msg_name = &sendAddr;
    mhdr.msg_namelen = AddrLen;
    mhdr.msg_control = cmbuf;
    mhdr.msg_controllen = 100;
    mhdr.msg_iovlen = 1;
    mhdr.msg_iov = &iov;

    shared_ptr<IntcpSess> sessPtr;
    IUINT32 lastLoop = -1, timeSum1 = 0, timeSum2 = 0, timeSum3 = 0, timeTmp;

    maxFd = (tunFd > listenFd) ? tunFd : listenFd;
    while (1)
    {
        int ret;
        fd_set rd_set;

        FD_ZERO(&rd_set);
        FD_SET(listenFd, &rd_set);
        FD_SET(tunFd, &rd_set);

        ret = select(maxFd + 1, &rd_set, NULL, NULL, NULL);
        if (ret < 0 && errno == EINTR)
        {
            continue;
        }

        if (ret < 0)
        {
            perror("select()");
            goto quit;
        }

        // Process data received from tun
        //=========================================
        if (FD_ISSET(tunFd, &rd_set))
        {
            // data from tun: just read it and write it to the network
            // responder
            if ((nread = read(tunFd, buffer, BUFSIZE)) < 0)
            {
                LOG(ERROR, "Read from tun error.\n");
                goto quit;
            }
            else if (nread == 0)
            {
                // Do nothing.
            }
            else if (nread > sizeof(struct iphdr))
            {
                struct iphdr *ipheader = (iphdr *)buffer;
                char src_ip[20];
                char dst_ip[20];
                writeIPstr(src_ip, ipheader->saddr);
                writeIPstr(dst_ip, ipheader->daddr);
                LOG(TRACE, "tunFd data: %s->%s\n", src_ip, dst_ip);
                // if (ipheader->saddr != 0 && ipheader->daddr == inet_addr("10.0.100.2"))
                if (ipheader->saddr != 0)
                {
                    LOG(INFO, "Read %d bytes from tunFd\n", nread);
                    tun_count++;
                    // set the session
                    sessPtr = args->sessPtrGo;
                    if (sessPtr->nodeRole != INTCP_ROLE_RESPONDER)
                    {
                        LOG(ERROR, "nodeRole error.\n");
                        goto quit;
                    }
                    if (GSsendFunc(sessPtr, buffer, nread, listenFd) < nread)
                    {
                        LOG(ERROR, "send data to listenFd error.\n");
                        goto quit;
                    }
                }
            }
        }
        // Process data received from NIC
        //=========================================
        if (FD_ISSET(listenFd, &rd_set))
        {
            // data from physical nic, read it and display the IP header
            // requester
            struct sockaddr_in *srcAddrPtr;
            socklen_t src_len = sizeof(srcAddrPtr);
            if ((nread = recvfrom(listenFd, buffer, BUFSIZE, 0, (struct sockaddr *)srcAddrPtr, &src_len)) < 0)
            {
                LOG(ERROR, "Read from nic error.\n");
                goto quit;
            }
            else if (nread == 0)
            {
                // Do nothing.
            }
            // now buffer[] contains a full packet or frame
            LOG(INFO, "Read %d bytes from listenFd\n", nread);
            buffer[nread] = 0;
            nic_count++;
            /*
            recvLen = recvmsg(listenFd, &mhdr, 0);
            for (struct cmsghdr *cmsg = CMSG_FIRSTHDR(&mhdr); cmsg != NULL; cmsg = CMSG_NXTHDR(&mhdr, cmsg))
            {
                if (cmsg->cmsg_level != SOL_IP || cmsg->cmsg_type != IP_ORIGDSTADDR)
                    continue;
                memcpy(&recvAddr, CMSG_DATA(cmsg), sizeof(struct sockaddr_in));
            }
            LOG(TRACE, "recv udp len=%d", recvLen);
            // now we get: data in recvBuf, recvLen, sendAddr, recvAddr

            sessPtr = args->sessPtrBack;
            if (sessPtr->nodeRole != INTCP_ROLE_REQUESTER)
            {
                LOG(ERROR, "nodeRole error.\n");
                goto quit;
            }

            bool isEndp = addrCmp(recvAddr, args->listenAddr);
            int segDstRole = IntcpTransCB::judgeSegDst(recvBuf, recvLen);
            if (segDstRole == INTCP_ROLE_RESPONDER)
            {
                requesterAddr = sendAddr;
                responderAddr = recvAddr;
            }
            else if (segDstRole == INTCP_ROLE_REQUESTER)
            {
                requesterAddr = recvAddr;
                responderAddr = sendAddr;
            }
            else
            {
                LOG(WARN, "recv not-INTCP packet");
                // TODO dst of some pkts can be midnode in future.
                continue;
            }

            Quad quad(requesterAddr, responderAddr);

            int ret = args->sessMapPtr->readValue(quad.chars, QUAD_STR_LEN, &sessPtr);
            if (ret == -1)
            {
                // if the endpoint receives a intcp DATA packet from unknown session, ignores it.
                if (isEndp && segDstRole == INTCP_ROLE_REQUESTER)
                {

                    LOG(WARN, "requester recvs an unknown packet");
                    continue;
                }
                continue;
            }
            */

            // remove kcp header and send data to host
            // sessPtr->input2Host(recvBuf, recvLen);
            if (GSrecvFunc(buffer, nread, tunFd) < 0)
            {
                LOG(ERROR, "send data to host error.\n");
                goto quit;
            }
        }
    }
quit:

    if (listenFd > 0)
        close(listenFd);
    if (tunFd > 0)
        close(tunFd);
    printf("Read data from tunFd %d: %lu, from listenFd %d: %lu.\n",
           tunFd, tun_count, listenFd, nic_count);
    printf("quit!\n");
    return nullptr;
}
