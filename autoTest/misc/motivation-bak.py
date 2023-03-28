
    #1.1
    if tpsetName == "mot_rtt_6":
        tpSet = TestParamSet(tpsetName, TestParam(loss=0.1,sendTime=180,bw=20, varBw=0),keyX="rttSat",keysCurveDiff=["e2eCC","midCC"])
        rttSats = [20,50,100,200,300]
        for rttSat in rttSats:
            tpSet.add(rttSat=rttSat,rttTotal=rttSat+50,e2eCC="cubic",midCC=['nopep','cubic'])
            tpSet.add(rttSat=rttSat,rttTotal=rttSat+50,e2eCC="hybla",midCC=['nopep','hybla'])
    
    #1.1 new
    elif tpsetName == "mot_rtt_7":
        tpSet = TestParamSet(tpsetName, TestParam(loss=0.1,sendTime=180,bw=20, varBw=0),keyX="rttSat",keysCurveDiff=["e2eCC","midCC"])
        rttSats = [20,50,100,150,200,250,300]
        for rttSat in rttSats:
            tpSet.add(rttSat=rttSat,rttTotal=rttSat+50,e2eCC="cubic",midCC=['nopep','cubic'])
            tpSet.add(rttSat=rttSat,rttTotal=rttSat+50,e2eCC="hybla",midCC=['nopep','hybla'])
            
    #2.1
    elif tpsetName == 'mot_bwVar_10':
        tpSet = TestParamSet(tpsetName, TestParam(loss=0,rttTotal=150,rttSat=100,bw=20,sendTime=180,varMethod='square',varIntv=8),keyX="varBw",keysCurveDiff=["e2eCC","midCC"])
        varBws = [0,4,8,12,16]
        for varBw in varBws:
            tpSet.add(varBw=varBw,e2eCC="cubic",midCC=['nopep','cubic'])
            tpSet.add(varBw=varBw,e2eCC="hybla",midCC=['nopep','hybla'])
    
    #2.2
    elif tpsetName == 'mot_bwVar_11':
        tpSet = TestParamSet(tpsetName, TestParam(loss=0,rttTotal=150,rttSat=100,bw=20,sendTime=180,varBw=8,varMethod='square'),keyX="varIntv",keysCurveDiff=["e2eCC","midCC"])
        #varIntvs = [1,2,4,6,8,10]
        varIntvs = [2,4,6,8,10]
        for varIntv in varIntvs:
            tpSet.add(varIntv=varIntv,e2eCC="cubic",midCC=['nopep','cubic'])
            tpSet.add(varIntv=varIntv,e2eCC="hybla",midCC=['nopep','hybla'])
    
    #2.1 new
    elif tpsetName == 'mot_bwVar_12':
        tpSet = TestParamSet(tpsetName, TestParam(loss=0,rttTotal=150,rttSat=100,bw=20,sendTime=180,varMethod='square',varIntv=8),keyX="varBw",keysCurveDiff=["e2eCC","midCC"])
        varBws = [0,3,6,9,12,15,18]
        for varBw in varBws:
            tpSet.add(varBw=varBw,e2eCC="cubic",midCC=['nopep','cubic'])
            tpSet.add(varBw=varBw,e2eCC="hybla",midCC=['nopep','hybla'])
    
    #2.2 new
    elif tpsetName == 'mot_bwVar_13':
        tpSet = TestParamSet(tpsetName, TestParam(loss=0,rttTotal=150,rttSat=100,bw=20,sendTime=180,varBw=15,varMethod='square'),keyX="varIntv",keysCurveDiff=["e2eCC","midCC"])
        #varIntvs = [1,2,4,6,8,10]
        varIntvs = [2,4,6,8,10]
        #varIntvs = [2,4]
        #varIntvs = [2]
        for varIntv in varIntvs:
            tpSet.add(varIntv=varIntv,e2eCC="cubic",midCC=['nopep','cubic'])
            tpSet.add(varIntv=varIntv,e2eCC="hybla",midCC=['nopep','hybla'])
            #tpSet.add(varIntv=varIntv,e2eCC="cubic",midCC=['cubic'])
            #tpSet.add(varIntv=varIntv,e2eCC="hybla",midCC=['nopep'])
                   
    #3.2
    elif tpsetName == 'mot_itm_6':
        tpSet = TestParamSet(tpsetName, TestParam(loss=0, rttTotal=150,rttSat=100,bw=40,sendTime=180),keyX="itmDown",keysCurveDiff=["midCC","e2eCC"])  
        #itmDowns = [4,6,8,10,12]
        #itmDowns = [0,1,2,3,4,5,6,7,8]
        #itmDowns = [0,2,4,6,8]
        itmDowns = [0,1,2,3,4]
        itmTotal = 20
        for itmDown in itmDowns:
            
            tpSet.add(itmTotal=itmTotal,itmDown=itmDown,e2eCC='cubic',midCC=['nopep','cubic']) 
            tpSet.add(itmTotal=itmTotal,itmDown=itmDown,e2eCC='hybla',midCC=['nopep','hybla'])
    
    #3.1        
    elif tpsetName == 'mot_itm_7':
        tpSet = TestParamSet(tpsetName, TestParam(loss=0,rttTotal=150,rttSat=100, bw=40, e2eCC='hybla', midCC='nopep',sendTime=180),keyX="itmTotal",keysCurveDiff=["midCC","e2eCC"])  
        itmDown = 2
        itmTotals = [10,15,20,25,30]
        #tpSet.add(itmTotal=25,itmDown=itmDown,e2eCC='cubic',midCC=['nopep']) 
        for itmTotal in itmTotals:
            tpSet.add(itmTotal=itmTotal,itmDown=itmDown,e2eCC='cubic',midCC=['nopep','cubic']) 
            tpSet.add(itmTotal=itmTotal,itmDown=itmDown,e2eCC='hybla',midCC=['nopep','hybla'])
    
    
    
    #4.1
    elif tpsetName == "mot_retran_3":
        tpSet = TestParamSet(tpsetName, TestParam(loss=0.1,sendTime=180,bw=20, varBw=0),keyX="rttSat",keysCurveDiff=["e2eCC","midCC"])
        rttSats = [20,50,100,200,300]
        #rttSats = [100,200]
        for rttSat in rttSats:
            
            #tpSet.add(rttSat=rttSat,rttTotal=rttSat+50,e2eCC="cubic",midCC=['nopep','cubic'])
            tpSet.add(rttSat=rttSat,rttTotal=rttSat+50,e2eCC="hybla",midCC=['nopep','hybla'])
            
    elif tpsetName == "mot_retran_4":
        tpSet = TestParamSet(tpsetName, TestParam(loss=5,sendTime=360,bw=20, varBw=0),keyX="rttSat",keysCurveDiff=["e2eCC","midCC"])
        rttSats = [20,50,100,200,300]
        #rttSats = [100,200]
        for rttSat in rttSats:
            
            #tpSet.add(rttSat=rttSat,rttTotal=rttSat+50,e2eCC="cubic",midCC=['nopep','cubic'])
            tpSet.add(rttSat=rttSat,rttTotal=rttSat+50,e2eCC="hybla",midCC=['nopep','hybla'])
    
    elif tpsetName == "mot_retran_5":
        tpSet = TestParamSet(tpsetName, TestParam(loss=1,sendTime=180,bw=20, varBw=0),keyX="rttSat",keysCurveDiff=["e2eCC","midCC"])
        rttSats = [20,50,100,200,300]
        #rttSats = [100,200]
        for rttSat in rttSats:
            
            #tpSet.add(rttSat=rttSat,rttTotal=rttSat+50,e2eCC="cubic",midCC=['nopep','cubic'])
            tpSet.add(rttSat=rttSat,rttTotal=rttSat+50,e2eCC="hybla",midCC=['nopep','hybla'])
    
    elif tpsetName == "mot_retran_6":
        tpSet = TestParamSet(tpsetName, TestParam(loss=0.5,sendTime=180,bw=20, varBw=0),keyX="rttSat",keysCurveDiff=["e2eCC","midCC"])
        rttSats = [20,50,100,200,300]
        #rttSats = [100,200]
        for rttSat in rttSats:
            
            #tpSet.add(rttSat=rttSat,rttTotal=rttSat+50,e2eCC="cubic",midCC=['nopep','cubic'])
            tpSet.add(rttSat=rttSat,rttTotal=rttSat+50,e2eCC="hybla",midCC=['nopep','hybla'])
    
    elif tpsetName == "mot_retran_7":
        tpSet = TestParamSet(tpsetName, TestParam(loss=0.1,sendTime=180,bw=20, varBw=0),keyX="rttSat",keysCurveDiff=["e2eCC","midCC"])
        rttSats = [20,50,100,200,300]
        #rttSats = [100,200]
        for rttSat in rttSats:
            
            #tpSet.add(rttSat=rttSat,rttTotal=rttSat+50,e2eCC="cubic",midCC=['nopep','cubic'])
            tpSet.add(rttSat=rttSat,rttTotal=rttSat+50,e2eCC="hybla",midCC=['nopep','hybla'])
    return tpSet
