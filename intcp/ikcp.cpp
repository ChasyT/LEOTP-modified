#include "./include/ikcp.h"
#undef LOG_LEVEL
#define LOG_LEVEL SILENT // SILENT//

#include <iostream>
using namespace std;

//---------------------------------------------------------------------
// create a new IntcpTransCB
//---------------------------------------------------------------------
IntcpTransCB::IntcpTransCB(
    void *_user,
    int (*_outputFunc)(const char *buf, int len, void *user, int dstRole),
    int (*_fetchDataFunc)(char *buf, IUINT32 start, IUINT32 end, void *user),
    int (*_onUnsatInt)(IUINT32 start, IUINT32 end, void *user),
    // bool _isUnreliable
    int _nodeRole) : user(_user),
                     outputFunc(_outputFunc),
                     fetchDataFunc(_fetchDataFunc),
                     onUnsatInt(_onUnsatInt),
                     // isUnreliable(_isUnreliable),
                     nodeRole(_nodeRole),
                     dataNextSn(0),
                     intNextSn(0),
                     rcvNxt(0),
                     cwnd(INTCP_CWND_MIN),
                     state(0),
                     srtt(0),
                     rttvar(0),
                     rto(INTCP_RTO_DEF),
                     hopSrtt(0),
                     hopRttvar(0),
                     nextFlushTs(0),
                     updated(0),
                     dataSnRightBound(-1),
                     dataByteRightBound(-1),
                     dataRightBoundTs(-1),
                     intSnRightBound(-1),
                     intByteRightBound(-1),
                     intRightBoundTs(-1),
#ifdef CUT_PAYLOAD
                     dataNextRangeStart(0),
    #ifdef USE_PIT
                     intNextRangeStart(0),
    #endif
#endif
                     ccState(INTCP_CC_SLOW_START),
                     ccDataLen(0),
                     dataOutputLimit(INTCP_MSS),
                     rmt_sndq_rest(INTCP_SNDQ_MAX),
                     sndQueueBytes(0),
                     intHopOwd(-1),
                     rmtSendRate(INTCP_SENDRATE_MIN),
                     intBufBytes(0),
                     lastCwndDecrTs(0),
                     lastThrpUpdateTs(0),
                     recvedBytesThisHRTT(0),
                     recvedBytesLastHRTT(0),
                     hasLossEvent(false),
                     thrpLastPeriod(0),
                     conseqTimeout(0),
                     lastSendIntTs(0),
                     lastFlushTs(0),
                     intOutputLimit(INTCP_SNDQ_MAX) // INTCP_SNDQ_MAX
{
    stat.init();

    void *tmp = malloc(INTCP_MTU * 3);
    assert(tmp != NULL);
    tmpBuffer = shared_ptr<char>(static_cast<char *>(tmp));
}

// allocate a new intcp segment
shared_ptr<IntcpSeg> IntcpTransCB::createSeg(int size)
{
    void *tmp = malloc(sizeof(IntcpSeg) + size);
    assert(tmp != NULL);
    return shared_ptr<IntcpSeg>(static_cast<IntcpSeg *>(tmp));
}

// output segment, size include kcp header
int IntcpTransCB::output(const void *data, int size, int dstRole)
{
    // LOG(DEBUG, "size %d", size-INTCP_OVERHEAD);
    if (size == 0)
        return 0;
    return outputFunc((const char *)data, size, user, dstRole);
}
#ifdef HBH_CC
int IntcpTransCB::outputInt(IUINT32 rangeStart, IUINT32 rangeEnd)
#else
int IntcpTransCB::outputInt(IUINT32 rangeStart, IUINT32 rangeEnd,IUINT16 wnd, IUINT32 ts)
#endif
{
    LOG(TRACE, "output int [%u,%u]", rangeStart, rangeEnd);
    shared_ptr<IntcpSeg> segPtr = createSeg(0);
    // segPtr->len = 0;
    segPtr->cmd = INTCP_CMD_INT;
    segPtr->rangeStart = rangeStart;
    segPtr->rangeEnd = rangeEnd;
    lastSendIntTs = _getMillisec();
#ifdef HBH_CC
    segPtr->ts = lastSendIntTs;
    segPtr->wnd = getDataSendRate();
#else
    if(nodeRole==INTCP_ROLE_REQUESTER){
        segPtr->ts = lastSendIntTs;
        segPtr->wnd = getDataSendRate();
    }
    else{
        segPtr->ts = ts;
        segPtr->wnd = wnd;
    }
#endif
    segPtr->sn = intNextSn++;
    segPtr->len = 0;
    encodeSeg(tmpBuffer.get(), segPtr.get());
    return output(tmpBuffer.get(), INTCP_OVERHEAD, INTCP_ROLE_RESPONDER);
}

//---------------------------------------------------------------------
// encodeSeg
//---------------------------------------------------------------------
char *IntcpTransCB::encodeSeg(char *ptr, const IntcpSeg *seg)
{
    ptr = encode8u(ptr, (IUINT8)seg->cmd);
    ptr = encode16(ptr, seg->wnd);
    ptr = encode32u(ptr, seg->ts);
    ptr = encode32u(ptr, seg->sn);
    ptr = encode32u(ptr, seg->len);

    // intcp
    ptr = encode32u(ptr, seg->rangeStart);
    ptr = encode32u(ptr, seg->rangeEnd);

    return ptr;
}

//---------------------------------------------------------------------
// user/upper level recv: returns size, returns below zero for EAGAIN
//---------------------------------------------------------------------
int IntcpTransCB::recv(char *buffer, int maxBufSize, IUINT32 *startPtr, IUINT32 *endPtr)
{
    // int i=0;
    // for(list<IntcpSeg*>::iterator tmp=rcvQueue.begin(); tmp != rcvQueue.end(); tmp++) {
    //     LOG(DEBUG,"rcvQueue seg %d [%d,%d)",i++,(*tmp)->rangeStart,(*tmp)->rangeEnd);
    // }

    list<shared_ptr<IntcpSeg>>::iterator p;
    shared_ptr<IntcpSeg> seg;

    if (rcvQueue.empty())
        return -1;

    if (nodeRole == INTCP_ROLE_MIDNODE)
    {
        shared_ptr<IntcpSeg> firstSeg = *rcvQueue.begin();
        if (firstSeg->rangeEnd - firstSeg->rangeStart != firstSeg->len)
        {
            LOG(DEBUG, "inconsistent range:rangeStart %u rangeEnd %u length %u", firstSeg->rangeStart, firstSeg->rangeEnd, firstSeg->len);
            rcvQueue.pop_front(); // discard
        }
        else if (firstSeg->len <= maxBufSize)
        {
            *startPtr = firstSeg->rangeStart;
            *endPtr = firstSeg->rangeEnd;
            memcpy(buffer, firstSeg->data, firstSeg->len);
            rcvQueue.pop_front();
        }
        // TODO else split
    }
    else
    {
        // copy seg->data in rcvQueue to buffer as much as possible
        *startPtr = *endPtr = (*rcvQueue.begin())->rangeStart;
        for (p = rcvQueue.begin(); p != rcvQueue.end();)
        {
            seg = *p;
            if (seg->len + *endPtr - *startPtr > maxBufSize)
                break;
            if (*endPtr != seg->rangeStart)
                break;
            memcpy(buffer, seg->data, seg->len);
            buffer += seg->len;
            *endPtr += seg->len;

            rcvQueue.erase(p++);
        }
    }

    moveToRcvQueue();

    return 0;
}

//---------------------------------------------------------------------
// user/upper level send, returns below zero for error
//---------------------------------------------------------------------
int IntcpTransCB::sendData(const char *buffer, IUINT32 start, IUINT32 end)
{
    int len = end - start;
    // if(len>64){
    //     LOG(DEBUG,"%d %d",start,end);
    // }
    shared_ptr<IntcpSeg> seg;

    if (len <= 0)
        return -1;

    while (len > 0)
    {
        int size = len > (int)INTCP_MSS ? (int)INTCP_MSS : len;
        seg = createSeg(size);
        assert(seg);
        if (seg == NULL)
        {
            return -2;
        }
        if (buffer && len > 0)
        {
            // LOG(DEBUG,"memcpy size %d",size);
            memcpy(seg->data, buffer, size);
        }
        seg->cmd = INTCP_CMD_PUSH;
        seg->len = size;
        seg->rangeStart = start;
        seg->rangeEnd = start + size;
        seg->wnd = 0;
        seg->ts = 0;
        start += size;
        sndQueue.push_back(seg);
#ifdef CUT_PAYLOAD
        sndQueueBytes += (INTCP_OVERHEAD+ seg->len);
#else
        sndQueueBytes += seg->len;
#endif
        //if(nodeRole==INTCP_ROLE_RESPONDER)
        LOG(TRACE, "sendData sn %d [%d,%d) ,ts %u, sndQ %u,", seg->sn, seg->rangeStart, seg->rangeEnd,_getMillisec(),sndQueueBytes/INTCP_MSS);
        buffer += size;
        len -= size;
    }

    return 0;
}

// add (rangeStart,rangeEnd) to intQueue
#ifdef HBH_CC
int IntcpTransCB::request(IUINT32 rangeStart, IUINT32 rangeEnd)
#else
int IntcpTransCB::request(IUINT32 rangeStart, IUINT32 rangeEnd, IUINT16 wnd, IUINT32 ts)    //wnd and ts is for midnode
#endif
{
    if (rangeEnd <= rangeStart)
    {
        LOG(WARN, "rangeStart %d rangeEnd %d", rangeStart, rangeEnd);
        return -2;
    }
    if (intBufBytes >= INTCP_INTB_MAX)
    {
        return -1;
    }
    ByteRange intr;
    intr.startByte = rangeStart;
    intr.endByte = rangeEnd;
#ifndef HBH_CC
    intr.wnd = wnd;
    intr.ts = ts;
#endif
    intQueue.push_back(intr);
    return 0;
}
//---------------------------------------------------------------------
// update rtt(call when receive data)
//---------------------------------------------------------------------
void IntcpTransCB::updateRTT(IINT32 rtt, int xmit)
{
    //LOG(SILENT,"update srtt %d",rtt);
    if (xmit > 1)
    {
        LOG(TRACE, "retrans packet rtt %d", rtt);
    }
    if (rtt <= 0)
    {
        return;
    }
    if (srtt == 0)
    {
        srtt = rtt;
        rttvar = rtt / 2;
        rto = _ibound_(INTCP_RTO_MIN, rtt * 3, INTCP_RTO_MAX);
        return;
    }
    int rttForUpdate = 0, doUpdate = 1;
    if (RTTscheme == INTCP_RTT_SCHM_MAXWND)
    {
        // Scheme 1: max-window filter
        // NOTE this will result to a smaller rttVar during rtt oscillation
        // get old maxRtt
        int maxRttOld = -1;
        for (int r : rttQueue)
        {
            maxRttOld = max(maxRttOld, r);
        }
        // update rtt queue
        rttQueue.push_back(rtt);
        while (rttQueue.size() > 5)
        { // TODO more adaptive value?
            rttQueue.pop_front();
        }
        // get new maxRtt
        int maxRtt = -1;
        for (int r : rttQueue)
        {
            maxRtt = max(maxRtt, r);
        }
        if (maxRttOld != maxRtt)
        {
            rttForUpdate = maxRtt;
        }
        else
        {
            doUpdate = 0;
        }
    }
    else if (RTTscheme == INTCP_RTT_SCHM_EXPO)
    {
        // Scheme 2: multiply rttvar & srtt by a factor for the timeout interests
        if (xmit <= 1)
        {
            rttForUpdate = rtt;
        }
        else
        {
            doUpdate = 0;
        }
    }

    // basic update logic
    if (doUpdate)
    {
        long delta = rttForUpdate - srtt;
        if (delta < 0)
            delta = -delta;
        rttvar = (3 * rttvar + delta) / 4;
        srtt = (7 * srtt + rttForUpdate) / 8;
        if (srtt < 1)
            srtt = 1;
        IINT32 rtoTmp = srtt + _imax_(INTCP_UPDATE_INTERVAL, 4 * rttvar);
        rto = _ibound_(INTCP_RTO_MIN, rtoTmp, INTCP_RTO_MAX);
    }

    LOG(TRACE, "rtt %d srtt %d val %d rto %d", rtt, srtt, rttvar, rto);
}

void IntcpTransCB::updateHopRTT(IINT32 hop_rtt)
{
    if (hopSrtt == 0)
    {
        hopSrtt = hop_rtt;
        hopRttvar = hop_rtt / 2;
    }
    else
    {
        long delta = hop_rtt - hopSrtt;
        if (delta < 0)
            delta = -delta;
        hopRttvar = (3 * hopRttvar + delta) / 4;
        hopSrtt = (7 * hopSrtt + hop_rtt) / 8;
        if (hopSrtt < 1)
            hopSrtt = 1;
    }
}

/*
void IntcpTransCB::detectIntHole(IUINT32 rangeStart, IUINT32 rangeEnd, IUINT32 sn)
{
    return;
    IUINT32 current = _getMillisec();
    if (intSnRightBound == -1 || current - intRightBoundTs > INTCP_SNHOLE_TIMEOUT)
    {
        intSnRightBound = sn + 1;
        intByteRightBound = rangeEnd;
        intRightBoundTs = current;
        intHoles.clear();
    }
    else
    {
        // locate the position of seg in intHoles
        list<Hole>::iterator iter, next;
        for (iter = intHoles.begin(); iter != intHoles.end(); iter = next)
        {
            next = iter;
            next++;
            if (current - iter->ts > INTCP_SNHOLE_TIMEOUT)
            {
                intHoles.erase(iter);
            }
            else if (sn >= iter->endSn)
            {
                iter->count++;
                if (iter->count >= INTCP_SNHOLE_THRESHOLD)
                {
                    if (iter->endByte - iter->startByte > (iter->endSn - iter->startSn) * INTCP_INT_RANGE_LIMIT)
                    {
                        LOG(TRACE, "---- Abnormal int hole [%u,%u) [%u,%u)----", iter->startSn, iter->endSn, iter->startByte, iter->endByte);
                    }
                    else
                    {
                        stat.cntIntHole++;
                        LOG(TRACE, "---- int hole [%u,%u) [%u,%u)----", iter->startSn, iter->endSn, iter->startByte, iter->endByte);
                        parseInt(iter->startByte, iter->endByte);
                    }
                    intHoles.erase(iter);
                }
            }
            else if (sn >= iter->startSn)
            {
                if (sn == iter->startSn)
                {
                    if (sn == iter->endSn - 1)
                    { // hole is fixed
                        intHoles.erase(iter);
                    }
                    else
                    {
                        iter->startSn++;
                        iter->startByte = rangeEnd;
                    }
                }
                else if (sn == iter->endSn - 1)
                {
                    iter->endSn--;
                    iter->endByte = rangeStart;
                    iter->count++;
                }
                else
                {
                    Hole newHole;
                    newHole.count = iter->count;
                    newHole.startSn = sn + 1;
                    newHole.endSn = iter->endSn;
                    newHole.startByte = rangeEnd;
                    newHole.endByte = iter->endByte;
                    newHole.ts = iter->ts;
                    intHoles.insert(next, newHole);

                    iter->endSn = sn;
                    iter->endByte = rangeStart;
                    iter->count++;
                }
            }
            else
            { // segPtr->sn < iter->startSn
                // for this hole and subsequent holes, all hole.start > sn
                break;
            }
        }
        if (sn >= intSnRightBound)
        {
            if (sn > intSnRightBound && (rangeStart > intByteRightBound))
            {
                // add a new hole
                Hole newHole;
                newHole.startSn = intSnRightBound;
                newHole.endSn = sn;
                newHole.startByte = intByteRightBound;
                newHole.endByte = rangeStart;
                newHole.ts = current;
                newHole.count = 1;
                intHoles.push_back(newHole);
            }
            intSnRightBound = sn + 1;
            intByteRightBound = _imax_(intByteRightBound, rangeEnd);
            intRightBoundTs = current;
        }
    }
    if (!intHoles.empty())
    {
        char tmp[100];
        string str;
        for (auto ho : intHoles)
        {
            snprintf(tmp, 100, "   [ st %d end %d bSt %d bEnd %d ]", ho.startSn, ho.endSn, ho.startByte, ho.endByte);
            str += tmp;
        }
        LOG(TRACE, "sn %d intHoles: %ld %s",
            sn, intHoles.size(), str.c_str());
    }
}
*/
#ifdef HBH_CC
void IntcpTransCB::parseInt(IUINT32 rangeStart, IUINT32 rangeEnd)
#else
void IntcpTransCB::parseInt(IUINT32 rangeStart,IUINT32 rangeEnd,IUINT16 wnd,IUINT32 ts)
#endif
{
    // TODO priority
    if (rangeEnd <= rangeStart)
    {
        LOG(TRACE, "rangeEnd <= rangeStart");
        return;
    }

    IUINT32 sentEnd = rangeStart;
    if (nodeRole != INTCP_ROLE_REQUESTER)
    {
        // first, try to fetch data
        IUINT32 segStart, segEnd;
        int fetchLen;
        for (segStart = rangeStart; segStart < rangeEnd; segStart += INTCP_MSS)
        {
            segEnd = _imin_(rangeEnd, segStart + INTCP_MSS);
            fetchLen = fetchDataFunc(tmpBuffer.get(), segStart, segEnd, user);
            sentEnd = segStart + fetchLen;
            if (fetchLen == 0)
                break;
            // push fetched data(less than mtu) to sndQueue
            sendData(tmpBuffer.get(), segStart, segStart + fetchLen);
            // if this seg is not completed due to data miss
            if (fetchLen < segEnd - segStart)
            {
                break;
            }
        }
    }

    // rest range
    if (sentEnd < rangeEnd)
    {
        // NOTE in midnode, if cache has [3,10], interest is [0,10], the whole cache is wasted;
        if (nodeRole == INTCP_ROLE_RESPONDER)
        {
            // append interest to pendingInts
            if (rangeEnd <= rangeStart)
            {
                LOG(WARN, "rangeStart %d rangeEnd %d", rangeStart, rangeEnd);
                return;
            }
            ByteRange ir;
            ir.ts = _getMillisec();
            ir.startByte = sentEnd;
            ir.endByte = rangeEnd;
            pendingInts.push_back(ir);
            LOG(TRACE, "unsat [%d,%d)", sentEnd, rangeEnd);
            onUnsatInt(sentEnd, rangeEnd, user);
        }
        else if (nodeRole == INTCP_ROLE_REQUESTER)
        {
            // TODO should be pushed to intQueue for shaping?

            // plan A
            // shared_ptr<IntcpSeg> newseg = createSeg(0);
            // newseg->len = 0;
            // newseg->cmd = INTCP_CMD_INT;
            // newseg->xmit = 0;
            // newseg->ts = ts;
            // newseg->rangeStart = sentEnd;
            // newseg->rangeEnd = rangeEnd;
            // intBuf.push_back(newseg);

            // plan B
            // request(sentEnd, rangeEnd);

            // plan C
            // neither pushed to intQueue nor to intBuf, send it directly
#ifdef HBH_CC
            outputInt(sentEnd, rangeEnd);
#else
            outputInt(sentEnd, rangeEnd,0,0);
#endif
            // rmt_sndq_rest -= segPtr->rangeEnd - segPtr->rangeStart;
        }
        else
        { // INTCP_ROLE_MIDNODE
            LOG(TRACE, "output int [%d,%d)", sentEnd, rangeEnd);
#ifdef HBH_CC
            request(sentEnd, rangeEnd);
#else
            request(sentEnd, rangeEnd, wnd, ts);
#endif
            //outputInt(sentEnd, rangeEnd);
        }
    }
}

void IntcpTransCB::notifyNewData(const char *buffer, IUINT32 dataStart, IUINT32 dataEnd)
{
    if (pendingInts.empty())
        return;
    list<ByteRange>::iterator p, next;
    IntcpSeg *seg;
    for (p = pendingInts.begin(); p != pendingInts.end(); p = next)
    {
        next = p;
        next++;
        int intStart = p->startByte, intEnd = p->endByte, ts = p->ts;
        // check if the union is not empty
        if (_itimediff(intStart, dataEnd) < 0 && _itimediff(intEnd, dataStart) > 0)
        {
            IUINT32 maxStart = _imax_(intStart, dataStart);
            IUINT32 minEnd = _imin_(intEnd, dataEnd);
            LOG(TRACE, "satisfy pending int: [%d,%d)", maxStart, minEnd);
            sendData(buffer + maxStart - dataStart, maxStart, minEnd);
            if (maxStart == intStart && minEnd == intEnd)
            {
                pendingInts.erase(p);
            }
            else if (minEnd == intEnd)
            {
                // partly sent
                p->endByte = maxStart;
            }
            else
            {
                p->startByte = minEnd;
                if (maxStart != intStart)
                {
                    ByteRange ir;
                    ir.ts = ts;
                    ir.startByte = intStart;
                    ir.endByte = maxStart;
                    pendingInts.insert(p, ir);
                }
            }
        }
    }
}
#ifdef CUT_PAYLOAD
// data header doesn't provide other information
void IntcpTransCB::sendDataHeader(IUINT32 rangeStart, IUINT32 rangeEnd)
{
    LOG(TRACE," generate header [%u,%u]",rangeStart,rangeEnd);
    shared_ptr<IntcpSeg> segPtr = createSeg(0);
    segPtr->cmd = INTCP_CMD_PUSH;
    segPtr->rangeStart = rangeStart;
    segPtr->rangeEnd = rangeEnd;
    segPtr->len = 0;
    segPtr->ts = 0;
    segPtr->wnd = 0;
    sndQueue.push_back(segPtr);
    sndQueueBytes += INTCP_OVERHEAD;
}

void IntcpTransCB::insertDataHole(IUINT32 rangeStart, IUINT32 rangeEnd)
{
    Hole newHole;
    newHole.count = 0;
    // newHole.startSn = 0;    //no use
    // newHole.endSn = 0;      //no use
    newHole.startByte = rangeStart;
    newHole.endByte = rangeEnd;
    newHole.ts = _getMillisec();
    dataHoles.push_back(newHole);
    return;
}

void IntcpTransCB::deleteDataHole(IUINT32 rangeStart, IUINT32 rangeEnd)
{
    list<Hole>::iterator iter, next;
    for (iter = dataHoles.begin(); iter != dataHoles.end(); iter = next)
    {
        next = iter;
        next++;
        if (iter->startByte >= rangeEnd)
            break;
        if (iter->endByte <= rangeStart)
            continue;
        if (iter->endByte <= rangeEnd)
        {
            if (iter->startByte >= rangeStart) // rangeStart<=holeStart<holeEnd<=rangeEnd
                dataHoles.erase(iter);
            else
            { // holeStart<rangeStart<holeEnd<=rangeEnd
                iter->endByte = rangeStart;
            }
        }
        else
        {
            if (iter->startByte >= rangeStart) // rangeStart<=holeStart<rangeEnd<holeEnd
                iter->startByte = rangeEnd;
            else
            { // holeStart<rangeStart<rangeEnd<holeEnd
                Hole newHole = *iter;
                iter->endByte = rangeStart;
                newHole.startByte = rangeEnd;
                dataHoles.insert(next, newHole);
            }
        }
    }
    return;
}

#ifdef USE_PIT
void IntcpTransCB::searchDataHoles(IUINT32 rangeStart, IUINT32 rangeEnd)
{
    list<Hole>::iterator iter, next;
    for (iter = dataHoles.begin(); iter != dataHoles.end(); iter = next)
    {
        next = iter;
        next++;
        if (iter->startByte >= rangeEnd)
            break;
        if (iter->endByte <= rangeStart)
            continue;
        if (iter->endByte < rangeEnd)
        {
            if (iter->startByte > rangeStart){ // rangeStart<holeStart<holeEnd<rangeEnd
                parseInt(rangeStart,iter->startByte);
                //parseInt(iter->endByte,rangeEnd);
                rangeStart = iter->endByte;
            } 
            else    // holeStart<=rangeStart<holeEnd<rangeEnd
            { 
                //parseInt(iter->endByte,rangeEnd);
                rangeStart = iter->endByte;
            }
        }
        else
        {
            if (iter->startByte > rangeStart){      // rangeStart<holeStart<rangeEnd<=holeEnd
                parseInt(rangeStart,iter->startByte);
                return;
            } 
            else
            {                                   // holeStart<=rangeStart<rangeEnd<=holeEnd
               return;
            }
        }
    }
    if(rangeEnd>rangeStart)
        parseInt(rangeStart,rangeEnd);
    return;
}
#endif

void IntcpTransCB::updateIntBuf(IUINT32 rangeStart, IUINT32 rangeEnd)
{
    IUINT32 intRangeStart, intRangeEnd;
    list<shared_ptr<IntcpSeg>>::iterator iter, next;
    for (iter = intBuf.begin(); iter != intBuf.end(); iter = next)
    {
        next = iter;
        next++;
        intRangeStart = (*iter)->rangeStart;
        intRangeEnd = (*iter)->rangeEnd;
        if (intRangeStart >= rangeEnd)
            break;
        if (intRangeEnd <= rangeStart)
            continue;
        if (intRangeEnd <= rangeEnd)
        {
            if (intRangeStart >= rangeStart) // rangeStart<=intStart<intEnd<=rangeEnd
                (*iter)->ts = _getMillisec();
            else
            { // intStart<rangeStart<intEnd<=rangeEnd
                shared_ptr<IntcpSeg> newseg = createSeg(0);
                memcpy(newseg.get(), (*iter).get(), sizeof(IntcpSeg));
                (*iter)->rangeEnd = rangeStart;
                newseg->rangeStart = rangeStart;
                newseg->ts = _getMillisec();
                intBuf.insert(next, newseg);
            }
        }
        else
        {
            if (intRangeStart >= rangeStart)
            { // rangeStart<=IntStart<rangeEnd<IntEnd
                shared_ptr<IntcpSeg> newseg = createSeg(0);
                memcpy(newseg.get(), (*iter).get(), sizeof(IntcpSeg));
                (*iter)->rangeStart = rangeEnd;
                newseg->rangeEnd = rangeEnd;
                newseg->ts = _getMillisec();
                intBuf.insert(iter, newseg);
            }
            else
            { // intStart<rangeStart<rangeEnd<intEnd
                shared_ptr<IntcpSeg> newseg1 = createSeg(0);
                shared_ptr<IntcpSeg> newseg2 = createSeg(0);
                memcpy(newseg1.get(), (*iter).get(), sizeof(IntcpSeg));
                memcpy(newseg2.get(), (*iter).get(), sizeof(IntcpSeg));
                newseg1->rangeEnd = rangeStart;
                newseg2->rangeStart = rangeEnd;
                (*iter)->rangeStart = rangeStart;
                (*iter)->rangeEnd = rangeEnd;
                (*iter)->ts = _getMillisec();
                intBuf.insert(iter, newseg1);
                intBuf.insert(next, newseg2);
            }
        }
    }
}

bool IntcpTransCB::detectDataHole(IUINT32 rangeStart, IUINT32 rangeEnd)
{
#ifndef USE_CACHE
    if (nodeRole==INTCP_ROLE_MIDNODE)
        return false;
#endif

    if (rangeStart == dataNextRangeStart)
    { // normal packet
        dataNextRangeStart = rangeEnd;
        return false;
    }
    else if (rangeStart < dataNextRangeStart)
    { // retransmission packet
        deleteDataHole(rangeStart, rangeEnd);
        return false;
    }
    else
    { // find a hole
        if(dataNextRangeStart==0||rangeStart-dataNextRangeStart>100*INTCP_MSS){          //abnormal hole
            dataNextRangeStart=rangeEnd;
            return false;
        }
        insertDataHole(dataNextRangeStart, rangeStart);
        if (nodeRole == INTCP_ROLE_MIDNODE)
        {
            sendDataHeader(dataNextRangeStart, rangeStart);
        }
        dataNextRangeStart = rangeEnd;
        return true;
    }
}

void IntcpTransCB::flushDataHoles()
{
    IUINT32 current = _getMillisec();
    LOG(TRACE, "dataHoles size %lu", dataHoles.size());
    list<Hole>::iterator iter, next;
    for (iter = dataHoles.begin(); iter != dataHoles.end(); iter = next)
    {
        next = iter;
        next++;
        if (_itimediff(current, iter->ts) >= INTCP_SNHOLE_TIMEOUT)
            dataHoles.erase(iter);
        if (_itimediff(current, iter->ts) >= INTCP_HOLE_WAIT)
        {
#ifdef USE_PIT
            if(iter->count==0){
                iter->count = 1;
                LOG(TRACE, " CP retran interest [%u,%u], waiting time %ld ", iter->startByte, iter->endByte,_itimediff(current,iter->ts));
                parseInt(iter->startByte, iter->endByte);
                if (nodeRole == INTCP_ROLE_REQUESTER)
                    updateIntBuf(iter->startByte, iter->endByte);
            }
#else            
            LOG(DEBUG, " CP retran interest [%u,%u], waiting time %ld ", iter->startByte, iter->endByte,_itimediff(current,iter->ts));
#ifdef HBH_CC
            parseInt(iter->startByte, iter->endByte);
#else
            parseInt(iter->startByte, iter->endByte,0,0);
#endif
            if (nodeRole == INTCP_ROLE_REQUESTER)
                updateIntBuf(iter->startByte, iter->endByte);
            dataHoles.erase(iter); // only try once
#endif
        }
    }
    return;
}

#else
//---------------------------------------------------------------------
// parse data
//---------------------------------------------------------------------
bool IntcpTransCB::detectDataHole(IUINT32 rangeStart, IUINT32 rangeEnd, IUINT32 sn)
{ // return true when find a new hole
    bool found_new_loss = false;
    // return false;
    IUINT32 current = _getMillisec();
    if (dataSnRightBound == -1 || current - dataRightBoundTs > INTCP_SNHOLE_TIMEOUT)
    {
        dataSnRightBound = sn + 1;
        dataByteRightBound = rangeEnd;
        dataRightBoundTs = current;
        dataHoles.clear();
    }
    else
    {
        // locate the position of seg in dataHoles
        list<Hole>::iterator iter, next;
        for (iter = dataHoles.begin(); iter != dataHoles.end(); iter = next)
        {
            next = iter;
            next++;
            if (current - iter->ts > INTCP_SNHOLE_TIMEOUT)
            {
                dataHoles.erase(iter);
            }
            else if (sn >= iter->endSn)
            {
                iter->count++;
                if (iter->count >= INTCP_SNHOLE_THRESHOLD)
                {
                    found_new_loss = true;
                    if (iter->endByte - iter->startByte > (iter->endSn - iter->startSn) * INTCP_MSS)
                    {
                        LOG(TRACE, "---- Abnormal data hole [%u,%u) [%u,%u) t %u----", iter->startSn, iter->endSn, iter->startByte, iter->endByte, current);
                    }
                    else
                    {
                        stat.cntDataHole++;
                        LOG(TRACE, "---- data hole [%u,%u) [%u,%u) t %u----", iter->startSn, iter->endSn, iter->startByte, iter->endByte, current);
                        parseInt(iter->startByte, iter->endByte);
                        list<shared_ptr<IntcpSeg>>::iterator iterInt;
                        // if the range of this hole could cover an interest in intBuf, modify the ts of interest
                        for (iterInt = intBuf.begin(); iterInt != intBuf.end(); iterInt++)
                        {
                            if (max(iter->startByte, (*iterInt)->rangeStart) < min(iter->endByte, (*iterInt)->rangeEnd))
                            {
                                //------------------------------
                                // update intBuf
                                //------------------------------
                                if (iter->startByte <= (*iterInt)->rangeStart)
                                {
                                    if (iter->endByte >= (*iterInt)->rangeEnd)
                                    { // range completely received
                                        (*iterInt)->ts = _getMillisec();
                                    }
                                    else
                                    {
                                        shared_ptr<IntcpSeg> newseg = createSeg(0);
                                        memcpy(newseg.get(), (*iterInt).get(), sizeof(IntcpSeg));
                                        newseg->rangeStart = iter->endByte;
                                        // newseg->rttUpdate = true;
                                        (*iterInt)->rangeEnd = iter->endByte;
                                        (*iterInt)->ts = _getMillisec();

                                        intBuf.insert(iterInt, newseg);
                                        iterInt++;
                                    }
                                }
                                else if (iter->endByte >= (*iterInt)->rangeEnd)
                                {
                                    shared_ptr<IntcpSeg> newseg = createSeg(0);
                                    memcpy(newseg.get(), (*iterInt).get(), sizeof(IntcpSeg));
                                    newseg->rangeStart = iter->startByte;
                                    // newseg->rttUpdate = true;
                                    (*iterInt)->rangeEnd = iter->startByte;
                                    newseg->ts = _getMillisec();
                                    intBuf.insert(iterInt, newseg);
                                    iterInt++;
                                }
                                else
                                {
                                    shared_ptr<IntcpSeg> newseg = createSeg(0);
                                    memcpy(newseg.get(), (*iterInt).get(), sizeof(IntcpSeg));
                                    newseg->rangeStart = iter->endByte;
                                    // newseg->rttUpdate = true; keep the same as the previous interest
                                    intBuf.insert(iterInt, newseg);

                                    newseg = createSeg(0);
                                    memcpy(newseg.get(), (*iterInt).get(), sizeof(IntcpSeg));
                                    newseg->rangeStart = iter->startByte;
                                    newseg->rangeEnd = iter->endByte;
                                    newseg->ts = _getMillisec();
                                    // newseg->rttUpdate = true;
                                    intBuf.insert(iterInt, newseg);

                                    (*iterInt)->rangeEnd = iter->startByte;
                                    iterInt++;
                                    iterInt++;
                                }
                            }
                        }
                    }
                    dataHoles.erase(iter);
                }
            }
            else if (sn >= iter->startSn)
            {
                if (sn == iter->startSn)
                {
                    if (sn == iter->endSn - 1)
                    { // hole is fixed
                        dataHoles.erase(iter);
                    }
                    else
                    {
                        iter->startSn++;
                        iter->startByte = rangeEnd;
                    }
                }
                else if (sn == iter->endSn - 1)
                {
                    iter->endSn--;
                    iter->endByte = rangeStart;
                    iter->count++;
                }
                else
                {
                    Hole newHole;
                    newHole.count = iter->count;
                    newHole.startSn = sn + 1;
                    newHole.endSn = iter->endSn;
                    newHole.startByte = rangeEnd;
                    newHole.endByte = iter->endByte;
                    newHole.ts = iter->ts;
                    dataHoles.insert(next, newHole);

                    iter->endSn = sn;
                    iter->endByte = rangeStart;
                    iter->count++;
                }
            }
            else
            { // segPtr->sn < iter->start
                // for this hole and subsequent holes, all hole.start > sn
                break;
            }
        }
        if (sn >= dataSnRightBound)
        {
            if (sn > dataSnRightBound && (rangeStart > dataByteRightBound))
            {
                // add a new hole
                Hole newHole;
                newHole.startSn = dataSnRightBound;
                newHole.endSn = sn;
                newHole.startByte = dataByteRightBound;
                newHole.endByte = rangeStart;
                LOG(TRACE, "---- data hole [%d,%d) cur %u----", newHole.startByte, newHole.endByte, current);
                newHole.ts = current;
                newHole.count = 1;
                dataHoles.push_back(newHole);
            }
            dataSnRightBound = sn + 1;
            dataByteRightBound = _imax_(dataByteRightBound, rangeEnd);
            dataRightBoundTs = current;
        }
    }
    if (!dataHoles.empty())
    {
        char tmp[100];
        string str;
        for (auto ho : dataHoles)
        {
            snprintf(tmp, 100, "   [ st %d end %d bSt %d bEnd %d ]", ho.startSn, ho.endSn, ho.startByte, ho.endByte);
            str += tmp;
        }
        LOG(TRACE, "sn %d dataHoles: %ld %s",
            sn, dataHoles.size(), str.c_str());
    }
    return found_new_loss;
}

#endif

#ifdef CUT_PAYLOAD
void IntcpTransCB::parseData(shared_ptr<IntcpSeg> dataSeg, bool data_header)
#else
void IntcpTransCB::parseData(shared_ptr<IntcpSeg> dataSeg)
#endif
{
    if (nodeRole == INTCP_ROLE_REQUESTER)
    {
#ifdef CUT_PAYLOAD
        if (data_header)
            return;
#endif
        list<shared_ptr<IntcpSeg>>::iterator intIter, intNext;
        // in requester, need to delete range of intBuf
        int intUseful = 0;
        for (intIter = intBuf.begin(); intIter != intBuf.end(); intIter = intNext)
        {
            shared_ptr<IntcpSeg> intSeg = *intIter;
            intNext = intIter;
            intNext++;
            if (dataSeg->rangeEnd <= intSeg->rangeStart)
            {
                break;
            }
            if (dataSeg->rangeStart < intSeg->rangeEnd && dataSeg->rangeEnd > intSeg->rangeStart)
            {
                LOG(TRACE, "[%d,%d) rtt %d current %u xmit %d", dataSeg->rangeStart, dataSeg->rangeEnd,
                    _getMillisec() - intSeg->ts, _getMillisec(), intSeg->xmit);
                intUseful = 1;
                // if(intSeg->rttUpdate){
                // // if(true){
                //     updateRTT(_itimediff(_getMillisec(), intSeg->ts));
                //     intSeg->rttUpdate = false;
                // }
                //-------------------------------
                // insert [the intersection of seg and interest] into rcvBuf
                //-------------------------------
                int intsecStart = _imax_(intSeg->rangeStart, dataSeg->rangeStart);
                int intsecEnd = _imin_(intSeg->rangeEnd, dataSeg->rangeEnd);
                shared_ptr<IntcpSeg> intsecDataSeg = createSeg(intsecEnd - intsecStart);
                intsecDataSeg->rangeStart = intsecStart;
                intsecDataSeg->rangeEnd = intsecEnd;
                intsecDataSeg->len = intsecEnd - intsecStart;
                LOG(TRACE, "satisfy interest range %u, data range %u", intsecEnd - intsecStart, dataSeg->len);
                memcpy(intsecDataSeg->data, dataSeg->data + intsecStart - dataSeg->rangeStart,
                       intsecEnd - intsecStart);
                // NOTE pass information to app layer
                IUINT32 cur_tmp = _getMillisec();
                // LOG(DEBUG,"xmit %u rto %u rcvTime %u",intSeg->xmit,intSeg->rto,cur_tmp);
                memcpy(intsecDataSeg->data + sizeof(IUINT32), &intSeg->xmit, sizeof(IUINT32));
                memcpy(intsecDataSeg->data + sizeof(IUINT32) * 2, &cur_tmp, sizeof(IUINT32));
                // memcpy(intsecDataSeg->data+sizeof(IUINT32)*3, &intSeg->firstTs, sizeof(IUINT32));

                // TODO entirely rewrite
                IUINT32 t0 = _getUsec(), loop = 0, front = true, t2, t3, t4;
                IUINT32 ns = intsecDataSeg->rangeStart, ne = intsecDataSeg->rangeEnd;

                list<RcvBufItr>::iterator itrNext, itrPrev;
                bool found = false;
                for (itrNext = rcvBufItrs.begin(); itrNext != rcvBufItrs.end(); itrNext++)
                {
                    if (itrNext->startByte >= ne)
                    {
                        found = true;
                        break;
                    }
                }
                itrPrev = found ? itrNext : rcvBufItrs.end();
                bool isPrevContinuous = itrPrev != rcvBufItrs.begin() && (--itrPrev)->endByte == ns;
                if (found)
                {
                    rcvBuf.insert(itrNext->itr, intsecDataSeg);
                    if (itrNext->startByte == ne)
                    {
                        if (isPrevContinuous)
                        {
                            itrPrev->endByte = itrNext->endByte;
                            rcvBufItrs.erase(itrNext);
                        }
                        else
                        {
                            itrNext->startByte = ns;
                        }
                    }
                    else
                    {
                        if (isPrevContinuous)
                        {
                            itrPrev->endByte = ne;
                        }
                        else
                        {
                            auto tmpItr = itrNext->itr;
                            --tmpItr;
                            RcvBufItr ptr = {
                                .startByte = ns,
                                .endByte = ne,
                                .itr = tmpItr};
                            rcvBufItrs.insert(itrNext, ptr);
                        }
                    }
                }
                else
                {
                    rcvBuf.push_back(intsecDataSeg);
                    if (isPrevContinuous)
                    {
                        itrPrev->endByte = ne;
                    }
                    else
                    {
                        auto tmpItr = rcvBuf.end();
                        --tmpItr;
                        RcvBufItr ptr = {
                            .startByte = ns,
                            .endByte = ne,
                            .itr = tmpItr};
                        rcvBufItrs.push_back(ptr);
                    }
                }
                // IUINT32 head = (*rcvBuf.begin())->rangeStart, tail = (*--rcvBuf.end())->rangeStart;
                // bool found=false;
                // list<shared_ptr<IntcpSeg>>::iterator dataIter;
                // t2 = _getUsec();
                // if(intsecDataSeg->rangeStart > (head+tail)/2){
                // // if(false){
                //     front=false;
                //     auto bound=rcvBuf.begin();
                //     IUINT32 isgStart = intsecDataSeg->rangeStart;
                //     t3 = _getUsec();
                //     for (dataIter = rcvBuf.end(); dataIter != bound; ) {
                //         --dataIter;
                //         ++loop;
                //         if (isgStart >= (*dataIter)->rangeEnd) {
                //             found = true;
                //             break;
                //         }
                //     }
                //     t4 = _getUsec();
                //     if(found){
                //         rcvBuf.insert(++dataIter,intsecDataSeg);
                //     }else{
                //         rcvBuf.insert(dataIter,intsecDataSeg);
                //     }
                // }else{
                //     auto bound=rcvBuf.end();
                //     IUINT32 isgEnd = intsecDataSeg->rangeEnd;
                //     t3 = _getUsec();
                //     for (dataIter = rcvBuf.begin(); dataIter != bound; ) {
                //         ++loop;
                //         if (isgEnd <= (*dataIter)->rangeStart) {
                //             found = true;
                //             break;
                //         }
                //         ++dataIter;
                //     }
                //     t4 = _getUsec();
                //     rcvBuf.insert(dataIter,intsecDataSeg);
                // }
                IUINT32 t1 = _getUsec();
                if (t1 - t0 > 100)
                {
                    // if(float(t1-t0)/loop > 100){
                    LOG(TRACE, "%d loop %d/%ld fr %d t:%d %d %d %d,h %d t %d", t1 - t0, loop, rcvBuf.size(), front,
                        t2 - t0, t3 - t2, t4 - t3, t1 - t4, (*rcvBuf.begin())->rangeStart, (*--rcvBuf.end())->rangeStart);
                }

                //------------------------------
                // update intBuf
                //------------------------------
                // intSeg->rttUpdate = false;
                intBufBytes -= intsecEnd - intsecStart;
                stat.recvedINTCP += intsecEnd - intsecStart;
                conseqTimeout = 0;
                if (dataSeg->rangeStart <= intSeg->rangeStart)
                {
                    if (dataSeg->rangeEnd >= intSeg->rangeEnd)
                    { // range completely received
                        updateRTT(_itimediff(_getMillisec(), intSeg->ts), intSeg->xmit);
                        intBuf.erase(intIter);
                    }
                    else
                    {
                        intSeg->rangeStart = dataSeg->rangeEnd;
                    }
                }
                else if (dataSeg->rangeEnd >= intSeg->rangeEnd)
                {
                    intSeg->rangeEnd = dataSeg->rangeStart;
                }
                else
                {
                    // intSeg->rangeEnd = sn;
                    shared_ptr<IntcpSeg> newseg = createSeg(0);
                    memcpy(newseg.get(), intSeg.get(), sizeof(IntcpSeg));
                    intSeg->rangeEnd = dataSeg->rangeStart;
                    newseg->rangeStart = dataSeg->rangeEnd;

                    intBuf.insert(intIter, newseg);
                }
            }
        }
        if (intUseful == 0)
        {
            LOG(DEBUG, "useless data recved [%u,%u)", dataSeg->rangeStart, dataSeg->rangeEnd);
        }
    }
    else
    {
        shared_ptr<IntcpSeg> segToForward = createSeg(dataSeg->len);
        // TODO copy char[] pointer??
        memcpy(segToForward.get(), dataSeg.get(), sizeof(IntcpSeg) + dataSeg->len);
        LOG(TRACE,"forward data [%u,%u], ts %u, sndQ %u",segToForward->rangeStart,segToForward->rangeEnd,_getMillisec(),sndQueueBytes/INTCP_MSS);
        sndQueue.push_back(segToForward);
#ifdef CUT_PAYLOAD
        sndQueueBytes += (INTCP_OVERHEAD+segToForward->len);
    #ifdef USE_CACHE
        if (!data_header)
            rcvBuf.push_back(dataSeg);
    #endif
#else
        sndQueueBytes += segToForward->len;
        rcvBuf.push_back(dataSeg);
#endif
    }

    moveToRcvQueue();
}

// reordering in requester: queueing in order of interest
//  (suppose interest is in order now)
//  move available data from rcvBuf -> rcvQueue
void IntcpTransCB::moveToRcvQueue()
{
    // TODO add rcvBufItrs logic
    while (!rcvBuf.empty())
    {
        if (nodeRole == INTCP_ROLE_MIDNODE)
        {
            // LOG(DEBUG,"rq size %ld rw %u",rcvQueue.size(), INTCP_WND_RCV);
            if (rcvQueue.size() < INTCP_WND_RCV)
            {
                rcvQueue.splice(rcvQueue.end(), rcvBuf, rcvBuf.begin(), rcvBuf.end());
            }
            else
            {
                break;
            }
        }
        else
        {
            shared_ptr<IntcpSeg> seg = *rcvBuf.begin();
            if (seg->rangeStart == rcvNxt && rcvQueue.size() < INTCP_WND_RCV)
            {
                rcvNxt = seg->rangeEnd;
                rcvQueue.splice(rcvQueue.end(), rcvBuf, rcvBuf.begin());
            }
            else
            {
                break;
            }
        }
    }
    if (nodeRole == INTCP_ROLE_REQUESTER)
    {
        while (!rcvBufItrs.empty() && rcvNxt >= rcvBufItrs.begin()->endByte)
        {
            rcvBufItrs.erase(rcvBufItrs.begin());
        }
        if (rcvNxt > rcvBufItrs.begin()->startByte)
        {
            rcvBufItrs.begin()->startByte = rcvNxt;
        }
    }
}

// for debug
double parse_data_time = 0;
double detect_time = 0;
IUINT32 last_print_time = 0;
//---------------------------------------------------------------------
// input data
//---------------------------------------------------------------------
int IntcpTransCB::input(char *data, int size)
{
    if (data == NULL || (int)size < (int)INTCP_OVERHEAD)
        return -1;

    // when receiving udp packet, we use judgeDst() to get info from the
    // first intcp seg, to decide which IntcpSess it should be inputed to.
    // if multiple intcp segs are concatenated in this single udp packet,
    // and they have different dst, there will be error.
    // so, now we only allow one intcp seg per input().
    // while (1) {
    IUINT32 ts, sn, len;
    IUINT32 rangeStart, rangeEnd; // intcp
    IINT16 wnd;
    IUINT8 cmd;
    shared_ptr<IntcpSeg> seg;
#ifdef CUT_PAYLOAD
    bool data_header;
#endif

    char *dataOrg = data;
    long sizeOrg = size;
    while (1)
    {
        IUINT32 current = _getMillisec();
        if (size < (int)INTCP_OVERHEAD)
            break;
        data = decode8u(data, &cmd);
        data = decode16(data, &wnd);
        data = decode32u(data, &ts);
        data = decode32u(data, &sn);
        data = decode32u(data, &len);
        // if(len+INTCP_OVERHEAD<size){
        //     LOG(WARN, "input size %d > seg size %d",size,len+INTCP_OVERHEAD);
        // }
        data = decode32u(data, &rangeStart);
        data = decode32u(data, &rangeEnd);
        size -= INTCP_OVERHEAD;

        if ((long)size < (long)len || (int)len < 0)
            return -2;

        if (cmd != INTCP_CMD_PUSH && cmd != INTCP_CMD_INT)
            return -3;

        if (cmd == INTCP_CMD_INT)
        {
#ifdef HBH_CC
            intHopOwd = _getMillisec() - ts;
            // if(intHopOwd>110){
            //     LOG(DEBUG,"(%u)%u",sn,intHopOwd);
            // }
            rmtSendRate = float(wnd) / 100;
#else
            if(ts!=0&&wnd>0){
                intHopOwd = _getMillisec() - ts;
                //printf("%d\n",intHopOwd);
                rmtSendRate = float(wnd) / 100;
                //printf("%f\n",rmtSendRate);
            }
#endif
            if(nodeRole==INTCP_ROLE_RESPONDER)
                LOG(TRACE, "%u recv int %u [%u,%u) %u rSR %.1f",
                    _getMillisec(), sn, rangeStart, rangeEnd, rangeEnd - rangeStart, rmtSendRate);
            if (!(rangeStart == 0 && rangeEnd == 0))
            {
                //detectIntHole(rangeStart, rangeEnd, sn);
                //if(nodeRole==INTCP_ROLE_RESPONDER)
                LOG(TRACE,"recv int [%u,%u]",rangeStart,rangeEnd);
#ifdef CUT_PAYLOAD
    #ifdef USE_PIT
                if(rangeStart>=intNextRangeStart){
                    parseInt(rangeStart,rangeEnd);
                }
                else{
                    searchDataHoles(rangeStart,rangeEnd);
                }
                if(rangeEnd>intNextRangeStart)
                    intNextRangeStart=rangeEnd;
    #else
        #ifdef HBH_CC
                parseInt(rangeStart,rangeEnd);
        #else
                parseInt(rangeStart,rangeEnd,wnd,ts);
        #endif
    #endif
#else
                parseInt(rangeStart, rangeEnd);
#endif
            }
        }
        else if (cmd == INTCP_CMD_PUSH)
        {
            // TODO avoid memcpy
            //  if (isMidnode) {
            //      decode16u(dataOrg+sizeof(cmd),&wnd);
            //      outputFunc(dataOrg, sizeOrg, user, INTCP_ROLE_REQUESTER);
            //  }
#ifdef CUT_PAYLOAD
            bool data_header = (bool)(len == 0);
#endif

#ifdef CUT_PAYLOAD
            if((!data_header) && (wnd!=0)){
                rmt_sndq_rest = wnd * INTCP_MSS; // TODO for midnode, ignore this part
                LOG(TRACE, "%d", wnd);
            }
#else
            if (wnd != 0){
                rmt_sndq_rest = wnd * INTCP_MSS; // TODO for midnode, ignore this part
                LOG(TRACE, "%d", wnd);
            }
            
#endif

            if (current > ts)
            {
                // if(current-ts > 210){
                //     LOG(DEBUG,"%u (%u)%d",current,sn,current-ts);
                // }else{
                //     // LOG(DEBUG,"         %u (%u)%d",current,sn,current-ts);
                // }
#ifdef HBH_CC
                updateHopRTT(current - ts);
                LOG(TRACE,"hopRTT %u",current - ts);
#else
                if(ts!=0){
                    updateHopRTT(current - ts);
                    LOG(TRACE,"hopRTT %u",current - ts);
                }
#endif
            }
            else
            {
                LOG(TRACE, "_getMillisec()>ts");
            }
            if (hopSrtt != 0)
            { // only begin calculating throughput when hoprtt exists
#ifdef CUT_PAYLOAD
                recvedBytesThisHRTT += (INTCP_OVERHEAD+len);
#else
                recvedBytesThisHRTT += len;
#endif
                stat.recvedUDP += len;
                if (lastThrpUpdateTs == 0)
                    lastThrpUpdateTs = current;
                if (_itimediff(current, lastThrpUpdateTs) > hopSrtt)
                { // hopSrtt
                    recvedBytesLastHRTT = recvedBytesThisHRTT;
                    thrpLastPeriod = bytesToMbit(recvedBytesThisHRTT) / (current - lastThrpUpdateTs) * 1000;
                    LOG(TRACE, "receive rate = %.2fMbps", thrpLastPeriod);
                    recvedBytesThisHRTT = 0;
                    lastThrpUpdateTs = current;
                }
            }
            updateCwnd(len);
            if (current - lastSendIntTs > hopSrtt * 0.9)
            {
#ifdef HBH_CC
                outputInt(0, 0);
#else
                outputInt(0, 0, 0, 0);
#endif
            }
            IUINT32 cf = _getUsec();
#ifdef CUT_PAYLOAD
            bool foundDataHole = detectDataHole(rangeStart, rangeEnd);
#else
            bool foundDataHole = detectDataHole(rangeStart, rangeEnd, sn);
#endif
            IUINT32 df = _getUsec();
            detect_time += ((double)(df - cf)) / 1000000;
            hasLossEvent = hasLossEvent || foundDataHole;

            seg = createSeg(len);
            seg->cmd = cmd;
            seg->wnd = wnd;
            seg->ts = ts;
            // seg->sn = sn;
            seg->len = len;
            seg->rangeStart = rangeStart;
            seg->rangeEnd = rangeEnd;
#ifdef CUT_PAYLOAD
            if (data_header)
            {
                LOG(DEBUG, " recv header [%u,%u]", rangeStart, rangeEnd);
                parseData(seg, data_header);
            }
            else if (rangeEnd - rangeStart != len)
            {
                LOG(DEBUG, "inconsistent data [%u,%u] len %u", rangeStart, rangeEnd, len);
                break;
                // continue;
            }
#else
            if (rangeEnd - rangeStart != len)
            {
                LOG(DEBUG, "inconsistent data range: rangeStart %u rangeEnd %u len %u", rangeStart, rangeEnd, len);
                break;
                // continue;
            }
#endif
            else
            {
                LOG(TRACE, "recv data %d [%d,%d), ts %u", sn, rangeStart, rangeEnd,_getMillisec());
                cf = _getUsec();
                memcpy(seg->data, data, len);
#ifdef CUT_PAYLOAD
                parseData(seg, data_header);
#else
                parseData(seg);
#endif
                df = _getUsec();
                parse_data_time += ((double)(df - cf)) / 1000000;
            }
            if (df - last_print_time > 1000000)
            {
                LOG(TRACE, "detect hole time %.2f parse data time %.2f", detect_time, parse_data_time);
                last_print_time = df;
            }
        }
        else
        {
            return -3;
        }

        data += len;
        size -= len;
    }

    return 0;
}

//---------------------------------------------------------------------
// flush
//---------------------------------------------------------------------

void IntcpTransCB::flushIntQueue()
{
    while (!intQueue.empty())
    {
        shared_ptr<IntcpSeg> newseg = createSeg(0);
        assert(newseg);
        newseg->len = 0;
        newseg->sn = 0;
        newseg->cmd = INTCP_CMD_INT;
        // newseg->rttUpdate = true;
        newseg->xmit = 0;

        bool first = true;
        // NOTE assume that rangeEnd of interest in intQueue is in order
        for (list<ByteRange>::iterator iter = intQueue.begin(); iter != intQueue.end();)
        {
            if (first)
            {
                newseg->rangeStart = iter->startByte;
                newseg->rangeEnd = _imin_(iter->endByte, newseg->rangeStart + INTCP_INT_RANGE_LIMIT);
#ifndef HBH_CC
                if(nodeRole==INTCP_ROLE_MIDNODE){
                    newseg->wnd = iter->wnd;
                    newseg->ts = iter->ts;
                }
#endif
                first = false;
            }
            else
            {
                if (iter->startByte == newseg->rangeEnd)
                {
                    LOG(TRACE, "%u %u %u %u", newseg->rangeStart, newseg->rangeEnd, iter->startByte, iter->endByte);
                    // newseg->rangeStart = _imin_(iter->start,newseg->rangeStart);
                    newseg->rangeEnd = _imin_(iter->endByte,
                                              newseg->rangeStart + INTCP_INT_RANGE_LIMIT);
                }
                else
                {
                    break;
                }
            }
            if (iter->endByte <= newseg->rangeEnd)
            {
                intQueue.erase(iter++);
            }
            else
            {
                iter->startByte = newseg->rangeEnd;
                break;
            }
        }
        // intRangeLimit -= newseg->rangeEnd-newseg->rangeStart;
        intBufBytes += newseg->rangeEnd - newseg->rangeStart;
        intBuf.push_back(newseg);
    }
}

void IntcpTransCB::flushIntBuf()
{
    if (intBufBytes == 0)
        return;

    IUINT32 current = _getMillisec();
    IUINT32 flushIntv = INTCP_UPDATE_INTERVAL;
    if (lastFlushTs != 0)
    {
        flushIntv = current - lastFlushTs;
    }

    // if(nodeRole==INTCP_ROLE_REQUESTER && rmt_sndq_rest<= 0){
    //     return;
    // }
    int newOutput;
    if (srtt != 0)
    {
        // TODO thrpLastPeriod -> thrp at producer
        newOutput = float(rmt_sndq_rest) * flushIntv / srtt + mbitToBytes(thrpLastPeriod) * flushIntv / 1000;
        newOutput = max(newOutput, mbitToBytes(INTCP_SENDRATE_MIN) * int(flushIntv) / 1000);
        intOutputLimit += newOutput;
    }
    LOG(TRACE, "%d %d %d %d %ld %d", rmt_sndq_rest, flushIntv, srtt, intOutputLimit, intQueue.size(), intBufBytes);
    char *sentEnd = tmpBuffer.get();
    int sizeToSend = 0;
    // from intBuf to udp
    list<shared_ptr<IntcpSeg>>::iterator p, next;

    int cntAll = 0, cntTimeout = 0, cntRetransed = 0, cntNeedSend = 0;
    int intBufSize = intBuf.size();
    bool reach_limit = false;
    int loop = 0;
    for (p = intBuf.begin(); p != intBuf.end(); p = next)
    {
        loop++;
        cntAll++;
        next = p;
        next++;
        IUINT32 current = _getMillisec();
        shared_ptr<IntcpSeg> segPtr = *p;
        IUINT32 segRto;
        int needsend = 0;
        if (nodeRole == INTCP_ROLE_MIDNODE)
        {
            needsend = 1;
        }
        else
        {
            // RTO mechanism
            if (segPtr->xmit >= 2)
            {
                cntRetransed++;
            }
            if (segPtr->xmit == 0)
            {
                needsend = 1;
                // } else if (_itimediff(current, segPtr->resendts) >= 0) {
            }
            else
            {
                // NOTE RTO function: segRto=f(rto, xmit)
                segRto = rto * (pow(1.5, segPtr->xmit - 1) + 1); // + 1000;
                // segRto = rto*( pow(1.5,segPtr->xmit-1) +1)+200;// + 1000;
                if (_itimediff(current, segPtr->ts) >= segRto)
                {
                    needsend = 1;
                    // needsend = 0;
                }
            }
        }

        if (needsend)
        {
            cntNeedSend += 1;
            if (nodeRole == INTCP_ROLE_REQUESTER)
            {
                // rmt_sndq_rest -= segPtr->rangeEnd - segPtr->rangeStart;
                if (intOutputLimit < segPtr->rangeEnd - segPtr->rangeStart)
                { // intOutputLimit<segPtr->rangeEnd - segPtr->rangeStart
                    LOG(TRACE, "intOutputLimit %d bytes seglen %d qsize %ld",
                        intOutputLimit, segPtr->rangeEnd - segPtr->rangeStart, sndQueue.size());
                    reach_limit = true;
                    break;
                }
                else
                {
                    intOutputLimit -= segPtr->rangeEnd - segPtr->rangeStart;
                    LOG(TRACE, "->%d", intOutputLimit);
                }
            }
            if (segPtr->xmit > 0)
            {
                if (segPtr->xmit > 0)
                { // 1
                    LOG(DEBUG, "----- Timeout [%d,%d) xmit %d cur %u rto %d -----",
                        segPtr->rangeStart, segPtr->rangeEnd, segPtr->xmit, _getMillisec(), rto);
                }
                if (segPtr->xmit >= INTCP_DEADLINK)
                { // || segRto>=INTCP_RTO_MAX) {
                    state = -1;
                    LOG(ERROR, "dead link");
                    exit(0);
                }
                hasLossEvent = true;
                cntTimeout++;
                stat.xmit++;
            }
            // clear hole
            // DEBUG
#ifdef CUT_PAYLOAD
            deleteDataHole(segPtr->rangeStart, segPtr->rangeEnd);
#else
            if (nodeRole != INTCP_ROLE_MIDNODE)
            {
                list<Hole>::iterator iter, next;
                for (iter = dataHoles.begin(); iter != dataHoles.end(); iter = next)
                {
                    next = iter;
                    next++;
                    IUINT32 maxStart = _imax_(segPtr->rangeStart, iter->startByte);
                    IUINT32 minEnd = _imin_(segPtr->rangeEnd, iter->endByte);
                    if (maxStart < minEnd)
                    {
                        LOG(TRACE, "RTO[%d,%d) cover hole [%d,%d)", segPtr->rangeStart, segPtr->rangeEnd, iter->startByte, iter->endByte);
                        if (maxStart == iter->startByte)
                        {
                            if (minEnd == iter->endByte)
                            { // hole is fixed
                                dataHoles.erase(iter);
                            }
                            else
                            {
                                iter->startByte = minEnd;
                            }
                        }
                        else if (minEnd == iter->endByte)
                        {
                            iter->endByte = maxStart;
                        }
                        else
                        {
                            Hole newHole;
                            newHole.count = iter->count;
                            newHole.startSn = iter->startSn;
                            newHole.endSn = iter->endSn;
                            newHole.startByte = minEnd;
                            newHole.endByte = iter->endByte;
                            newHole.ts = iter->ts;
                            dataHoles.insert(next, newHole);

                            iter->endByte = maxStart;
                        }
                    }
                }
            }
#endif

#ifdef HBH_CC
            outputInt(segPtr->rangeStart, segPtr->rangeEnd);
#else
            outputInt(segPtr->rangeStart, segPtr->rangeEnd,segPtr->wnd,segPtr->ts);
#endif
            segPtr->xmit++;
            segPtr->ts = current;

            if (nodeRole == INTCP_ROLE_MIDNODE)
            {
                intBufBytes -= (*p)->rangeEnd - (*p)->rangeStart;
                intBuf.erase(p);
            }
            // if(nodeRole==INTCP_ROLE_REQUESTER && rmt_sndq_rest<= 0){
            //     break;
            // }
        }
    }
    LOG(TRACE, "loop %d", loop);
    if (cntTimeout > 0)
        LOG(TRACE, "flushIntBuf Intbuf size %d cntAll %d needSend %d retransed %d timeout %d", intBufSize, cntAll, cntNeedSend, cntRetransed, cntTimeout);
    if (srtt != 0 && !reach_limit)
    {
        intOutputLimit = min(intOutputLimit, newOutput);
    }
    stat.cntTimeout += cntTimeout;
    if (cntTimeout > 0)
    {
        LOG(TRACE, "RTO %d %d/%d/%d", rto, cntTimeout, cntRetransed, cntAll);
        conseqTimeout++;
    }
    if (RTTscheme == INTCP_RTT_SCHM_EXPO && cntTimeout > 0 && conseqTimeout < 10)
    {
        srtt = srtt * INTCP_RTO_EXPO;
        rto = rto * INTCP_RTO_EXPO;
    }
}

// sndQueue -> send straightforward;
void IntcpTransCB::flushData()
{
    IUINT32 current = _getMillisec();
    IUINT32 flushIntv = INTCP_UPDATE_INTERVAL;
    if (lastFlushTs != 0)
    {
        flushIntv = current - lastFlushTs;
    }

    // TODO CC -- cwnd/sendingRate; design token bucket
    LOG(TRACE, "%.1f %u", rmtSendRate, flushIntv);
    // DEBUG
    //  rmtSendRate = 19;
    int newOutput = mbitToBytes(rmtSendRate * flushIntv / 1000);
    //printf("%f\n",rmtSendRate);
    dataOutputLimit += newOutput;
    LOG(TRACE, "dataOutputLimit %d bytes %ld", dataOutputLimit, sndQueue.size());
    // int dataOutputLimit = 65536;

    char *sentEnd = tmpBuffer.get();
    int sizeToSend = 0;

    bool reach_limit = false;
    list<shared_ptr<IntcpSeg>>::iterator p, next;
    shared_ptr<IntcpSeg> segPtr;
#ifndef HBH_CC
    if(nodeRole==INTCP_ROLE_MIDNODE)
        dataOutputLimit = 65536;
#endif
    for (p = sndQueue.begin(); p != sndQueue.end(); p = next)
    {
        next = p;
        next++;
        segPtr = *p;
#ifdef CUT_PAYLOAD
        if (dataOutputLimit < segPtr->len+INTCP_OVERHEAD)
#else
        if (dataOutputLimit < segPtr->len)
#endif
        {
            LOG(TRACE, "dataOutputLimit %d bytes seglen %d qsize %ld", dataOutputLimit, segPtr->len, sndQueue.size());

            reach_limit = true;
            break;
        }
        else
        {

#ifdef CUT_PAYLOAD
        #ifdef HBH_CC
            dataOutputLimit -= (INTCP_OVERHEAD+segPtr->len);
        #else
            if(nodeRole==INTCP_ROLE_RESPONDER){
                dataOutputLimit -= (INTCP_OVERHEAD+segPtr->len);
            }
        #endif
#else
            dataOutputLimit -= segPtr->len;
#endif
            stat.sentINTCP += segPtr->len;
        }

        sizeToSend = (int)(sentEnd - tmpBuffer.get());
        if (sizeToSend + (INTCP_OVERHEAD + segPtr->len) > INTCP_MTU)
        {
            output(tmpBuffer.get(), sizeToSend, INTCP_ROLE_REQUESTER);
            sentEnd = tmpBuffer.get();
        }

        segPtr->sn = dataNextSn++;
        //LOG(SILENT, "flushData sn %d [%d,%d), ts %u, sndQ %u", segPtr->sn, segPtr->rangeStart, segPtr->rangeEnd, _getMillisec(),sndQueueBytes/INTCP_MSS);
#ifdef HBH_CC
        segPtr->ts = _getMillisec() - intHopOwd;
#else
        if(nodeRole==INTCP_ROLE_RESPONDER)
            segPtr->ts = _getMillisec() - intHopOwd;
#endif

        // make sure the midnode doesn't change wnd from responder;
        // TODO if it's from cache, wnd=0
        if (nodeRole == INTCP_ROLE_RESPONDER)
        {
            segPtr->wnd = getIntDev();
            LOG(TRACE, "%d %d", sndQueueBytes, segPtr->wnd);
        }
        LOG(TRACE, "flushData sn %d [%d,%d), ts %u, wnd %d, sndQ %u", segPtr->sn, segPtr->rangeStart, segPtr->rangeEnd, segPtr->ts, segPtr->wnd, sndQueueBytes/INTCP_MSS);
        sentEnd = encodeSeg(sentEnd, segPtr.get());
        memcpy(sentEnd, segPtr->data, segPtr->len);
        sentEnd += segPtr->len;
#ifdef CUT_PAYLOAD
        sndQueueBytes -= (segPtr->len+INTCP_OVERHEAD);
#else
        sndQueueBytes -= segPtr->len;
#endif
        sndQueue.erase(p);
    }
    // if cwnd is not enough for data, the remain wnd can be used for next loop
    if (!reach_limit)
    {
        dataOutputLimit = min(dataOutputLimit, newOutput); // 0;
    }

    // if(cwnd!=0) {
    //     LOG(DEBUG,"%d %d",rmt_cwnd,reach_limit);
    // }
    // flush remain segments
    sizeToSend = (int)(sentEnd - tmpBuffer.get());
    if (sizeToSend > 0)
    {
        output(tmpBuffer.get(), sizeToSend, INTCP_ROLE_REQUESTER);
    }
}

void IntcpTransCB::flush()
{
    IUINT32 tmp = _getMillisec();
    // 'update' haven't been called.
    if (updated == 0)
        return;

    if (nodeRole != INTCP_ROLE_RESPONDER)
    {
        flushIntQueue();
        flushIntBuf();
#ifdef CUT_PAYLOAD
        flushDataHoles();
#endif
    }
    if (nodeRole != INTCP_ROLE_REQUESTER)
    {
        flushData();
    }
    lastFlushTs = tmp;
}

//---------------------------------------------------------------------
// update state (call it repeatedly, every 10ms-100ms), or you can ask
// check when to call it again (without input/_send calling).
// 'current' - current timestamp in millisec.
//---------------------------------------------------------------------
void IntcpTransCB::update()
{
    IUINT32 current = _getMillisec();
    if (current - stat.lastPrintTs > 1000)
    {
        // DEBUG
        // int t = (current-stat.startTs)/1000%5;
        // if(t<2 && current-stat.startTs>5000){
        rcvBuf.clear();
        rcvBufItrs.clear();
        //}

        if (nodeRole == INTCP_ROLE_REQUESTER)
        {
            LOG(SILENT, "%u. %4d %d C %.1f ↑%.1f ↓%.1f+%.2f iQ %ld iB %d rB %ld T %d D %d Hthrp %.2f",
                current, srtt, hopSrtt,
                cwnd,
                float(getDataSendRate()) / 100,
                bytesToMbit(stat.recvedINTCP) * 1000 / (current - stat.lastPrintTs),
                bytesToMbit(stat.recvedUDP - stat.recvedINTCP) * 1000 / (current - stat.lastPrintTs),
                intQueue.size(),
                intBufBytes / INTCP_MSS,
                rcvBuf.size(),
                stat.cntTimeout, stat.cntDataHole,
                thrpLastPeriod);
            // NOTE
            printf("  %4ds %.2f Mbits/sec receiver\n",
                   (current - stat.startTs) / 1000,
                   bytesToMbit(stat.recvedINTCP) * 1000 / (current - stat.lastPrintTs));
            fflush(stdout);
        }
        if (nodeRole == INTCP_ROLE_MIDNODE)
        {
            LOG(SILENT, "CC| %d C %.1f ↑%.1f ↓%.1f I %d D %d Hthrp %.2f",
                hopSrtt,
                cwnd,
                float(getDataSendRate()) / 100,
                bytesToMbit(stat.recvedUDP) * 1000 / (current - stat.lastPrintTs),
                stat.cntIntHole, stat.cntDataHole,
                thrpLastPeriod);
            fflush(stdout);
        }
        if (nodeRole != INTCP_ROLE_REQUESTER)
        {
            LOG(SILENT, "%4d r↑%.1f sent %.1f sQ %d I %d",
                // stat.ssid,
                (current - stat.startTs) / 1000,
                rmtSendRate,
                bytesToMbit(stat.sentINTCP) * 1000 / (current - stat.lastPrintTs),
                sndQueueBytes / INTCP_MSS,
                stat.cntIntHole);
            fflush(stdout);
        }
        stat.reset();
    }

    if (updated == 0)
    {
        updated = 1;
        nextFlushTs = current;
    }

    IINT32 slap = _itimediff(current, nextFlushTs);

    if (slap >= 0 || slap < -10000)
    {
        // LOG(DEBUG,"iq %ld ib %ld pit %ld sq %ld rb %ld rq %ld",
        //         intQueue.size(), intBuf.size(),pendingInts.size(),
        //         sndQueue.size(),rcvBuf.size(),rcvQueue.size());
        flush();
        if (slap >= INTCP_UPDATE_INTERVAL || slap < -10000)
        {
            nextFlushTs = current + INTCP_UPDATE_INTERVAL;
        }
        else
        {
            nextFlushTs = nextFlushTs + INTCP_UPDATE_INTERVAL;
        }
    }
}

//---------------------------------------------------------------------
// Determine when should you invoke update:
// returns when you should invoke update in millisec, if there
// is no input/_send calling. you can call update in that
// time, instead of call update repeatly.
// Important to reduce unnacessary update invoking. use it to
// schedule update (eg. implementing an epoll-like mechanism,
// or optimize update when handling massive kcp connections)
//---------------------------------------------------------------------
IUINT32 IntcpTransCB::check()
{
    IUINT32 currentU = _getMillisec();
    if (updated == 0)
    {
        return currentU;
    }
    IUINT32 _ts_flush = nextFlushTs;
    if (_itimediff(currentU, _ts_flush) >= 0 ||
        _itimediff(currentU, _ts_flush) < -10000)
    {
        return currentU;
    }

    IUINT32 tmin = _ts_flush; //_ts_flush>currentU is guaranteed
    // calculate most near rto
    //  for (auto p = intBuf.begin(); p != intBuf.end(); p++) {
    //      if (_itimediff((*p)->resendts*1000, currentU)<=0) {
    //          return currentU;
    //      }
    //      tmin = _imin_(tmin,(*p)->resendts*1000);
    //  }

    tmin = _imin_(tmin, currentU + INTCP_UPDATE_INTERVAL);
    return tmin;
}

// rate limitation on sending data
IINT16 IntcpTransCB::getDataSendRate()
{
    float rate;
    if (hopSrtt == 0)
    { // haven't receive feedback
        rate = INTCP_SENDRATE_MIN;
    }
    else
    {
        // suppose rcvBuf and rcvQueue is always big enough
        // NOTE hopSrtt -> minHrtt
        int minHrtt = 999999;
        for (auto pr : hrttQueue)
        {
            minHrtt = min(minHrtt, pr.second);
        }
        rate = bytesToMbit(cwnd * INTCP_MSS) / minHrtt * 1000; // Mbps
        //printf("cwmd %f, minHrtt %u, rate %f\n",cwnd, minHrtt,rate);
        //rate = thrpLastPeriod;
        //printf("%.1f\n",rate);
        if (nodeRole != INTCP_ROLE_REQUESTER)
        { // MIDNODE
            float rateForQueue = (bytesToMbit(INTCP_SNDQ_MAX) - bytesToMbit(sndQueueBytes)) / hopSrtt * 1000 + rmtSendRate;
            // float rateForQueue = max(float(0),bytesToMbit(INTCP_SNDQ_MAX)-bytesToMbit(sndQueueBytes))/hopSrtt*1000+rmtSendRate;
            /*
            float rateForQueue;
            float IncreaseRate = (bytesToMbit(INTCP_SNDQ_MAX)-bytesToMbit(sndQueueBytes))/hopSrtt*1000;
            if(IncreaseRate<0)
                rateForQueue = IncreaseRate/4 + rmtSendRate;
            else
                rateForQueue = IncreaseRate + rmtSendRate;
            */
            LOG(TRACE, "rate %.2f rateForQueue %.2f rmtSendRate %.2f", rate, rateForQueue,rmtSendRate);
            rate = min(rate, rateForQueue);
            //rate = rateForQueue;
        }
        rate = max(rate, INTCP_SENDRATE_MIN);
    }
    rate = min(rate, INTCP_SENDRATE_MAX);
    // DEBUG
    //return IINT16(18*100);
    return IINT16(rate * 100);
    
}
// deviation of sendQueueBytes - INTCP_SNDQ_MAX
IINT16 IntcpTransCB::getIntDev()
{
    return IINT16(INTCP_SNDQ_MAX / INTCP_MSS) - IINT16(sndQueueBytes / INTCP_MSS);
    // IUINT16((INTCP_SNDQ_MAX - _imin_(INTCP_SNDQ_MAX,sndQueueBytes))/INTCP_MSS);
}

// cc
void IntcpTransCB::updateCwnd(IUINT32 dataLen)
{
    IUINT32 current = _getMillisec();

    bool congSignal;
    int minHrtt = 99999999;
    if (CCscheme == INTCP_CC_SCHM_LOSSB)
    {
        congSignal = hasLossEvent;
        hasLossEvent = false;
    }
    else if (CCscheme == INTCP_CC_SCHM_RTTB)
    {
        while (!hrttQueue.empty() && current - hrttQueue.begin()->first > HrttMinWnd)
        {
            hrttQueue.pop_front();
        }
        // NOTE avoid too long hrttQueue
        if (current > (hrttQueue.rbegin())->first + hopSrtt / 2)
        {
            hrttQueue.push_back(pair<IUINT32, int>(current, hopSrtt));
        }
        for (auto pr : hrttQueue)
        {
            minHrtt = min(minHrtt, pr.second);
        }
        if (thrpLastPeriod == -1)
        {
            congSignal = false;
        }
        else
        {
            congSignal = mbitToBytes(thrpLastPeriod) * (hopSrtt - minHrtt) / 1000 > QueueingThreshold;
        }
    }
    float cwndOld = cwnd; // for debug
    // LOG(SILENT,"cwnd %d mtu\n",cwnd);

    ccDataLen += dataLen;

    if (ccState == INTCP_CC_SLOW_START)
    {
        if (congSignal || cwnd >= INTCP_SSTHRESH_INIT)
        { // entering ca
            ccDataLen = cwnd * INTCP_MSS;
            ccState = INTCP_CC_CONG_AVOID;
        }
        else
        {
            // NOTE 5.0
            cwnd = (ccDataLen / INTCP_MSS) * (pow(2, min(5.0, double(hopSrtt) / INTCP_RTT0)) - 1);
        }
    }
    if (ccState == INTCP_CC_CONG_AVOID && allow_cwnd_decrease(current))
    {
        if (congSignal)
        {
            // NOTE cwnd decrease function
            if (CCscheme == INTCP_CC_SCHM_LOSSB)
            {
                cwnd = max(cwnd / 2, INTCP_CWND_MIN);
            }
            else if (CCscheme == INTCP_CC_SCHM_RTTB)
            {
#ifdef CUT_PAYLOAD
                float cwndNew = (float(mbitToBytes(thrpLastPeriod)) / 1000 * minHrtt / INTCP_MSS) * 0.8;
#else
                float cwndNew = (float(mbitToBytes(thrpLastPeriod)) / 1000 * minHrtt / INTCP_MSS) * 0.9;
#endif
                LOG(TRACE, "--- hopSrtt %d minHrtt %d C %.1f->%.1f ↓%.1f delta %u --- ", hopSrtt, minHrtt, cwnd, cwndNew, thrpLastPeriod, hopSrtt - minHrtt);
                
                cwnd = max(cwndNew, INTCP_CWND_MIN);
            }
            lastCwndDecrTs = current;
            ccDataLen = 0;
            congSignal = false;
        }
        else
        {
            bool allowInc = allow_cwnd_increase();
            // printf("ccDataLen=%u bytes,cwnd = %u\n",ccDataLen,cwnd);
            //  float cwndGain = pow(float(hopSrtt)/INTCP_RTT0,2);
            //  if(ccDataLen*cwndGain > cwnd*INTCP_MSS && allowInc){
            //      cwnd += 1;
            //      ccDataLen = 0;
            //  }else if (ccDataLen*cwndGain > 5*cwnd*INTCP_MSS && (!allowInc)){
            //      cwnd = max(INTCP_CWND_MIN,cwnd-1);
            //      ccDataLen = 0;
            //  }
            if (ccDataLen > cwnd * INTCP_MSS / 10 && allowInc)
            {
#ifdef CUT_PAYLOAD
                cwnd += 1; // 0.1
#else
                cwnd += 0.1;
#endif
                ccDataLen = 0;
            }
            else if (ccDataLen > 5 * cwnd * INTCP_MSS / 10 && (!allowInc))
            {
                cwnd = max(INTCP_CWND_MIN, cwnd - 0.1f);
                ccDataLen = 0;
            }
        }
    }
    if (cwndOld != cwnd)
    {
        LOG(TRACE, "%u cwnd %.1f", current, cwnd);
    }
}

bool IntcpTransCB::allow_cwnd_increase()
{
    if (thrpLastPeriod == 0 || cwnd == 0)
        return true;
    if (thrpLastPeriod < (bytesToMbit(cwnd * INTCP_MSS) / hopSrtt * 1000) / 2)
        return false;
    return true;
}

bool IntcpTransCB::allow_cwnd_decrease(IUINT32 current)
{
    if (lastCwndDecrTs == 0 || hopSrtt == 0)
        return true;
    // NOTE rtt*2
    if (_itimediff(current, lastCwndDecrTs) < hopSrtt * 2)
        return false;
    return true;
}

// assume that there is exactly one INTCP packet in one recvUDP()
int IntcpTransCB::judgeSegDst(const char *data, long size)
{
    if (data == nullptr || (int)size < (int)INTCP_OVERHEAD)
        return -1;
    IUINT8 cmd;
    // have to use a typecasting here, not good
    decode8u((char *)data, &cmd);
    if (cmd == INTCP_CMD_INT)
    {
        return INTCP_ROLE_RESPONDER;
    }
    else
    {
        return INTCP_ROLE_REQUESTER;
    }
}

// peek data size
int IntcpTransCB::peekSize()
{

    if (rcvQueue.empty())
        return -1; // recv_queue

    return (*rcvQueue.begin())->len;
}

int IntcpTransCB::getRwnd()
{
    if (rcvQueue.size() < INTCP_WND_RCV)
    {
        return INTCP_WND_RCV - rcvQueue.size();
    }
    return 0;
}

int IntcpTransCB::getWaitSnd()
{
    return sndQueue.size();
}

float IntcpTransCB::getCwnd()
{
    return cwnd;
}

//--- Mega=1000*1000 ---//

float bytesToMbit(int bytes)
{
    return float(bytes) / 125000;
}
int mbitToBytes(float mbit)
{
    return mbit * 125000;
}
