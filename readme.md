# Integra
## Small convenient IPC based on

[![N|Solid](https://zeromq.org/images/logo.gif)](https://zeromq.org/)
and [Python-zeroconf](https://python-zeroconf.readthedocs.io/en/latest/)

You can share your Python classes in Bonjour style!
### How does it work?

Server:
```
from integra import ipc
import MySharedClass # Use anything
shared_class = MySharedClass()
ipc["shared_class"] = shared_class # We share it
while True:
    ...
```

Client (any machine on LAN or localhost):
```
from integra import ipc
remote_shared = ipc["shared_class"]
result = remote_shared.awesome_method()
```
That's all, you find your class or service by name and make calls like it's local.
Please note that security is on your own.

## How to install?
```
pip3 install git+https://github.com/pmus/interga.git#egg=integra
```