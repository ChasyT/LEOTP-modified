#!/usr/bin/python3
# /INTCP$ app*/int*/intcpc > autoTest/misc/templog.txt

import time
import matplotlib.pyplot as plt
import os
import sys
import functools
import argparse
import seaborn as sns
import numpy as np 
from scipy.stats import scoreatpercentile
import statsmodels.api as sm

sys.path.append(os.path.dirname(os.path.dirname(os.sys.path[0])))
sys.path.append(os.path.dirname(os.sys.path[0]))
from FileUtils import createFolder, fixOwnership, writeText
import MyParam


logFilePath = os.sys.path[0]+'/templog.txt'
times = []
cwnds = []
with open(logFilePath,"r") as f:
    lines = f.readlines()
    for line in lines:
        try:
            nums = line.split('cwnd ')[1].split()
            times.append(int(nums[0]))
            cwnds.append(int(nums[1]))
        except:
            continue
for i in range(1, len(times)):
    times[i] = (times[i]-times[0])/1000
times[0] = 0
print(f'time len {times[-1]} sample num {len(times)}')
def plotOneFig(times,cwnds):
    plt.figure(figsize=(8,5),dpi = 320)
    # plt.ylim((0,1000))
    plt.plot(times, cwnds)#,marker='x')
    # legend_font = {'size':12}#"family" : "Times New Roman",
    # plt.legend(frameon=True,prop=legend_font)
    plt.xlabel('time',size=12) #family="Times New Roman",
    plt.ylabel('cwnd(MSS)',size=12)#family="Times New Roman",
    plt.title('time-cwnd',size=15)#family="Times New Roman",
    plt.yticks(size=12)#fontproperties = 'Times New Roman',
    plt.xticks(size=12)#fontproperties = 'Times New Roman',
    #plt.tight_layout()
    plt.savefig(os.sys.path[0]+'/time-cwnd.png')
    return

R=50000
plotOneFig(times[:R],cwnds[:R])
fixOwnership(os.sys.path[0],'r')