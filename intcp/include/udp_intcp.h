#ifndef __UDP_INTCP_H__
#define __UDP_INTCP_H__

#include "ikcp.h"
#include "ByteMap.h"
#include "cache.h"
#include "tunnel.h"

#include <arpa/inet.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#include <cstring>
#include <mutex>
#include <iostream>
#include <thread>



#define QUAD_STR_LEN 12 //4+2+4+2

#define DEFAULT_SERVER_PORT 5000
#define DEFAULT_MID_PORT 6000
#define DEFAULT_CLIENT_PORT 7000
#define REUSE_PORT_RANGE 1000
#define BUFSIZE 2048

using namespace std;

const int MaxBufSize = 3000;
const socklen_t AddrLen = (socklen_t)(sizeof(struct sockaddr_in));

/***************** util functions *****************/

struct sockaddr_in toAddr(in_addr_t IP, uint16_t port);
bool addrCmp(struct sockaddr_in addr1, struct sockaddr_in addr2);
void writeIPstr(char *ret, in_addr_t address);

int createSocket(in_addr_t IP, uint16_t port, bool reusePort, uint16_t *finalPort);

/***************** INTCP session *****************/

class Quad
{
public:
    in_addr_t reqAddrIP;
    uint16_t reqAddrPort;
    in_addr_t respAddrIP;
    uint16_t respAddrPort;
    
    char chars[QUAD_STR_LEN];
    Quad(in_addr_t _reqAddrIP, uint16_t _reqAddrPort, in_addr_t _respAddrIP, uint16_t _respAddrPort);
    Quad(struct sockaddr_in requesterAddr, struct sockaddr_in responderAddr);
    Quad reverse();
    void toChars();
    struct sockaddr_in getReqAddr();
    struct sockaddr_in getRespAddr();

    bool operator == (Quad const& quad2) const;
};
class IntcpSess{
public:
    int socketFd_toReq, socketFd_toResp, tunFd_toHost, packetId;
    struct sockaddr_in requesterAddr, responderAddr;
    char nameChars[QUAD_STR_LEN];
    int nodeRole;
    shared_ptr<IntcpTransCB> transCB;
    // IntcpTransCB *transCB_resp;
    Cache *cachePtr;
    mutex lock;
    pthread_t transUpdaterThread, onNewSessThread;
    // pthread_t TransUpdater_resp;

    //requester
    IntcpSess(in_addr_t reqAddrIP, in_addr_t respAddrIP, 
        uint16_t respAddrPort, Cache* _cachePtr,
        void *(*onNewSess)(void* _sessPtr));
    //responder
    IntcpSess(Quad quad, int listenFd, Cache* _cachePtr,
        void *(*onNewSess)(void* _sessPtr),int (*onUnsatInt)(IUINT32 start, IUINT32 end, void *user));
    //midnode
    IntcpSess(Quad quad, Cache* _cachePtr,
        void *(*onNewSess)(void* _sessPtr));
    //GSnode
    IntcpSess(Quad quad, int _nodeRole, Cache *_cachePtr,
        void *(*onNewSess)(void *_sessPtr));
    
    int inputUDP(char *recvBuf, int recvLen);
    int input2Host(char *recvBuf, int recvLen);
    int request(int rangeStart, int rangeEnd);
    int recvData(char *recvBuf, int maxBufSize, IUINT32 *startPtr, IUINT32 *endPtr);
    void insertData(const char *sendBuf, int start, int end);
};
void* TransUpdateLoop(void *args);
int udpSend(const char* buf,int len, void* user, int dstRole);
int send2host(const char *buf, int len, void* user);
int fetchData(char *buf, IUINT32 start, IUINT32 end, void *user);
shared_ptr<IntcpTransCB> createTransCB(const IntcpSess *sessPtr, int nodeRole, int (*onUnsatInt)(IUINT32 start, IUINT32 end, void *user));

/***************** multi-session management *****************/


struct udpRecvLoopArgs
{
    ByteMap<shared_ptr<IntcpSess>> *sessMapPtr;
    void* (*onNewSess)(void*);
    int (*onUnsatInt)(IUINT32 start, IUINT32 end, void *user);
    struct sockaddr_in listenAddr;
    int listenFd=-1;
    Cache* cachePtr;
};
void *udpRecvLoop(void *_args);

struct GSudpRecvLoopArgs
{
    ByteMap<shared_ptr<IntcpSess>> *sessMapPtr;
    void* (*onNewSess)(void*);
    int (*onUnsatInt)(IUINT32 start, IUINT32 end, void *user);
    shared_ptr<IntcpSess> sessPtrBack;
    shared_ptr<IntcpSess> sessPtrGo;
    struct sockaddr_in listenAddr;
    int tunFd=-1;
    int listenFd=-1;
    Cache* cachePtr;
};

int GSsendFunc(shared_ptr<IntcpSess> sess, char *buffer, int buflen, int listenFd);
int GSrecvFunc(char *data, int buflen, int tunFd);
void * GSudpRecvLoop(void *_args);

#endif