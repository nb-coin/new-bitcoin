
import asyncore
import socket

from .. import util
from .. import coins
from . import connection

from ..node import AddrInUseError, StopNode

class RawNode(asyncore.dispatcher, object):
  def __init__(self, data_dir=None, address=None, coin=coins.Newbitcoin):
    asyncore.dispatcher.__init__(self)
    self._coin = coin
    
    if data_dir is None:
      data_dir = util.default_data_directory()
    self._data_dir = data_dir
    
    self._peers = dict()
    
    self._listen = True
    if address is None:
      self._listen = False
      address = ('127.0.0.1',0)
    self._address = address
    
    try:
      self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
      self.set_reuse_addr()
      self.bind(address)
      self.listen(5)
      
      if address[1] == 0: # if bound to a random port, keep track
        self._address = self.getsockname()
    # port in use... Maybe already running.
    except socket.error as e:
      if e.errno == 48:
        raise AddrInUseError()
      raise e
  
  coin = property(lambda s: s._coin)
  data_dir = property(lambda s: s._data_dir)
  
  address = property(lambda s: s._address)
  ip = property(lambda s: s._address[0])
  port = property(lambda s: s._address[1])
  
  def serve_forever(self):
    try:
      asyncore.loop(5,map=self)
    except StopNode as e:
      pass
    finally:
      self.handle_close()
  
  def close(self):
    asyncore.dispatcher.close(self)
  
  def begin_loop(self):  # hand the start of event loop, will override in sub-class
    pass
  
  def handle_accept(self):
    pair = self.accept()
    if not pair: return
    
    (sock,address) = pair
    print('Incoming connection from %s' % repr(addr))
    
    ''' # we banned this address less than an hour ago
    if address in self._banned:
      if time.time() - self._banned[address] < 3600:
        sock.close()
        return
      del self._banned[address] '''
    
    # we are not accepting incoming connections; drop it
    if not self._listen:
      sock.close()
      return
    
    # asyncore keeps a reference to us in the map (ie. node = self)
    connection.Connection(node=self,sock=sock,address=address)
  
  def readable(self):
    return True
  
  # emulate a dictionary so we an pass in the Node as the asyncode map
  
  def items(self):  # map.items() will be called in asyncore loop
    self.begin_loop()
    
    ''' # how long since we called heartbeat?
    now = time.time()
    if now - self._last_heartbeat > 10:
      self._last_heartbeat = now;
      self.heartbeat() '''
    
    return self._peers.items()
  
  def values(self):
    return self._peers.values()
  
  def keys(self):
    return self._peers.keys()
  
  def get(self, name, default = None):
    return self._peers.get(name, default)
  
  def __nonzero__(self):
    return True
  
  def __len__(self):
    return len(self._peers)
  
  def __getitem__(self, name):
    return self._peers[name]
  
  def __setitem__(self, name, value):
    self._peers[name] = value
  
  def __delitem__(self, name):
    del self._peers[name]
  
  def __iter__(self):
    return iter(self._peers)
  
  def __contains__(self, name):
    return name in self._peers

# from nbc.node import raw
# node = raw.RawNode(address=('127.0.0.1',20303))
# node.serve_forever()
