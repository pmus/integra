import pyximport

pyximport.install()
from loguru import logger
import integra
from tools.classes import DemoClass
from tools.asynctool import myasync
from time import sleep, monotonic as time
from os import _exit as os_exit

logger.add(".//logs//client_{time}.log", rotation="1 week")


def test():
    try:
        mysuper = integra.get_service_wait("notfoundclass", timeout=3)
    except Exception as e:
        logger.success("Got error as expected!")
        logger.error(f"// {e}")
        os_exit(0)


if __name__ == "__main__":
    test()
