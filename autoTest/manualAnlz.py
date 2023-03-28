import matplotlib.pyplot as plt
import math
import numpy as np
from get_trace import get_trace
import os
import sys
from FileUtils import createFolder, fixOwnership, writeText
import statsmodels.api as sm

plt.rc('font',family='Times New Roman')
tick_size = 20
label_size = 24
legend_size = 24
line_width = 3.2
marker_size = 10

# for all graph
borderpad = 0.1
labelspacing = 0
borderaxespad = 0.05

# for cdf,plot and seq
handletextpad = 0.5
handlelength = 1.5

resultPath = "./result/motivation"

def motivation_leo_rtt(city1,city2):
    plt.figure(figsize=(8,5),dpi = 320)
    __,__,__,links_params = get_trace(city1,city2)
    rtts = [sum(lp["rtt"]) for lp in links_params]
    plt.plot(list(range(len(rtts))),rtts,linewidth=line_width)
    #plt.legend(loc='best',fontsize=legend_size,borderpad=0.2,labelspacing=0.2,handlelength=1,handletextpad=0.3)
    title = "leo_rtt_seq"
    #plt.title(title)
    plt.xlabel("Time(s)",size=label_size)
    plt.ylabel("Beijing-Paris RTT(ms)",size=label_size)

    plt.xlim((0,len(rtts)))
    #plt.ylim((60,80))
    plt.tick_params(labelsize=tick_size)
    plt.tight_layout()
    plt.grid()
    plt.savefig('%s/%s.png' % (resultPath, title))
    plt.savefig('%s/%s.pdf' % (resultPath, title))

def get_threoetical_value(hop,mode="ete",metric="thrp",bw=20,hopRtt=10,hopLoss=0.01):
    if metric=="thrp":
        if mode=="ete":
            return bw*(1-hop*hopLoss)
        else:
            return bw*(1-hopLoss)
    else:
        if mode=="ete":
            return hopRtt*hop*(1+hop*hopLoss)
        else:
            return hopRtt*hop*(1+hopLoss)

def motivation_thrp_threoetical(bw=20,hopRtt=10,hopLoss=0.01,hops=[1,2,3,4,5]):
    plt.figure(figsize=(8,5),dpi = 320)
    plt.plot(hops,
             [get_threoetical_value(i,"ete","thrp",bw=bw,hopRtt=hopRtt,hopLoss=hopLoss) for i in hops],
             label ="end to end",linewidth=line_width,marker='o',markersize=marker_size
            )
    plt.plot(hops,
             [get_threoetical_value(i,"hbh","thrp",bw=bw,hopRtt=hopRtt,hopLoss=hopLoss) for i in hops],
             label = "hop by hop",linewidth=line_width,marker='s',markersize=marker_size
            )
    title = "thrp_threoetical"
    plt.legend(frameon=True,fontsize=legend_size,borderpad=borderpad,labelspacing=labelspacing,borderaxespad=borderaxespad,handlelength=handlelength,handletextpad=handletextpad)
    plt.xlabel("Hop count",size=label_size)
    plt.ylabel("Throughput(Mbps)",size=label_size)
    #plt.xlim((0,17))
    plt.ylim((15,20))
    plt.tick_params(labelsize=tick_size)
    plt.tight_layout()
    plt.grid()
    plt.savefig('%s/%s.png' % (resultPath, title))
    plt.savefig('%s/%s.pdf' % (resultPath, title))

def motivation_rtt_threoetical(max_hop=10,bw=20,hopRtt=10,hopLoss=0.01):
    plt.figure(figsize=(8,5),dpi = 320)
    plt.plot([i for i in range(1,max_hop+1)],
             [get_threoetical_value(i,"ete","rtt",bw=bw,hopRtt=hopRtt,hopLoss=hopLoss) for i in range(1,max_hop+1)],
             label ="end to end",linewidth=line_width,marker='o',markersize=marker_size
            )
    plt.plot([i for i in range(1,max_hop+1)],
             [get_threoetical_value(i,"hbh","rtt",bw=bw,hopRtt=hopRtt,hopLoss=hopLoss) for i in range(1,max_hop+1)],
             label = "hop by hop",linewidth=line_width,marker='s',markersize=marker_size
            )
    title = "rtt_threoetical"
    plt.legend(frameon=True,fontsize=legend_size,borderpad=borderpad,labelspacing=labelspacing,borderaxespad=borderaxespad,handlelength=handlelength,handletextpad=handletextpad)
    plt.xlabel("Hop count",size=label_size)
    plt.ylabel("RTT(ms)",size=label_size)
    #plt.ylim((0,bw))
    plt.tick_params(labelsize=tick_size)
    plt.tight_layout()
    plt.grid()
    plt.savefig('%s/%s.png' % (resultPath, title))
    plt.savefig('%s/%s.pdf' % (resultPath, title))

def C(n,m): #n>m
    return math.factorial(n)/(math.factorial(m)*math.factorial(n-m))

def gen_owd_distribute(hopCount,hopOwd,hopLoss,N,mode="e2e"):
    owds = []
    if mode=="e2e":
        total_loss = 1-(1-hopLoss)**hopCount
        retran_time = 0
        while True:
            p = (total_loss**retran_time)*(1-total_loss)
            owd = (1+2*retran_time)*hopCount*hopOwd
            times = int(p*N)
            if times>=1:
                print(times,owd)
                owds = owds + [owd]*times
                retran_time += 1
            else:
                break
    else:
        retran_time = 0
        while True:
            p = C(hopCount-1+retran_time,retran_time)*(hopLoss**retran_time)*((1-hopLoss)**hopCount)
            owd = hopCount*hopOwd + 2*retran_time*hopOwd
            times = int(p*N)
            if times>=1:
                print(times,owd)
                owds = owds + [owd]*times
                retran_time += 1
            else:
                break
    return owds

def motivation_owd_cdf(hop=5,hopOwd=20,hopLoss=0.01,N=100000):
    plt.figure(figsize=(8,5),dpi = 320)
    owds_e2e = gen_owd_distribute(hop,hopOwd,hopLoss,N,"e2e")
    owds_hbh = gen_owd_distribute(hop,hopOwd,hopLoss,N,"hbh")
    print(len(owds_e2e),len(owds_hbh))
    x_max = max(owds_e2e[-1],owds_hbh[-1])
    x = np.linspace(0,x_max,num=500)

    # end to end
    ecdf1 = sm.distributions.ECDF(owds_e2e)
    y = ecdf1(x)
    plt.step(x,y,linewidth=line_width)

    # hop by hop
    ecdf2 = sm.distributions.ECDF(owds_hbh)
    y = ecdf2(x)
    plt.step(x,y,linewidth=line_width,linestyle="--")

    legends = ["end to end","hop by hop"]
    title = "rtt_theoretical_cdf"

    plt.xlim((0,x_max))
    plt.ylim((0.9,1.005))
    plt.legend(legends,frameon=True,fontsize=legend_size,borderpad=borderpad,labelspacing=labelspacing,borderaxespad=borderaxespad,handlelength=handlelength,handletextpad=handletextpad)
    plt.xlabel("OWD(ms)",size=label_size)
    plt.ylabel("CDF",size=label_size)
    plt.tick_params(labelsize=tick_size)
    plt.tight_layout()
    plt.grid()
    plt.savefig('%s/%s.png' % (resultPath, title))
    plt.savefig('%s/%s.pdf' % (resultPath, title))

def test():
    for i in range(8):
        plt.plot([j for j in range(5)],[i for j in range(5)],label="%d"%(i))
    plt.legend()
    plt.show()

if __name__=="__main__":
    os.chdir(sys.path[0])
    createFolder(resultPath)
    #motivation_leo_rtt(6,24)
    #motivation_thrp_threoetical(hops = [3*i+1 for i in range(5)])
    #motivation_rtt_threoetical(max_hop=20)
    motivation_owd_cdf(hop=10,hopOwd=10,hopLoss=0.005)
    #test()
    fixOwnership(resultPath,'r')
