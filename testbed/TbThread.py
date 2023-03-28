import threading
import time

Threads = []

LatchNum = 0
def latchRunning():
    return LatchNum > 0
def latchNumInc():
    global LatchNum
    LatchNum += 1
def latchNumDec():
    global LatchNum
    LatchNum -= 1
def latchNumReset():
    global LatchNum
    LatchNum = 0

class SleepException(Exception):
    pass
def sleepWithCaution(sec):
    for i in range(int(sec*10)):
        time.sleep(0.1)
        if not latchRunning():
            raise SleepException()

def NormalFunc(func):
    def funcNew(*args, **kwargs):
        time.sleep(0.5)
        print('[ Normal Thread start ] %s' % (func.__name__))
        try:
            ret = func(*args, **kwargs)
        except SleepException:
            ret = None
        print('[ Normal Thread  end  ] %s' % (func.__name__))
        return ret
    return funcNew

def LatchFunc(func):
    def funcNew(*args,**kwargs):
        print('[ Latch Thread start ] %s' % (func.__name__))
        latchNumInc()
        ret = func(*args,**kwargs)
        latchNumDec()
        print('[ Latch Thread  end  ] %s' % (func.__name__))
        return ret
    return funcNew

class TbThread:
    def __init__(self, isLatchThread, func):
        wrapper = LatchFunc if isLatchThread else NormalFunc
        self.func = wrapper(func)
        self.isLatchThread = isLatchThread
        self.thread = None
    def start(self, *args, **kwargs):
        self.thread = threading.Thread(daemon=not self.isLatchThread,
                target=self.func, args=args, kwargs=kwargs)
        self.thread.start()
    def join(self):
        self.thread.join()


def threadFunc(isLatchThread):
    def wrapper(func):
        Threads.append(TbThread(isLatchThread, func))
        return Threads[-1]
    return wrapper


atomicLock = threading.Lock()
def atomic(func):
    def wrapper(*args, **kwargs):
        atomicLock.acquire()
        ret = func(*args, **kwargs)
        atomicLock.release()
        return ret
    return wrapper
