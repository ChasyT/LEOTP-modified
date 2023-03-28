import matplotlib.pyplot as plt

def getPlotParam(cc,isRttTest=False):
    if not isRttTest:
        if cc[0] == 'h':
            #color = 'orangered'
            color = 'orange'
        elif cc[0] == 'c':
            #color = 'royalblue'
            color = 'mediumblue'
        else:
            color = 'g'

        if cc[1] == 'e2e':
            marker = 'x'
            linestyle = '--'
        else:
            marker = 's'
            linestyle = '-'
    else:
        if cc[1] == 'e2e':
            #color = 'purple'
            color = 'orange'
            marker = 'x'
        else:
            #color = 'green'
            color = 'mediumblue'
            marker = 's'
        linestyle = '-'
    return color,marker,linestyle
    
def plotSeq(resultPath, result, keyX, groups, ccs, title, legends=[],isRttTest=False):
    labelsize = 28
    titlesize = 28
    ticksize = 28
    legendsize = 24
    print("entering plotseq")
    #plt.figure(figsize=(5,5),dpi=200)
    plt.figure(figsize=(8,5),dpi = 320)
    plt.gcf().subplots_adjust(bottom=0.2,left=0.2)
    #plt.figure(dpi=200)
    if not isRttTest:
        plt.ylim((0,20))
    else:
        pass
        #plt.ylim((0,1000))
    legend_font = {"family" : "Times New Roman",'size':legendsize}
    if len(groups)==1:
        group = groups[0]
        plt.plot([testParam.get(keyX) for testParam in group],
                 [result[testParam] for testParam in group])
    else:
        for i,group in enumerate(groups):
            # print(len(group))
            # for testParam in group:
            #     print(testParam.get(keyX),result[testParam])

            color,marker,linestyle = getPlotParam(ccs[i],isRttTest)

            if not isRttTest:
                print(group)
                print(result[i])
                print(legends[i])
                plt.plot(group,
                            result[i], label=legends[i],marker=marker,linestyle=linestyle,color=color,markersize=8,linewidth=1.5)
                #plt.legend()
            else:
                drawCondfidenceCurve(group,result,keyX,legends[i],color,marker,mode=2)
                #plt.legend()
        plt.legend(frameon=True,prop=legend_font)
    
    plt.xlabel(keyX,family="Times New Roman",size=labelsize) #(keyX.title()+'('+xunit+')')
    if isRttTest:
        plt.ylabel('one way delay(ms)',family="Times New Roman",size=labelsize),
        #plt.ylabel('error rate')
    else:
        plt.ylabel('Throughput(Mbps)',family="Times New Roman",size=labelsize)
    # plt.title(title,family="Times New Roman",size=titlesize)
    plt.yticks(fontproperties = 'Times New Roman',size=ticksize)
    plt.xticks(fontproperties = 'Times New Roman',size=ticksize)
    #plt.tight_layout()
    plt.savefig('%s/%s.pdf' % (resultPath, title))
    return

resultPath='./tmp'

result=[[17.7,13.9,13.1,12.3,12.1],
[18.7,18.3,18.1,17.7,17.4],
[17.6,13.95,13,12.45,12.3],
[18.5,18.3,18.3,18.1,18.2]
]
keyX='Bandwidth period(s)'
groups=[[2,4,6,8,10],[2,4,6,8,10],[2,4,6,8,10],[2,4,6,8,10]]
ccs=[['c','e2e'],['c','hbh'],['h','e2e'],['h','hbh']]
title="varIntv - throughput"
legends = ['cubic end-to-end','cubic hop-by-hop',
    'hybla end-to-end','hybla hop-by-hop']
plotSeq(resultPath, result, keyX, groups, ccs, title, legends, False)

result=[[19,17.4,15.0,15.3,14.0],
[18.9,18.75,18.6,18.2,17.9],
[18.8,17.5,16.3,13.3,13],
[19,18.7,18.5,17.6,17.5]
]
keyX='Intermittent time(s)'
groups=[[2,4,6,8,10],[2,4,6,8,10],[2,4,6,8,10],[2,4,6,8,10]]
ccs=[['c','e2e'],['c','hbh'],['h','e2e'],['h','hbh']]
title="itmDown - throughput"
legends = ['cubic end-to-end','cubic hop-by-hop',
    'hybla end-to-end','hybla hop-by-hop']
plotSeq(resultPath, result, keyX, groups, ccs, title, legends, False)


