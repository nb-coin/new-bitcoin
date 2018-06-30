# The MIT License (MIT)
#
# Copyright (c) 2014 Richard Moore
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.


from . import base58

from .ecdsa.ecdsa import point_is_valid
from .ecdsa import SECP256k1 as curve
from .ecdsa.numbertheory import square_root_mod_prime
from .ecdsa.util import number_to_string, string_to_number

import hashlib

__all__ = [
    'compress_public_key', 'decompress_public_key',
    'privkey_to_wif', 'privkey_from_wif',
    'publickey_to_address'
]

def CHR(i):    # compatible to python3
  return bytes(bytearray((i,)))

def ORD(ch):   # compatible to python3
  return ch if type(ch) == int else ord(ch)

def compress_public_key(public_key):
    if ORD(public_key[0]) != 4 or len(public_key) != 65:    # public_key[0] != '\x04'
        raise ValueError('invalid uncompressed public key')
    y_parity = string_to_number(public_key[33:65])
    return CHR(0x02 + (y_parity & 0x01)) + public_key[1:33]

_a = curve.curve.a()
_b = curve.curve.b()
_p = curve.curve.p()
_n = curve.order

def decompress_public_key(public_key):
    ch = ORD(public_key[0])
    if ch == 4 and len(public_key) == 65:
        x = string_to_number(public_key[1:33])
        y = string_to_number(public_key[33:65])
        if not point_is_valid(curve.generator, x, y):
            raise ValueError('invalid public key')
        return public_key

    if (ch != 2 and ch != 3) or len(public_key) != 33:
        raise ValueError('invalid compressed public key')

    x = string_to_number(public_key[1:])
    y = square_root_mod_prime((x ** 3 + _a * x + _b) % _p, _p)
    if not point_is_valid(curve.generator, x, y):
        raise ValueError('invalid public key')

    if (ch & 0x01) != (y & 0x01):
        y = _p - y

    return b'\x04' + public_key[1:] + number_to_string(y, _n)


# See: https://en.bitcoin.it/wiki/Wallet_import_format
def privkey_to_wif(privkey, prefix = b'\x80'):
    return base58.encode_check(prefix + privkey)

# See: https://en.bitcoin.it/wiki/Wallet_import_format
def privkey_from_wif(privkey, prefix = b'\x80'):
    key = base58.decode_check(privkey)
    if ORD(prefix) != ORD(key[0]):
        raise ValueError('wif private key has does not match prefix')
    if len(key) == 33:
        ch = ORD(privkey[0])
        if ch != 53:  # 53 is '5'
            raise ValueError('uncompressed wif private key does not begin with 5')
        return key[1:]
    elif len(key) == 34:
        if ORD(key[-1]) != 1:  # not 0x01
            raise ValueError('compressed wif private key missing compression bit')
        ch = ORD(privkey[0])
        if ch != 76 and ch != 75:  # 76 is 'L', 75 is 'K'
            raise ValueError('uncompressed wif private key does not begin with 5')
        return key[1:-1]
    raise ValueError('invalid wif private key')

def pubkeyhash_to_address(publickey_hash, vcn, version = b'\x00'):
    # return base58.encode_check(version + publickey_hash)
    return base58.encode_check(version + (b'%04x' % (vcn & 0xFFFF)) + publickey_hash)

# See: https://en.bitcoin.it/wiki/Technical_background_of_Bitcoin_addresses
def publickey_to_address(publickey, vcn, version = b'\x00'):
    # return pubkeyhash_to_address(hash160(publickey),version)
    pubHash = hashlib.sha512(publickey).digest()
    s1 = hashlib.new('ripemd160',pubHash[:32]).digest()
    s2 = hashlib.new('ripemd160',pubHash[32:]).digest()
    return pubkeyhash_to_address(hashlib.sha256(s1+s2).digest(),vcn,version)

