import copy

SegUnit = {
        'bw': 'Mbps', 'rttSat': 'ms', 'loss': '%', 
        'itmDown': 's','itmTotal':'s', 
        'varBw': 'Mbps', 'varIntv': 's'
}
def getUnit(key):
    key = key.split('.')[-1]
    if key not in SegUnit:
            return ''
    else:
        return SegUnit[key]

class Param:
    BasicKeys = []
    def __init__(self, template=None, **kwargs):
        if template==None:
            keys = self.BasicKeys
        else:
            keys = list(template.__dict__.keys())
        for key in keys:
            if key in kwargs:
                value = kwargs[key]
                kwargs.pop(key)
            elif template.__class__ == self.__class__:
                value = template.get(key)
            else:
                raise Exception(f'seg "{key}" is missed in {self.__class__.__name__}.')
            self.set(key, value)

        # like 'linksParam.pep-h2.bw'
        for key in kwargs:
            self.set(key, kwargs[key])

    def set(self, key='nokey', value=None, **kwargs):
        if key != 'nokey':
            if issubclass(type(value), Param):
                newValue = value.copy()
            else:
                newValue = copy.deepcopy(value)
            obj = self
            if '.' in key:
                l,key = key.rsplit('.',1)
                obj = self.get(l)
            obj.__dict__[key] = newValue
        for kw in kwargs:
            self.set(kw, kwargs[kw])
        return self

    def get(self, key):
        if '.' in key:
            l,key = key.rsplit('.',1)
            return self.get(l).get(key)
        else:
            return self.__dict__[key]

    def compareKeys(self, param, keysCmp):
        for key in keysCmp:
            if self.get(key) != param.get(key):
                return False
        return True

    def serialize(self,indent=0,exclude=[]):
        IndentSpace = '    '
        string = ''
        nonParams = []
        for key in self.__dict__:
            if key in exclude:
                continue
            if issubclass(type(self.get(key)), Param):
                continue
            nonParams.append(key)
        if nonParams!=[]:
            string += IndentSpace*indent
            string += ', '.join([f'{key}={self.get(key)}' for key in nonParams])
            string += '\n'
            
        for key in self.__dict__:
            if key in exclude:
                continue
            if issubclass(type(self.get(key)), Param):
                string += IndentSpace*indent
                string += key+'\n'
                string += self.get(key).serialize(indent+1)
        return string

    # easy-to-read string of seg/key
    def segToStr(self, key):
        return '%s=%s%s'%(key, str(self.get(key)), getUnit(key))
    def keyToStr(self,key):
        return '%s(%s)'%(key, getUnit(key))

    def copy(self):
        return self.__class__(template=self)

LinkNameSep = '_'
class TopoParam(Param):
    BasicKeys = ['name',
            'numMidNode','nodes','links','pathes']
    def serialize(self,indent=0):
        IndentSpace = '    '
        string = f'{IndentSpace*(indent)}{self.name}\n'
        return string
    def linkNames(self):
        return [f'{l[0]}{LinkNameSep}{l[1]}' for l in self.links]

class LinkParam(Param):
    BasicKeys = ['bw', 'rtt', 'loss', 
            'itmTotal', 'itmDown',
            'varBw', 'varIntv', 'varMethod',
    ]
    # def serialize(self,indent=0,exclude=[]):
    #     if self.itmDown==0:
    #         exclude += ['itmTotal','itmDown']
    #     if self.varBw==0:
    #         exclude += ['varBw', 'varIntv', 'varMethod']
    #     return super().serialize(indent=indent,exclude=exclude)

class PartialLinkParam(Param):
    pass

class LinksParam(Param):
    BasicKeys = ['defaultLP']
    # dic: {'h1_pep1':{'bw':40,'loss':0.1}}
    def __init__(self, defaultLP=None, dic=None, template=None):
        if template != None:
            super().__init__(template)
            return
        self.set('defaultLP', defaultLP)
        if dic:
            for linkName in dic:
                for key in dic[linkName]:
                    self.set(linkName+'.'+key,dic[linkName][key])

    def get(self,key):
        if key not in self.__dict__:
            self.__dict__[key] = PartialLinkParam()
        return super().get(key)
    
    def getLP(self,linkName):
        if linkName in self.__dict__:
            tmpLP = self.defaultLP.copy()
            for key in self.get(linkName).__dict__:
                if key in LinkParam.BasicKeys:
                    tmpLP.set(key, self.get(linkName).get(key))
            return tmpLP
        else:
            return self.defaultLP

# AppParam is defined by user
class AppParam(Param):
    def __init__(self, template=None, **kwargs):
        super().__init__(template=template, **kwargs)


class TestParam(Param):
    BasicKeys = ['name',
            'topoParam','linksParam','appParam']
    def completeKey(self,key):
        first = key.split('.',1)[0]
        if first in self.BasicKeys + list(self.__dict__.keys()):
            return key
        else:
            #print(first)
            #print(self.appParam.__dict__)
            if first in self.appParam.__dict__:
                return 'appParam.' + key
            elif first in self.topoParam.__dict__:
                return 'topoParam.' + key
            else:
                return 'linksParam.' + key
    def get(self, key):
        return super().get(self.completeKey(key))
    def set(self, key, value):
        return super().set(self.completeKey(key), value)
    @classmethod
    def template(cls,topo,links,app):
        return TestParam(name="nameless",topoParam=topo,linksParam=links,appParam=app)
    

class TestParamSet:
    def __init__(self, tpsetName, topo,links,app, keyX='nokeyx', keysCurveDiff=[], keysPlotDiff=[]):
        self.tpsetName = tpsetName
        self.tpTemplate = TestParam.template(topo,links,app)
        self.keyX = keyX
        self.keysCurveDiff = keysCurveDiff
        self.keysPlotDiff = keysPlotDiff

        self.testParams = []
        
    # sometimes two or more segs are variable, but we don't want a Cartesian Product
    # at this time we must add the testParams manually by this function
    def add(self, segDict,*segGroupDicts):
        for key in segDict:
            if type(segDict[key]) != list:
                segDict[key] = [segDict[key]]

        lenSegDict = len(segDict.keys())
        lenSegGroupDicts = len(segGroupDicts)
        sumLen = lenSegDict+lenSegGroupDicts
        pos = [0] * sumLen
        while True:
            perm = {}
            tpNameItems = []
            for i,key in enumerate(list(segDict.keys())):
                perm[key] = segDict[key][pos[i]]
                if key=="topoParam":
                    tpNameItems.append(perm[key].name)
                else:
                    tpNameItems.append(key+'_'+str(perm[key]))
            for i,group in enumerate(segGroupDicts):
                keyInGroup = list(group.keys())[pos[i+lenSegDict]]
                # merge segGroup into perm
                # the right dict will cover the left one in shared segs
                perm = {**perm, **group[keyInGroup]}
                tpNameItems.append(keyInGroup)
            
            self.testParams.append(TestParam(
                    template=self.tpTemplate,
                    name='_'.join(tpNameItems),
                    **perm))

            # move to next one
            if sumLen==0:
                break
            ptr = sumLen - 1
            pos[ptr] += 1
            done = False
            while True:
                if ptr<lenSegDict:
                    numChoice = len(list(segDict.values())[ptr])
                else:
                    numChoice = len(segGroupDicts[ptr-lenSegDict])
                if pos[ptr] != numChoice:
                    break
                pos[ptr] = 0
                ptr -= 1
                if ptr == -1:
                    done = True
                    break
                pos[ptr] += 1
            if done:
                break
