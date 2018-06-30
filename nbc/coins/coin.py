
__all__ = ['Coin', 'satoshi_per_coin']


satoshi_per_coin = 100000000

class Coin(object):
    name = None

    symbols = [ ]
    symbol = None

    protocol_version = 70002
    dns_seeds = [ ]

    port = 0

    genesis_version = 1
    genesis_block_hash = b'\x00' * 32
    genesis_merkle_root = b'\x00' * 32
    genesis_timestamp = 0
    genesis_bits = 504365040    # 0x1e0ffff0
    genesis_nonce = 0

    magic = b'\x00' * 4

    addrVer = b'\x00'

    alert_public_key = None

    checkpoint_public_key = None

    # Callables that can be used to guess the current block height. This data
    # should not be trusted blindly, but is useful for approximating the
    # completeness of a blockchain sync.
    # Each entry should be a (name, callable) tuple
    block_height_guess = []

    def __hash__(self):
        return hash(self.symbol)

    def __cmp__(self, other):
        return cmp(self.name, other.name)

    def __str__(self):
        return '<%s>' % self.name.capitalize()
