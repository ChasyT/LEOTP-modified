#ifndef __TUNNEL_H__
#define __TUNNEL_H__

#include <net/if.h>
#include <linux/if_tun.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <arpa/inet.h>
#include <string.h>
#include <unistd.h>

using namespace std;

int tun_alloc(char *dev, int flags); 
int open_udp_client_socket(const char * IP, int port, sockaddr_in* serv);
int tun_write(int tun_fd, char* buffer, int length);

#endif