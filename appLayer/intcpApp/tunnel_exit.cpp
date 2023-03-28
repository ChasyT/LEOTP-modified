#include "../../intcp/include/api.h"
#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <string.h>
#include <arpa/inet.h>

int main(int argc, const char* argv[])
{
    // 创建套接字
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    int tun_fd;
    char tun_name[IFNAMSIZ];
    if(fd == -1)
    {
        perror("socket error");
        exit(1);
    }
    // fd绑定本地的IP和端口
    strcpy(tun_name,"tun77");
    tun_fd = tun_alloc(tun_name, IFF_TUN | IFF_NO_PI);
    if(tun_fd < 0){
        perror("Allocating interface");
        exit(1);
    }

    struct sockaddr_in serv;
    memset(&serv, 0, sizeof(serv));
    serv.sin_family = AF_INET;
    serv.sin_port = htons(8765);
    serv.sin_addr.s_addr = htonl(INADDR_ANY);
    int ret = bind(fd, (struct sockaddr*)&serv, sizeof(serv));
    if(ret == -1)
    {
        perror("bind error");
        exit(1);
    }

    struct sockaddr_in client;
    socklen_t cli_len = sizeof(client);
    // 通信
    char buf[2000] = {0};

    system("ifconfig tun77 mtu 1472 up 10.0.0.1 netmask 255.255.255.0");
    system("echo 1 | dd of=/proc/sys/net/ipv4/ip_forward");

    while(1)
    {
        int recvlen = recvfrom(fd, buf, sizeof(buf), 0, 
                               (struct sockaddr*)&client, &cli_len);
        if(recvlen == -1)
        {
            perror("recvform error");
            exit(1);
        }
        /*
        printf("recv buf: %s\n", buf);
        char ip[64] = {0};
        printf("New Client IP: %s, Port: %d\n",
            inet_ntop(AF_INET, &client.sin_addr.s_addr, ip, sizeof(ip)),
            ntohs(client.sin_port));
        */
        // 给客户端发送数据
        //sendto(fd, buf, strlen(buf)+1, 0, (struct sockaddr*)&client, sizeof(client));
        tun_write(tun_fd, buf, recvlen);
    }
    close(fd);
    return 0;
}