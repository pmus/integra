from loguru import logger
from os import _exit as os_exit
import sys

sys.path.append("..")
from integra import ipc

demo = ipc["democlass"]  # Same as:demo = ipc.get_service_wait("democlass")
awesome = demo.awesome_method()
some_var = demo.some_var()  # Yes, we must 'call' that var.
desrever = demo.reverse("ABC")
logger.success(
    f"Test: got demo: {demo}, type: {type(demo)}, {some_var=}, {awesome=}, {desrever=}"
)
assert awesome == "QWERTY"
assert desrever == "CBA"
ipc.run = False
import time
print('Kill')
time.sleep(100)
os_exit(0)
