from mininet.node import Node

class TbNode(Node):
    def config(self, **params):
        super(self.__class__, self).config(**params)
        self.cmd('sysctl net.ipv4.ip_forward=1')
    def terminate( self ):
        self.cmd('sysctl net.ipv4.ip_forward=0')
        super(self.__class__, self).terminate()

# class EndpointNode(Node):
#     def config(self, **params):
#         super(self.__class__, self).config(**params)
#         # self.cmd()
#     def terminate( self ):
#         # self.cmd()
#         super(self.__class__, self).terminate()