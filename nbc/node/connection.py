
import asyncore
import os
import socket
import sys
import time
import traceback

from .. import util
from .. import protocol

BLOCK_SIZE = 8192             # one receive block size

_SECONDS_OF_30M  = 30 * 60    #  30 Minutes * 60
_SECONDS_OF_5M   = 5 * 60     #   5 Minutes * 60
_SECONDS_OF_180M = 180 * 60   # 180 Minutes * 60

class Connection(asyncore.dispatcher):
  'Handles buffering input and output into messages and call command_xxx'
  
  SERVICES = protocol.SERVICE_NODE_NETWORK
  
  def __init__(self, node, address, sock=None):
    self._node = node
    self._send_buffer = b''   # send buffer
    self._recv_buffer = b''   # receive buffer
    self._tx_bytes = 0
    self._rx_bytes = 0
    
    self._last_tx_time = 0
    self._last_ping_time = 0
    self._last_rx_time = 0
    
    # remote node details
    self._address = address
    self._external_ip = None
    self._services = None
    self._start_height = None
    self._user_agent = None
    self._version = None
    self._relay = None
    
    self._banscore = 0
    self._verack = False # get version acknowledgement or not
    
    if sock:  # sock come from listen-accept
      asyncore.dispatcher.__init__(self,sock=sock,map=node) # map: a dictionary whose items are the channels to watch
      self._incoming = True
    else:     # we using an address to connect to
      asyncore.dispatcher.__init__(self,map=node)
      
      try:
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connect(address)
      except Exception as e:
        self.handle_close()
        raise e
      self._incoming = False
    
    # bootstrap communication with the node by broadcasting ver
    now = time.time()
    message = protocol.Version( version = node.coin.protocol_version,
                services = self.SERVICES,
                timestamp = now,
                addr_recv = protocol.NetworkAddress(now,self.SERVICES,address[0],address[1]),
                addr_from = protocol.NetworkAddress(now,self.SERVICES,node.external_ip,node.port),
                nonce = os.urandom(8),
                user_agent = node.user_agent,
                start_height = node.blockchain_height,
                relay = False )
    self.send_message(message)
  
  # remote node details
  address = property(lambda s: s._address)
  ip = property(lambda s: s._address[0])
  port = property(lambda s: s._address[1])
  
  incoming = property(lambda s: s._incoming)
  
  services = property(lambda s: s._services)
  start_height = property(lambda s: s._start_height)
  user_agent = property(lambda s: s._user_agent)
  version = property(lambda s: s._version)
  relay = property(lambda s: s._relay)
  external_ip = property(lambda s: s._external_ip)
  
  # connection details
  verack = property(lambda s: s._verack)
  rx_bytes = property(lambda s: s._rx_bytes)
  tx_bytes = property(lambda s: s._tx_bytes)
  
  node = property(lambda s: s._node)
  banscore = property(lambda s: s._banscore)
  
  # last time we heard from remote
  timestamp = property(lambda s: (time.time() - s._last_rx_time))
  
  def add_banscore(self, penalty=1):
    self._banscore += penalty
  
  def reduce_banscore(self, penalty=1):
    i = self._banscore - penalty
    self._banscore = 0 if i < 0 else i
  
  def readable(self):
    now = time.time()
    rx_ago = now - self._last_rx_time
    tx_ago = now - self._last_tx_time
    ping_ago = now - self._last_ping_time
    
    # haven't sent anything for 30 minutes, send a ping every 5 minutes
    if self._last_tx_time and tx_ago > _SECONDS_OF_30M and ping_ago > _SECONDS_OF_5M:
      self.send_message(protocol.Ping(os.urandom(8)))
      self._last_ping_time = time.time()
    
    # it's been over 3 hours, just disconnect
    if self._last_rx_time and rx_ago > _SECONDS_OF_180M:
      self.handle_close()
      return False
    return True
  
  def handle_read(self):
    try:
      chunk = self.recv(BLOCK_SIZE)
    except Exception as e:
      chunk = ''
    
    if not chunk:  # remote connection closed
      self.handle_close()
      return
    
    self._recv_buffer += chunk
    self._rx_bytes += len(chunk)
    self.node._rx_bytes += len(chunk)
    self._last_rx_time = time.time()
    
    # process as many messages
    while True:
      length = protocol.Message.first_msg_len(self._recv_buffer)
      if length is None or length > len(self._recv_buffer):
        break  # not enough bytes for next message
      
      # parse the message and handle it
      payload = self._recv_buffer[:length]
      self._recv_buffer = self._recv_buffer[length:]  # remove one message
      try:
        message = protocol.Message.parse(payload,self.node.coin.magic)
        self.handle_message(message)
      except protocol.UnknownMsgError as e:
        self.node.invalid_command(self,payload,e)
      except protocol.MsgFormatError as e:
        self.node.invalid_command(self,payload,e)
      except Exception as e:  # just print error, avoid stopping
        self.node.log(traceback.format_exc(),peer=self,level=self.node.LOG_LEVEL_ERROR)
  
  def writable(self):
    return len(self._send_buffer) > 0
  
  def handle_write(self):
    try:
      sent = self.send(self._send_buffer)
      self._tx_bytes += sent
      self.node._tx_bytes += sent
      self._last_tx_time = time.time()
    except Exception as e:
      self.handle_close()
      return
    self._send_buffer = self._send_buffer[sent:]
  
  def handle_error(self):
    t,v,tb = sys.exc_info()
    if t == socket.error:
      self.node.log('--- connection refused',peer=self,level=self.node.LOG_LEVEL_INFO)
    else:
      self.node.log(traceback.format_exc(),peer=self,level=self.node.LOG_LEVEL_ERROR)
    del tb
    self.handle_close()
  
  def handle_close(self):
    try:
      self.close()
    except Exception as e:
      pass
    self.node.disconnected(self)
  
  def handle_message(self, message):
    logLevel = self.node.log_level
    if logLevel <= self.node.LOG_LEVEL_PROTOCOL:
      self.node.log('<<< ' + str(message), peer=self, level=logLevel)
    elif logLevel <= self.node.LOG_LEVEL_DEBUG:
      self.node.log('<<< ' + message._debug(), peer=self, level=logLevel)
    
    kwargs = dict((k,getattr(message,k)) for (k,t) in message.properties)
    if message.command == protocol.Version.command:
      self._services = message.services
      self._start_height = message.start_height
      self._user_agent = message.user_agent
      self._version = message.version
      self._relay = message.relay
      self._external_ip = message.addr_recv.address
      
      self.node.connected(self)
    elif message.command == protocol.VersionAck.command:
      self._verack = True
    
    if message:
      method = getattr(self.node,'command_'+message.name,None)
      if method:
        method(self,**kwargs)
      else:
        self.node.log('error: method not defined: command_%s' % message.name, peer=self, level=self.node.log_level)
  
  def send_message(self, message):
    logLevel = self.node.log_level
    if logLevel <= self.node.LOG_LEVEL_PROTOCOL:
      self.node.log('>>> ' + str(message), peer=self, level=logLevel)
    elif logLevel <= self.node.LOG_LEVEL_DEBUG:
      self.node.log('>>> ' + message._debug(), peer=self, level=logLevel)
    
    self._send_buffer += message.binary(self.node.coin.magic)
  
  def __hash__(self):
    return hash(self.address)

  def __eq__(self, other):
    return self == other
  
  def __str__(self):
    return '<Connection(%s) %s:%d>' % (self._fileno,self.ip,self.port)
