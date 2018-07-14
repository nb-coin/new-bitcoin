
import sys, time, asyncore, socket, random
from threading import Event, Thread

from six import print_

from .. import util
from .. import coins
from .. import protocol
from . import connection
from ..node import AddrInUseError, StopNode, add_portmap, remove_portmap

try:
  range = xrange
except NameError as err:  # range same to xrange in python3
  pass

VERSION = [0,0,1]

MAX_ADDRESSES = 2500      # maximum number of address stored in memory
ADDRESSES_PER_ASK = 1000  # maximun number of address returned when ask by peer

MAX_RELAY_COUNT = 100     # maximum recent messages a peer can ask to be relayed
RELAY_COUNT_DECAY = 10    # how many messages per second we forget from each peer

class BaseNode(asyncore.dispatcher, object):
  LOG_LEVEL_PROTOCOL = 0
  LOG_LEVEL_DEBUG    = 1
  LOG_LEVEL_INFO     = 2
  LOG_LEVEL_ERROR    = 3
  LOG_LEVEL_FATAL    = 4
  
  def __init__(self, data_dir=None, address=None, seek_peers=16, max_peers=125, bootstrap=True, log=sys.stdout, coin=coins.Newbitcoin):
    asyncore.dispatcher.__init__(self,map=self)
    self._coin = coin
    
    if data_dir is None:
      data_dir = util.default_data_directory()
    self._data_dir = data_dir
    
    self._peers = dict()
    self._addresses = dict() # map of (address,port) to (timestamp,service)
    
    self._seek_peers = seek_peers
    self._max_peers = max_peers
    self._bootstrap = bootstrap
    self._log = log
    self._log_level = self.LOG_LEVEL_ERROR
    
    self._bootstrap = None
    if bootstrap:
      self._bootstrap = coin.dns_seeds[:]  # copy dns seeds
    
    self._banned = dict()
    self._user_agent = '/nbc:%s(%s)/' % ('.'.join(str(i) for i in VERSION),coin.name)
    self._last_heartbeat = 0
    
    self._tx_bytes = 0    # total send bytes
    self._rx_bytes = 0    # total receive bytes
    
    self._listen = True
    if address is None:
      self._listen = False
      address = ('127.0.0.1',0)
    self._address = address
    
    self._guessed_external_ip = address[0]
    self._external_ip = None
    self._upnp = None
    
    # relay_count maps peer to number of messages sent recently so we can throttle peers when too chatty
    self._relay_count = dict()
    self._last_relay_decay = time.time()
    
    try:
      self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
      self.set_reuse_addr()
      self.bind(address)
      self.listen(5)
      
      if address[1] == 0: # if bound to a random port, keep track
        self._address = self.getsockname()
    except socket.error as e:  # port in use... Maybe already running
      if e.errno == 48:
        raise AddrInUseError()
      raise e
  
  coin = property(lambda s: s._coin)
  data_dir = property(lambda s: s._data_dir)
  
  # blockchain height will include when connecting to a peer, sub-class should override it
  blockchain_height = 0
  
  address = property(lambda s: s._address)
  ip = property(lambda s: s._address[0])
  port = property(lambda s: s._address[1])
  
  def _get_external_ip(self):
    if self._external_ip:
      return self._external_ip
    return self._guessed_external_ip
  def _set_external_ip(self,address):
    self._external_ip = address
  external_ip = property(_get_external_ip,_set_external_ip)
  
  def _get_user_agent(self):
    return self._user_agent
  def _set_user_agent(self, user_agent):
    self._user_agent = user_agent
  user_agent = property(_get_user_agent,_set_user_agent)
  
  def _get_log_level(self):
    return self._log_level
  def _set_log_level(self, log_level):
    self._log_level = log_level
  log_level = property(_get_log_level,_set_log_level)
  
  def log(self, message, peer=None, level=LOG_LEVEL_INFO):
    if self._log is None or level < self._log_level: return
    
    if peer:
      source = peer.address[0]
    else: source = 'node'
    message = '(%s) %s' % (source, message)
    print_(message,file=self._log)
  
  def serve_forever(self):
    if self._listen:
      self._upnp = add_portmap(self.port,'TCP','Newbitcoin Peer manager')
    
    try:
      asyncore.loop(5,map=self)
    except StopNode as e:
      pass
    finally:
      self.handle_close()
      
      if self._listen:
        remove_portmap(self.port,'TCP')
  
  def close(self):
    asyncore.dispatcher.close(self)
  
  def invalid_command(self, peer, payload, exception):
    self.log('invalid command: %r (%s)' % (payload,exception))
  
  def connected(self, peer):    # called by a peer once know version
    self._check_external_ip()
  
  def disconnected(self, peer): # called by a peer after closed
    if peer.address in self._addresses:
      del self._addresses[peer.address]
  
  def add_peer(self, address, force=True):  # if already have max_peers and not force, ignore adding
    if not force and len(self._peers) >= self._max_peers:
      return False  # too much peers
    if address in [n.address for n in self.values()]:
      return False  # already exists this peer
    
    try:            # asyncore keeps a reference in the map
      connection.Connection(address=address,node=self)
    except Exception as e:
      print('meet error: %s' % e)
      return False  # will remove self._addresses[address] in self.disconnected()
    return True
  
  def remove_peer(self, address):
    peers = self.peers
    for peer in peers:
      if peer.address == address:
        peer.handle_close()
        break
  
  @property
  def peers(self):
    return [n for n in self.values() if isinstance(n,connection.Connection)]
  
  #----------------
  
  def punish_peer(self, peer, reason=None):
    peer.add_banscore()
    if peer.banscore > 5:
      self._banned[peer.ip] = time.time()
      peer.handle_close()
  
  def _check_external_ip(self):  # We rely on the peers to tell our IP, take the majority answer even if exists dishonest peer
    counter = dict()
    peers = self.peers
    for peer in peers:
      address = peer.external_ip
      if address is None: continue
      if address not in counter: counter[address] = 0
      counter[address] += 1
    if counter:
      counter = [(counter[a],a) for a in counter]
      counter.sort()
      self._guessed_external_ip = counter[-1][1]
  
  def add_any_peer(self):
    if not self._addresses or random.randint(0,199) == 1: # if no address, or for sometimes (random 1/200) use dns seeds
      if self._bootstrap:  # at least has one item
        addr = self._bootstrap[random.randint(0,len(self._bootstrap)-1)]  # addr should be RAW node
        self.add_peer(addr,False)        # connection of RAW would be more using than normal
      # else, router node should not using self._bootstrap
    else:
      peers = self.peers
      actives = [n.address for n in peers]
      for address in self._addresses:
        if address in actives: continue  # ignore already connected one
        self.add_peer(address)           # try add one peer
        break
  
  def _decay_relay(self):  # aging policy for throttling relaying
    return
    
    dt = time.time() - self._last_relay_decay
    for peer in list(self._relay_count):
      count = self._relay_count[peer]
      count -= dt * RELAY_COUNT_DECAY
      if count <= 0.0:
        del self._relay_count[peer]
      else:
        self._relay_cound[peer] = count
    
    self._last_relay_decay = time.time()
  
  def heartbeat(self):     # called every 10 seconds to do maintenance
    peers = self.peers
    
    # if need more peer connections, attempt to add some
    for i in range(0,min(self._seek_peers-len(peers),5)): # max 5 at a time
      self.add_any_peer()
    
    # if not many addresses, try ask more
    if peers and len(self._addresses) < 50:
      peer = random.choice(peers)
      peer.send_message(protocol.GetAddress())
    
    for peer in peers:    # give a little back to peers that went bad but seem be OK now
      peer.reduce_banscore()
    
    self._decay_relay()   # give a little more room for relaying
  
  #----------------
  
  def begin_loop(self):   # hand the start of event loop, will override in sub-class
    pass
  
  def handle_accept(self):
    pair = self.accept()
    if not pair: return
    
    (sock,address) = pair
    print('Incoming connection from %s' % repr(address))
    
    if address in self._banned:
      if time.time() - self._banned[address] < 3600:
        sock.close()            # banned it within one hour
        return
      del self._banned[address] # else, ignore early banned list
    
    if not self._listen: # if not accepting incoming, drop it
      sock.close()
      return
    
    connection.Connection(node=self,sock=sock,address=address) # asyncore will keep a reference in map for us
  
  def readable(self):
    return True
  
  # emulate a dictionary so we an pass in the Node as the asyncode map
  
  def items(self):  # map.items() will be called in asyncore loop
    self.begin_loop()
    
    now = time.time()
    if now - self._last_heartbeat > 10: # more than 10 seconds since last heartbeat
      self._last_heartbeat = now;
      self.heartbeat()
    
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
  
  #------ command_xxx ----
  
  def command_ping(self, peer, nonce):
    peer.send_message(protocol.Pong(nonce))
  
  def command_pong(self, peer, nonce):
    pass
  
  def command_version(self, peer, version, services, timestamp, addr_recv, addr_from, nonce, user_agent, start_height, relay):
    peer.send_message(protocol.VersionAck())
  
  def command_version_ack(self, peer): # a peer acknowledged us, record address
    if len(self._addresses) < MAX_ADDRESSES:
      self._addresses[peer.address] = (peer.timestamp, peer.services)
  
  def command_get_address(self, peer):
    def sortAddr(a,b):
      return cmp(self._addresses[b][0],self._addresses[a][0]) # by timestamp and with decrease
    
    addresses = []
    for address in sorted(self._addresses,sortAddr):  # add the most recent peers
      (timestamp, services) = self._addresses[address]
      if services is None: continue
      
      (ip, port) = address
      addresses.append(protocol.NetworkAddress(timestamp,services,ip,port))
      if len(addresses) >= ADDRESSES_PER_ASK: break
    
    peer.send_message(protocol.Address(addresses)) # send our address list to peer
  
  def command_address(self, peer, addr_list):
    for address in addr_list:
      if len(self._addresses) > MAX_ADDRESSES: return
      self._addresses[(address.address,address.port)] = (address.timestamp,address.services)

def startServer(node):
  ts = Thread(target=node.serve_forever)
  ts.setDaemon(True)
  ts.start()
  time.sleep(2.5)  # waiting server thread started that will prepare upnp NAT

# from nbc.node import basenode
# node = basenode.BaseNode(address=('127.0.0.1',30303))
# node.log_level = node.LOG_LEVEL_DEBUG
# basenode.startServer(node)
#
# node.close()
