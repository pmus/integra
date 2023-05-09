from loguru import logger
from random import randint as rnd
from time import sleep
from os import _exit as exit
import sys

sys.path.append("..")
from integra import Integra

ipc = Integra(local_only=True)  # only localhost shares


class DemoClass(object):
    """
    Used to be shared via Integra as a sample service.
    """

    def __init__(self):
        self.some_var = rnd(0, 65535)

    def awesome_method(self) -> int:
        return "QWERTY"

    def reverse(self, some_str: str):
        return some_str[::-1]


def server_main():
    """
    Create an instance of DemoClass and share it with network.
    """
    ipc["democlass"] = DemoClass()  # or: ipc.add_service("democlass", demo)

    try:
        logger.info("Sleeping 60 sec.")
        sleep(60)
    except KeyboardInterrupt:
        pass
        exit(0)


if __name__ == "__main__":
    server_main()
    exit(0)
