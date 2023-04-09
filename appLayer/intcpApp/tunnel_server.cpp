#include "../../intcp/include/api.h"
#include "config.h"
#include <string.h>
#include <sys/time.h>
#undef LOG_LEVEL
#define LOG_LEVEL DEBUG

void *onNewSess(void* _sessPtr){
    return nullptr;
}

int main(){
    char tun_name[IFNAMSIZ];
    int tunFd;
    strcpy(tun_name, "servertun");
    tunFd = tun_alloc(tun_name, IFF_TUN | IFF_NO_PI);  /* tun interface */

    system("ifconfig servertun mtu 1472 up 10.0.101.1 netmask 255.255.255.0");
    system("echo 1 | dd of=/proc/sys/net/ipv4/ip_forward");
    system("route del default");
    system("route del -net 10.0.1.0/24 dev gs2_m1");
    system("route add -host 10.0.1.2 gw 10.0.3.1 dev gs2_m1");
    system("route add default gw 10.0.101.2 servertun");

    flushBeforeExit();
    Cache cache(QUAD_STR_LEN);
    ByteMap<shared_ptr<IntcpSess>> sessMap;
    LOG(INFO,"entering intcps");
    fflush(stdout);
    startGSnode(&cache, &sessMap, onNewSess,
            "10.0.100.1", DEFAULT_SERVER_PORT, "10.0.1.2", DEFAULT_CLIENT_PORT, tunFd);
    return 0;
}
