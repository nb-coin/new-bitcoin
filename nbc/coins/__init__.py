
from .newbitcoin import Newbitcoin

from .coin import satoshi_per_coin

__all__ = [
    'Newbitcoin', 'satoshi_per_coin'
]

Coins = [
    Newbitcoin,
]


def get_coin(name = None, symbol = None):
    if name is None: name = ''
    if symbol is None: symbol = ''
    
    for coin in Coins:
        if name and name.lower() == coin.name or symbol.upper() in coin.symbols:
            return coin
    
    return None
