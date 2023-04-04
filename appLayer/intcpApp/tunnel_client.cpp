#include "../../intcp/include/api.h"
#include <unistd.h>
#include "config.h"
#include <thread>
#include <sys/time.h>
#include <netinet/ip.h>
#include <netinet/udp.h>
#include <arpa/inet.h>
//#include <getopt.h>
#undef LOG_LEVEL
#define LOG_LEVEL DEBUG

char clientAddr[20] = "10.0.1.2";

IUINT32 _round_up(IUINT32 x,IUINT32 y){
    return ((x+y-1)/y)*y;
}

void request_func(IntcpSess * _sessPtr){
    int sendStart = 0, ret;
    while(1){
#ifdef FLOW_TEST
        if(sendStart > TOTAL_DATA_LEN)
            break;
#endif
        ret = _sessPtr->request(sendStart, sendStart+REQ_LEN);
        if(ret == -1){// intBuf is full
            LOG(TRACE,"intBuf is full");
        } else {
            LOG(TRACE,"request range [%d,%d)",sendStart,sendStart+REQ_LEN);
            sendStart += REQ_LEN;
        }
        usleep(1000*REQ_INTV);
    }
}

void *onNewSess(void* _sessPtr){
    IntcpSess *sessPtr = (IntcpSess*)_sessPtr;

    thread t(request_func,sessPtr);
    t.detach();
    
    int ret;
    char recvBuf[MaxBufSize];
    IUINT32 start,end;
    IUINT32 rcn=0;
    IUINT32 printTime = 0, startTime = _getMillisec();
    IUINT32 recvedBytes = 0;         //bytes
    const IUINT32 CheckInterval = 1000;

    int loops = 0;
    //DEBUG 1->0
    while(1){
        usleep(10);//sleep 0.01ms
        
        ret = sessPtr->recvData(recvBuf,MaxBufSize,&start,&end);
        if(ret==0)
            recvedBytes += (end-start);
        IUINT32 curTime = _getMillisec();
        if(printTime==0||curTime-printTime>CheckInterval){
            if(printTime!=0){
                //NOTE
                // printf("%4ds %.2f Mbits/sec receiver\n",
                //         int((curTime - startTime)/1000),
                //         bytesToMbit(recvedBytes)*1000/(curTime-printTime)
                // );
            }
            recvedBytes = 0;
            printTime = curTime;
        }
        if(ret<0)
            continue;
        recvBuf[end-start]='\0';
        
        
        IUINT32 pos = _round_up(start,REQ_LEN);
        while(1){
            if(pos+sizeof(IUINT32)*2>end)
                break;
            //LOG(TRACE,"%d %d %d\n",pos,start,end);
            IUINT32 sendTime = *((IUINT32 *)(recvBuf+pos-start));
            IUINT32 xmit = *((IUINT32 *)(recvBuf+pos-start+sizeof(IUINT32)));
            IUINT32 recvTime = *((IUINT32 *)(recvBuf+pos-start+sizeof(IUINT32)*2));
            IUINT32 firstTs = *((IUINT32 *)(recvBuf+pos-start+sizeof(IUINT32)*3));
            curTime = _getMillisec();
            // LOG(TRACE, "recv [%d,%d)\n", start, end);

            // if(recvTime<1000){
            //LOG(TRACE,"recv [%d,%d) xmit %u intcpRtt %u owd_noOrder %u sendTime %u recvTime %u curTime %u owd_obs %u\n",pos,pos+REQ_LEN,xmit,recvTime-firstTs,recvTime-sendTime,sendTime,recvTime,curTime, curTime-sendTime);
                // abort();
            // }
            fflush(stdout);
            pos += REQ_LEN;
        }
    }
    return nullptr;
}

int main(int argc,char** argv){
    int ch;
    
    while((ch=getopt(argc,argv,"c:"))!=-1){
        switch(ch){
            case 'c':
                strncpy(clientAddr,optarg,19);
                break;
            default:
                printf("unkown option\n");
                break;
        }
    }

    char tun_name[IFNAMSIZ];
    int tunFd;
    strcpy(tun_name, "tun_gs1");
    tunFd = tun_alloc(tun_name, IFF_TUN | IFF_NO_PI);  /* tun interface */

    system("ifconfig clienttun mtu 1472 up 10.0.0.1 netmask 255.255.255.0");
    system("route del default");
    system("route add -host 10.0.100.1 gw 10.0.2.2 dev gs1_m1");
    system("route add default gw 10.0.0.2 clienttun");

    flushBeforeExit();
    Cache cache(QUAD_STR_LEN);
    ByteMap<shared_ptr<IntcpSess>> sessMap;
    LOG(INFO,"entering intcptc\n");
    LOG(INFO,"client ip:%s\n",clientAddr);
    startGSRequester(&cache,&sessMap,onNewSess,
        (const char*)clientAddr,"10.0.100.1",DEFAULT_SERVER_PORT,tunFd);
    return 0;
}
