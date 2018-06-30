
import sys
from .. import coins
from . import basenode

class RawNode(basenode.BaseNode):
  def __init__(self, data_dir=None, address=None, seek_peers=16, max_peers=125, bootstrap=True, log=sys.stdout, coin=coins.Newbitcoin):
    basenode.BaseNode.__init__(self,data_dir,address,seek_peers,max_peers,bootstrap,log,coin)

# from nbc.node import raw, basenode
# node = raw.RawNode(address=('127.0.0.1',20303))
# basenode.startServer(node)
