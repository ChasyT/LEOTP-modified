#!/bin/bash
cd `dirname $0`
INTCP="../../intcp"
echo "start making..."
g++ -c ${INTCP}/*.cpp -lpthread -g -std=c++11
echo "making intcps"
g++ intcp_server.cpp *.o -o intcps -lpthread -g -std=c++11
echo "making intcpm"
g++ intcp_mid.cpp    *.o -o intcpm -lpthread -g -std=c++11
echo "making intcpc"
g++ intcp_client.cpp *.o -o intcpc -lpthread -g -std=c++11
echo "making intcptc"
g++ tunnel_client.cpp *.o -o intcptc -lpthread -g -std=c++11
echo "making intcpts"
g++ tunnel_server.cpp *.o -o intcpts -lpthread -g -std=c++11
echo "finished."
rm *.o

# -g is for gdb
# https://blog.csdn.net/qq_41006901/article/details/90699486
