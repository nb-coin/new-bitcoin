
from .. import util
from . import coin

__all__ = ['Newbitcoin']

import codecs
_decodeHex = codecs.getdecoder("hex_codec")

def decodeHex(s):  # avoid using 'ff'.decode('hex') that not supported in python3
  return _decodeHex(s)[0]

class Newbitcoin(coin.Coin):

    name = "newbitcoin"

    # All symbols the coin uses and "primary" symbol
    symbols = ['NBC']
    symbol = symbols[0]

    # See: https://en.bitcoin.it/wiki/Satoshi_Client_Node_Discovery
    #      https://github.com/bitcoin/bitcoin/blob/master/src/chainparams.cpp#L143
    dns_seeds = [ ("127.0.0.1",20303),
#        ("seed.bitcoin.sipa.be", 8333),
#        ("dnsseed.bluematt.me", 8333),
#        ("dnsseed.bitcoin.dashjr.org", 8333),
#        ("seed.bitcoinstats.com", 8333),
#        ("seed.bitnodes.io", 8333),
#        ("bitseed.xf2.org", 8333),
    ]

    port = 8333
    rpc_port = 8332

    genesis_version = 1
    genesis_block_hash = decodeHex(b'6fe28c0ab6f1b372c1a6a246ae63f74f931e8365e15a089c68d6190000000000')
    genesis_merkle_root = decodeHex(b'3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a')
    genesis_timestamp = 1231006505
    genesis_bits = 486604799
    genesis_nonce = 2083236893

    magic = b'\xf9\x6e\x62\x63'

    addrVer = b'\x00'

    alert_public_key = decodeHex(b'04fc9702847840aaf195de8442ebecedf5b095cdbb9bc716bda9110971b28a49e0ead8564ff0db22209e0374782c093bb899692d524e9d6a6956e7c5ecbcd68284')

    # Not sure if these will be needed later... from chainparams
    secret_key = b'\xef'  # 239
    ext_public_key = b'\x04\x35\x87\xcf'
    ext_secret_key = b'\x04\x35\x83\x94'

    script_address = b'\x05'

    block_height_guess = [
        ('blockchain.info', util.fetch_url_json_path_int('https://blockchain.info/latestblock', 'height')),
        ('blockexplorer.com', util.fetch_url_int('https://blockexplorer.com/q/getblockcount')),
        ('blockr.io', util.fetch_url_json_path_int('http://btc.blockr.io/api/v1/coin/info', 'data/last_block/nb')),
        ('chain.so', util.fetch_url_json_path_int('https://chain.so/api/v2/get_info/BTC', 'data/blocks')),
    ]


#class BitcoinTestnet(Bitcoin):
#    name = "bitcoin-testnet"
#    address_version = b'\x6f'
#    magic = "\xfa\xbf\xb5\xda"

#class BitcoinTestnet3(Bitcoin):
#    name = "bitcoin-testnet3"
#    port = 18333
#    magic = b'\x0b\x11\x09\x07'
#    alert_public_key = decodeHex('04302390343f91cc401d56d68b123028bf52e5fca1939df127f63c6467cdf9c8e2c14b61104cf817d0b780da337893ecc4aaff1309e536162dabbdb45200ca2b0a')
