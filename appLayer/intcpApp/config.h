//define RTT_TEST
//#define FLOW_TEST 
// #define TOTAL_DATA_LEN 300 //bytes
#define TOTAL_DATA_LEN 100000000

#ifdef RTT_TEST
    #define REQ_LEN 16 //bytes per segment
    #define REQ_INTV 5//ms  interval between two request
#else
    #ifdef FLOW_TEST
        #define REQ_INTV 1  //ms  interval between two request
        #define REQ_LEN 10000 //for flow test
    #else
        #define REQ_LEN INTCP_MSS*10 //bytes per segment
        #define REQ_INTV 1  //ms  interval between two request
    #endif
#endif
