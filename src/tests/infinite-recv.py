from loguru import logger
from time import sleep, monotonic as time
from os import _exit as os_exit
import sys

sys.path.append("..")
from integra import ipc


def bench():
    demo = ipc["democlass"]
    demo_type = type(demo)
    logger.success(f"Bench: got demo: {demo}, type: {demo_type}")
    service_names = list(ipc.dict_services.keys())
    logger.success(f"Avail. services: {service_names}")

    var = demo.some_var()
    logger.info(f"some_var is: {var}")

    n = 0
    while True:
        rnd = demo.awesome_method()
        print(f"Request #{n} ok, got {rnd}")
        n += 1
        sleep(1)
    logger.info(f"Last awesome_method is: {rnd}")
    finish = time()
    seconds = finish - start
    speed = int(samples / seconds)
    logger.success(f"Benchmark: {speed} rec/s")


if __name__ == "__main__":
    bench()
    os_exit(0)
