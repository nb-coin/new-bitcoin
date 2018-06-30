
import hashlib
import os
import struct
from binascii import hexlify

from .. import util
from . import format

__all__ = ['MsgFormatError', 'Message', 'UnknownMsgError',

           'Address', 'Alert', 'Block', 'GetAddress', 'GetBlocks', 'GetData',
           'GetHeaders', 'Headers', 'Inventory', 'MemoryPool', 'NotFound',
           'Ping', 'Pong', 'Reject', 'Transaction', 'Version', 'VersionAck']

def _debug(obj, params):
  message = ['<%s' % obj.__class__.__name__]
  for (k, v) in params:
    if isinstance(v,(list,tuple)):
      message.append(('len(%s)=%d' % (k,len(v))))
      if len(v):
        k = '%s[0]' % k
        v = v[0]
    
    if v:
      if isinstance(v,format.NetworkAddress):
        text = '%s:%d' % (v.address, v.port)
      elif isinstance(v,format.InventoryVector):
        obj_type = 'unknown'
        if v.object_type <= 2:
          obj_type = ['error', 'tx', 'block'][v.object_type]
        text = '%s:%s' % (obj_type, hexlify(v.hash))
      elif isinstance(v,format.Txn):
        text = hexlify(v.hash)
      elif isinstance(v,format.BlockHeader):
        text = hexlify(v.hash)
      else:
        text = str(v)
      message.append(('%s=%s' % (k,text)))
  
  return ' '.join(message) + '>'

class UnknownMsgError(Exception): pass  # when command not registed
class MsgFormatError(Exception): pass   # invalid message header

class Message(format.CompoundType):
  '''A message object. This base class is responsible for serializing and
     deserializing binary network payloads.

     Each message sub-class should specify an array of (name, FormatType)
     tuples named properties. See below for examples.

     Message subclasses will automatically be registered, unless they set
     not_regist = True.

     Messages are rigorously type checked for the properties that are given
     to ensure the bytes over the wire will be what was expected.'''
  
  command = None
  not_regist = False
  properties = []
  
  _magic = None  # only parsed messages will have a magic number
  magic = property(lambda s: s._magic)
  
  def binary(self, magic):
    payload = format.CompoundType.binary(self)
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    command = self.command.encode('latin-1')
    command = command + (b'\x00' * (12 - len(command)))  # pad to 12 bytes
    return magic + command + struct.pack('<I',len(payload)) + checksum + payload
  
  MessageTypes = dict()
  
  @staticmethod
  def register(msg_type):
    Message.MessageTypes[msg_type.command] = msg_type
  
  @staticmethod
  def first_msg_len(data):
    if len(data) < 20:  # not enough to determine payload size yet
      return None
    return struct.unpack('<I', data[16:20])[0] + 24
  
  @classmethod
  def parse(cls, data, magic):
    if data[0:4] != magic:  # check magic
      raise MsgFormatError('bad magic number')
    
    # get binary payload
    (length, ) = struct.unpack('<I', data[16:20])
    payload = data[24:24 + length]
    
    # check the checksum
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    if data[20:24] != checksum:
      raise MsgFormatError('bad checksum')
    
    # get the correct class for this message's command
    command = data[4:16].strip(b'\x00').decode('latin-1')
    msg_type = cls.MessageTypes.get(command)
    if msg_type is None:
      raise UnknownMsgError('command: %r (%r)' % (command, data))
    
    # parse the properties using the correct class's parse
    (vl, message) = super(Message,msg_type).parse(payload)
    message._magic = magic
    return message
  
  @property
  def name(self):  # should overridden in sub-class, it determines which command_* will be called
    return self.command
  
  def _debug(self):
    return _debug(self,[])

class Version(Message):
  command = 'version'
  
  properties = [
    ('version', format.FtNumber('i')),
    ('services', format.FtNumber('Q')),
    ('timestamp', format.FtNumber('q',allow_float=True)),
    ('addr_recv', format.FtNetworkAddressNoTimestamp()),
    ('addr_from', format.FtNetworkAddressNoTimestamp()),
    ('nonce', format.FtBytes(8)),
    ('user_agent', format.FtVarString()),
    ('start_height', format.FtNumber('i')),
    ('relay', format.FtOptional(format.FtNumber('B'), True)),
  ]
  
  def _debug(self):
    return _debug(self,[
      ('v', self.version), ('s', self.services),
      ('ua', self.user_agent), ('sh', self.start_height),
    ])

class VersionAck(Message):
  command = 'verack'
  name = 'version_ack'

class Address(Message):
  command = 'addr'
  name = 'address'
  
  properties = [
    ('addr_list',format.FtArray(format.FtNetworkAddress(),max_length=1000)),
  ]
  
  def _debug(self):
    return _debug(self, [('a', self.addr_list)])

class Inventory(Message):
  command = 'inv'
  name = 'inventory'
  
  properties = [
    ('inventory', format.FtArray(format.FtInventoryVector(), max_length = 50000)),
  ]
  
  def _debug(self):
    return _debug(self, [('i', self.inventory)])

class GetData(Inventory):
  command = 'getdata'
  name = 'get_data'

class NotFound(Inventory):
  command = 'notfound'
  name = 'not_found'

class GetBlocks(Message):
  command = 'getblocks'
  name = 'get_blocks'
  
  properties = [
    ('version', format.FtNumber('I')),
    ('block_locator_hashes', format.FtArray(format.FtBytes(32), 1)),
    ('hash_stop', format.FtBytes(32)),
  ]
  
  def _debug(self):
    return _debug(self, [('blh', [hexlify(h) for h in self.block_locator_hashes])])

class GetHeaders(GetBlocks):
  command = 'getheaders'
  name = 'get_headers'

class Transaction(Message):
  command = 'tx'
  name = 'transaction'
  
  properties = [
    ('version', format.FtNumber('I')),
    ('tx_in', format.FtArray(format.FtTxnIn(), 1)),
    ('tx_out', format.FtArray(format.FtTxnOut(), 1)),
    ('lock_time', format.FtNumber('I')),
  ]
  
  def _debug(self):
    return _debug(self, [('in', self.tx_in), ('out', self.tx_out)])

class Block(Message):
  command = "block"
  
  properties = [
    ('version', format.FtNumber('I')),
    ('prev_block', format.FtBytes(32)),
    ('merkle_root', format.FtBytes(32)),
    ('timestamp', format.FtNumber('I', allow_float = True)),
    ('bits', format.FtNumber('I')),
    ('nonce', format.FtNumber('I')),
    ('txns', format.FtArray(format.FtTxn())),
  ]

  @staticmethod
  def from_block(block):
    return Block(block.version, block.previous_hash,  ## block.previous_block_hash,
                 block.merkle_root, block.timestamp, block.bits,
                 block.nonce, block.transactions)
  
  def _debug(self):
    block_hash = util.get_block_header(self.version, self.prev_block,
      self.merkle_root, self.timestamp, self.bits, self.nonce)
    return _debug(self, [('h', hexlify(block_hash)), ('t', self.txns)])

class Headers(Message):
  command = 'headers'
  
  properties = [
    ('headers', format.FtArray(format.FtBlockHeader())),
  ]

  def _debug(self):
    return _debug(self, [('h', self.headers)])

class GetAddress(VersionAck):
  command = 'getaddr'
  name = 'get_address'

class MemoryPool(VersionAck):
  command = 'mempool'
  name = 'memory_pool'

class Ping(Message):
  command = 'ping'
  
  properties = [
    ('nonce', format.FtBytes(8)),
  ]
  
  def _debug(self):
    return _debug(self, [('n', hexlify(self.nonce))])

class Pong(Ping):
  command = 'pong'

class Reject(Message):
  command = 'reject'
  
  properties = [
    ('message', format.FtVarString()),
    ('ccode', format.FtNumber('B')),
    ('reason', format.FtVarString()),
  ]
  
  def _debug(self):
    return _debug(self, [('m', self.message), ('r', self.reason)])

class FilterLoad(Message):
  command = 'filterload'
  name = 'filter_load'
  
  not_regist = True
  
  properties = [
    ('filter', format.FtArray(format.FtNumber('B'))),
    ('n_hashes_func', format.FtNumber('I')),
    ('n_tweak', format.FtNumber('I')),
    ('n_flags', format.FtNumber('B')),
  ]

class FilterLoad(Message):
  command = 'filteradd'
  name = "filter_add"
  
  not_regist = True
  
  properties = [
    ('data', format.FtVarString()),
  ]

class FilterClear(VersionAck):
  command = 'filterclear'
  name = 'filter_clear'
  
  not_regist = True

class MerkleBlock(Message):
  command = 'merkleblock'
  name = 'merkle_block'
  
  not_regist = True

  properties = [
    ('version', format.FtNumber('I')),
    ('prev_block', format.FtBytes(32)),
    ('merkle_root', format.FtBytes(32)),
    ('timestamp', format.FtNumber('I', allow_float = True)),
    ('bits', format.FtNumber('I')),
    ('nonce', format.FtNumber('I')),
    ('total_transactions', format.FtNumber('I')),
    ('hashes', format.FtArray(format.FtBytes(32))),
    ('flags', format.FtArray(format.FtNumber('b'))),
  ]

class Alert(Message):
  command = 'alert'
  
  properties = [
    ('payload', format.FtVarString()),
    ('signature', format.FtVarString())
  ]
  
  payload_properties = [
    'version', 'relay_until', 'expiration', 'id', 'cancel', 'set_cancel',
    'min_ver', 'max_ver', 'set_sub_ver', 'priority', 'comment',
    'status_bar', 'reserved'
  ]

  # Alert is a special... The binary packed format contains additional info
  # See: https://en.bitcoin.it/wiki/Protocol_specification#alert
  version = property(lambda s: s._parse_and_get('version'))
  relay_until = property(lambda s: s._parse_and_get('relay_until'))
  expiration = property(lambda s: s._parse_and_get('expiration'))
  id = property(lambda s: s._parse_and_get('id'))
  cancel = property(lambda s: s._parse_and_get('cancel'))
  set_cancel = property(lambda s: s._parse_and_get('set_cancel'))
  min_ver = property(lambda s: s._parse_and_get('min_ver'))
  max_ver = property(lambda s: s._parse_and_get('max_ver'))
  set_sub_ver = property(lambda s: s._parse_and_get('set_sub_ver'))
  priority = property(lambda s: s._parse_and_get('priority'))
  comment = property(lambda s: s._parse_and_get('comment'))
  status_bar = property(lambda s: s._parse_and_get('status_bar'))
  reserved = property(lambda s: s._parse_and_get('reserved'))

  # The above properties will use this method to extract and cache everything
  def _parse_and_get(self, name):
    if not hasattr(self, '_data'):
      self._data = dict()
    
    if not self._data:
      data = self.payload
      
      self._data = dict()
      
      offset = 0
      
      # extract version, relay_until, expiration, id and cancel
      (v, r, e, i, c) = struct.unpack('<iqqii', data[offset:offset + 28])
      self._data['version'] = v
      self._data['relay_until'] = r
      self._data['expiration'] = e
      self._data['id'] = i
      self._data['cancel'] = c
      offset += 28
      
      # extract the set of alerts this alert cancels
      (vl, s) = format.parse_var_set(data[offset:], format.FtNumber('i'))
      self._data['set_cancel'] = s
      offset += vl
      
      # extract minimum and maximum versions affecte by this alert
      (minver, maxver) = struct.unpack('<ii', data[offset:offset + 8])
      self._data['min_ver'] = minver
      self._data['max_ver'] = maxver
      offset += 8
      
      # extract the set of sub-versions affected by this alert
      (vl, s) = format.parse_var_set(data[offset:], format.FtVarString())
      self._data['set_sub_ver'] = s
      offset += vl
      
      # extract priority
      (p, ) = struct.unpack('<i', data[offset:offset + 4])
      self._data['priority'] = p
      offset += 4
      
      # extract comment (no need to display)
      (vl, c) = format.FtVarString.parse(data[offset:])
      self._data['comment'] = c
      offset += vl
      
      # extract status bar message (should be shown in the UI)
      (vl, s) = format.FtVarString.parse(data[offset:])
      self._data['status_bar'] = s
      offset += vl
      
      # just incase *this* is an old version and the new format includes
      # extra stuff, we can still view it
      (vl, r) = format.FtVarString.parse(data[offset:])
      self._data['reserved'] = r
      offset += vl
      
    return self._data[name]
  
  def verify(self, public_key):
    return util.ecc.verify(self.payload, public_key, self.signature)
  
  def __str__(self):
    return '<message.Alert version=%d relay_until=%d expiration=%d id=%d cancel=%d cancel_set=[%s] min_ver=%d maxver=%d set_sub_ver=[%s] priority=%s comment=%r status_bar=%r reserverd=%r>' % (self.version, self.relay_until, self.expiration, self.id, self.cancel, ", ".join(str(i) for i in self.set_cancel), self.min_ver, self.max_ver, ", ".join(self.set_sub_ver), self.priority, self.comment, self.status_bar, self.reserved)
  
  def _debug(self):
    return _debug(self, [('s', self.status_bar)])
