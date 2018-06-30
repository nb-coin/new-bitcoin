
from random import randint

from .. import util
from ..util.ecdsa import SECP256k1 as curve
from ..util.ecdsa.util import string_to_number, number_to_string, randrange

import getpass
from binascii import hexlify, unhexlify
from ..util.pyaes.aes import AESModeOfOperationCBC as AES

def ORD(ch):   # compatible to python3
  return ch if type(ch) == int else ord(ch)

def _aesEncrypt(sText, passphrase):
  if not isinstance(passphrase,bytes):
    raise ValueError('passphrase should be bytes')
  passphrase = passphrase[:16].ljust(16,b'\x00')
  aes = AES(passphrase)
  
  m,n = divmod(len(sText),16)
  if n:
    sText = sText + b'\x00' * (16 - n)  # align to 16 * N
    m += 1
  
  sEncoded = b''; iFrom = 0
  for i in range(m):
    sEncoded += aes.encrypt(sText[iFrom:iFrom+16])
    iFrom += 16
  return sEncoded

def _aesDecrypt(sText, passphrase=''):
  m,n = divmod(len(sText),16)
  if m == 0 or m >= 16 or n != 0:  # encrypted text should be 16 * N
    raise ValueError('invalid encrypted text')
  
  while not passphrase:
    passphrase = getpass.getpass('Passphrase:').strip()
  if not isinstance(passphrase,bytes):
    passphrase = passphrase.encode('latin-1')
  passphrase = passphrase[:16].ljust(16,b'\x00')
  aes = AES(passphrase)
  
  sDecoded = b''; iFrom = 0
  for i in range(m):
    sDecoded += aes.decrypt(sText[iFrom:iFrom+16])
    iFrom += 16
  return sDecoded

def _keyFromPoint(point, compressed):
  'Converts a point into a key.'
  key = ( b'\x04' +
          number_to_string(point.x(),curve.order) +
          number_to_string(point.y(),curve.order) )
  if compressed:
    key = util.key.compress_public_key(key)
  return key

class Address(object):
  def __init__(self, pubKey=None, privKey=None, vcn=None, testnet=False):
    self._compressed = False
    self._privKey = privKey
    self._testnet = testnet
    
    if privKey:
      if pubKey is not None:
        raise ValueError('cannot specify public and private key both')
      assert(type(privKey) == bytes)
      
      # this is a compressed private key
      ch = ORD(privKey[0])
      if ch == 76 or ch == 75:  # 76 is 'L', 75 is 'K'
        self._compressed = True
      elif ch != 53:            # 53 is '5'
        raise ValueError('unknown private key type: %r' % privKey[0])
      
      secexp = string_to_number(util.key.privkey_from_wif(self._privKey))
      point = curve.generator * secexp
      pubKey = _keyFromPoint(point,False)
    else: self._privKey = None
    
    if pubKey:
      assert(type(pubKey) == bytes)
      
      ch = ORD(pubKey[0])
      if ch == 4:  # prefix with 0x04 means decompressed
        if len(pubKey) != 65:
          raise ValueError('invalid uncomprssed public key')
      elif ch == 2 or ch == 3:
        pubKey = util.key.decompress_public_key(pubKey)
        self._compressed = True
      else:
        raise ValueError('invalid public key')
      self._pubKey = pubKey
    else:
      raise ValueError('no address parameters')
    
    if vcn is None:
      self._vcn = randint(0,0xffff)
    else: self._vcn = int(vcn) & 0xFFFF
    
    # public address
    ver = b'\x6f' if self._testnet else b'\x00'
    self._address = util.key.publickey_to_address(self.publicKey(),self._vcn,version=ver)
  
  pubKey  = property(lambda s: s._pubKey)
  privKey = property(lambda s: s._privKey)
  vcn     = property(lambda s: s._vcn)
  address = property(lambda s: s._address)
  compressed = property(lambda s: s._compressed)
  testnet = property(lambda s: s._testnet)
  
  def publicKey(self):
    'The public key, compressed if the address is compressed.'
    if self._compressed:
      return util.key.compress_public_key(self._pubKey)
    return self._pubKey
  
  def _priv_key(self):
    'The binary representation of a private key.'
    if self._privKey is None:
      return None
    return util.key.privkey_from_wif(self.privKey)
  
  @staticmethod
  def generate(vcn=None, testnet=False, compressed=True): # suggest only using compressed address
    'Generate a new random address.'
    secexp = randrange(curve.order)
    key = number_to_string(secexp,curve.order)
    if compressed:
      key = key + b'\x01'
    return Address(privKey=util.key.privkey_to_wif(key),vcn=vcn,testnet=testnet)
  
  def decompress(self):
    'Returns the decompressed address.'
    if not self._compressed: return self
    
    if self._privKey:
      return Address(privKey=util.key.privkey_to_wif(self._priv_key()),vcn=self._vcn,testnet=self._testnet)
    if self._pubKey:
      return Address(pubKey=util.key.decompress_public_key(self._pubKey),vcn=self._vcn,testnet=self._testnet)
    raise ValueError('address cannot be decompressed')
  
  def compress(self):
    'Returns the compressed address.'
    if self._compressed: return self
    
    if self._privKey:
      return Address(privKey=util.key.privkey_to_wif(self._priv_key()+b'\x01'),vcn=self._vcn,testnet=self._testnet)
    if self.pubKey:
      return Address(pubKey=util.key.compress_public_key(self._pubKey),vcn=self._vcn,testnet=self._testnet)
    raise ValueError('address cannot be compressed')
  
  def sign(self, data):
    "Signs data with this address' private key."
    
    if self._privKey is None: raise ValueError('invalid private key')
    pk = util.key.privkey_from_wif(self._privKey)
    return util.ecc.sign(data,pk)
  
  def verify(self, data, signature):
    "Verifies the data and signature with this address' public key."
    
    if self._pubKey is None: raise ValueError('invalid public key')
    return util.ecc.verify(data,self._pubKey,signature)
  
  def __str__(self):
    privateKey = 'None'
    if self._privKey: privateKey = '**redacted**'
    return '<Address address=%s private=%s>' % (self._address,privateKey)
  
  def dump_to_cfg(self, passphrase=''):
    cfg = { 'encrypted': False, 'type': 'default',
      'vcn': self._vcn,
      'testnet': self._testnet,
      'prvkey': None, 'pubkey': None,
    }
    
    privKey = self._privKey; pubKey = self._pubKey
    if privKey:
      assert(len(privKey) <= 255)
      privKey = (b'%02x' % len(privKey)) + privKey
      
      if passphrase:
        privKey = _aesEncrypt(privKey,passphrase)
        cfg['encrypted'] = True
      
      cfg['prvkey'] = hexlify(privKey).decode('latin-1')
    elif pubKey:
      cfg['pubkey'] = hexlify(pubKey).decode('latin-1')
    return cfg
  
  @classmethod
  def load_from_cfg(klass, cfg, passphrase=''):
    pubKey = cfg['pubkey']; prvKey = cfg['prvkey']
    if prvKey:
      prvKey = unhexlify(prvKey)
      if cfg.get('encrypted'):
        prvKey = _aesDecrypt(prvKey,passphrase)
      
      try:
        orgLen = int(prvKey[:2],16); nowLen = len(prvKey)
        if nowLen < 2 + orgLen or nowLen > orgLen + 17:   # 17 is 2 + padding(15)
          raise ValueError('out of range')
        prvKey = prvKey[2:2+orgLen]  # first 2 bytes is original length
      except:
        raise ValueError('invalid private key')
    elif pubKey:
      pubKey = unhexlify(pubKey)
    return klass(pubKey=pubKey, privKey=prvKey, vcn=cfg['vcn'], testnet=cfg['testnet'])
