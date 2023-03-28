#include "./include/tunnel.h"

int tun_alloc(char *dev, int flags) {
    struct ifreq ifr;
    int fd, err;
    char *clonedev = "/dev/net/tun";

    /* Arguments taken by the function:
     *
     * char *dev: the name of an interface (or '\0'). MUST have enough
     *   space to hold the interface name if '\0' is passed
     * int flags: interface flags (eg, IFF_TUN etc.)
     */
    
     /* open the clone device */
    if( (fd = open(clonedev, O_RDWR)) < 0 ) {
        return fd;
    }
    
    /* preparation of the struct ifr, of type "struct ifreq" */
    memset(&ifr, 0, sizeof(ifr));
    
    ifr.ifr_flags = flags;   /* IFF_TUN or IFF_TAP, plus maybe IFF_NO_PI */
    
    if (*dev) {
        /* if a device name was specified, put it in the structure; otherwise,
         * the kernel will try to allocate the "next" device of the
         * specified type */
        strncpy(ifr.ifr_name, dev, IFNAMSIZ);
    }
    
    /* try to create the device */
    if( (err = ioctl(fd, TUNSETIFF, (void *) &ifr)) < 0 ) {
        close(fd);
        return err;
    }
    
    /* if the operation was successful, write back the name of the
     * interface to the variable "dev", so the caller can know
     * it. Note that the caller MUST reserve space in *dev (see calling
     * code below) */
    strcpy(dev, ifr.ifr_name);
    
    /* this is the special file descriptor that the caller will use to talk
     * with the virtual interface */
    return fd;
}

int open_udp_client_socket(const char * IP, int port, sockaddr_in* serv){
    int sockfd = -1;
    if((sockfd=socket(AF_INET,SOCK_DGRAM,0))<0){
        return -1;
    }
    memset(serv, 0, sizeof(*serv));
    serv->sin_family = AF_INET;
    serv->sin_port = htons(port);
    //(serv->sin_addr).s_addr = IP;
    inet_pton(AF_INET, IP ,&((serv->sin_addr).s_addr));
    return sockfd;
}

int tun_write(int tun_fd, char* buffer, int length){
    int bytes_written;
    bytes_written = write(tun_fd, buffer, length);
    return bytes_written;
}