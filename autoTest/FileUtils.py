import os

# Change the owner of the file to SUDO_UID
def fixOwnershipSingle(path):
    uid = os.environ.get('SUDO_UID')
    gid = os.environ.get('SUDO_GID')
    if uid is not None:
        os.chown(path, int(uid), int(gid))
def fixOwnership(path,recursive='n'):
    if recursive == 'r':
        fixOwnershipSingle(path)
        for root,dirs,files in os.walk(path):
            for dir in dirs:
                fixOwnershipSingle(os.path.join(root, dir))
            for file in files:
                fixOwnershipSingle(os.path.join(root, file))
    else:
        fixOwnershipSingle(path)

def createFolder(path):
    if not os.path.exists(path):
        parent = os.path.dirname(path)
        if os.path.exists(parent):
            createFolder(parent)
        os.makedirs(path, mode=0o0777)
        fixOwnership(path)

def writeText(path, string):
    with open(path,'w') as f:
        f.write(string)
    fixOwnership(path,'r')

def delFile(path):
    if os.path.exists(path):
        os.remove(path)