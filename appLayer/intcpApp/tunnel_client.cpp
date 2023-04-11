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

void *onNewSess(void* _sessPtr){
    return nullptr;
}

int main(int argc,char** argv){
    char tun_name[IFNAMSIZ];
    int tunFd;
    strcpy(tun_name, "clienttun");
    tunFd = tun_alloc(tun_name, IFF_TUN | IFF_NO_PI);  /* tun interface */

    system("ifconfig clienttun mtu 1472 up 10.0.0.1 netmask 255.255.255.0");
    system("route del default");
    system("route add -host 10.0.100.1 gw 10.0.2.2 dev gs1_m1");
    system("route add default gw 10.0.0.2 clienttun");

    flushBeforeExit();
    Cache cache(QUAD_STR_LEN);
    ByteMap<shared_ptr<IntcpSess>> sessMap;
    LOG(INFO,"entering intcptc\n");
    fflush(stdout);
    startGSnode(&cache, &sessMap, onNewSess,
        "10.0.1.2", DEFAULT_CLIENT_PORT, "10.0.100.1", DEFAULT_SERVER_PORT, tunFd);
    return 0;
}
