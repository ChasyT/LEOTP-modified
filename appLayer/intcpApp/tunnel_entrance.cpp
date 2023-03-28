#include "../../intcp/include/api.h"

#undef LOG_LEVEL
#define LOG_LEVEL DEBUG


#include <netinet/ip.h>
#include <netinet/udp.h>
#include <arpa/inet.h>

int main(){
    int tun_fd,nread;
    unsigned char buffer[2000];
    char src_ip[20];
    char dst_ip[20];
    uint16_t src_port;
    uint16_t dst_port;
    struct iphdr*  ipheader;
    sockaddr_in serverAddr;
    char tun_name[IFNAMSIZ];
    
    /* Connect to the device */
    strcpy(tun_name, "tun77");
    tun_fd = tun_alloc(tun_name, IFF_TUN | IFF_NO_PI);  /* tun interface */
    int sockfd = -1;
    if(tun_fd < 0){
        perror("Allocating interface");
        exit(1);
    }

    system("ifconfig tun77 mtu 1472 up 10.0.0.1 netmask 255.255.255.0");
    system("route del default");
    system("route add -host 10.0.100.1 gw 10.0.2.2 dev gs1_m1");
    system("route add default gw 10.0.0.2 tun77");

    /* Now read data coming from the kernel */
    while(1) {
        /* Note that "buffer" should be at least the MTU size of the interface, eg 1500 bytes */
        nread = read(tun_fd,buffer,sizeof(buffer));
        if(nread < 0) {
            perror("Reading from interface");
            close(tun_fd);
            exit(1);
        }
        ipheader = (iphdr*) buffer;
        writeIPstr(src_ip,ipheader->saddr);
        writeIPstr(dst_ip,ipheader->daddr);
        printf("%s->%s\n",src_ip,dst_ip);
        if(ipheader->saddr!=0){
            if(sockfd==-1){
                sockfd = open_udp_client_socket("10.0.100.1", 8765, &serverAddr);
            }
            sendto(sockfd,buffer,nread,0,(struct sockaddr*)&serverAddr,sizeof(serverAddr));
        }
        /* Do whatever with the data */
        printf("Read %d bytes from device %s\n", nread, tun_name);
    }
}
