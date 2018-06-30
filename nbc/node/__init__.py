
import sys
from six import PY3

if PY3:
  if sys.platform == 'darwin':
    from .darwin3 import miniupnpc
else:
  if sys.platform == 'darwin':
    from .darwin2 import miniupnpc

class AddrInUseError(Exception): pass
class StopNode(Exception): pass

_upnp = None

def _init_upnp():
  global _upnp
  if _upnp: return _upnp
  
  u = miniupnpc.UPnP()
  u.discoverdelay = 200
  try:
    print('discovering... delay = %ums' % u.discoverdelay)
    devices = u.discover()
    print('%u device(s) detected' % devices)
    _upnp = u
  except Exception as e:
    print('!! meet Exception: %s' % e)
  return _upnp

def add_portmap(port, proto, label=''):
  u = _init_upnp()
  try:
    u.selectigd()  # select Internet Gateway Device
    extAddr = u.externalipaddress()
    print('local ip address %s: ' % u.lanaddr)
    print('external ip address: %s' % extAddr)
    print('%s %s' % (u.statusinfo(), u.connectiontype()))
    print('trying to redirect %s port %u %s => %s port %u %s' %
          (extAddr, port, proto, u.lanaddr, port, proto))
    
    # find a free port for the redirection
    eport = port
    r = u.getspecificportmapping(eport,proto)
    while r != None and eport < 65536:
      eport = eport + 1
      r = u.getspecificportmapping(eport,proto)
    b = u.addportmapping(eport,proto,u.lanaddr,port,label,'')
    if b:
      print('success! now waiting for %s request on %s:%u' % (proto,extAddr,eport))
      return u
    else:
      print('!! failed')
  except Exception as e:
    print('!! meet Exception: %s' % e)

def remove_portmap(port, proto):
  if not _upnp: return
  try:
    b = _upnp.deleteportmapping(port,proto)
    if b:
      print('successfully deleted port mapping')
    else:
      print('!! failed to remove port mapping')
  except Exception as e:
    print('!! meet Exception: %s' % e)
