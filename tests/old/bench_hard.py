import pyximport

pyximport.install()
from loguru import logger
from tools.classes import DemoClass
from tools.asynctool import myasync
from time import sleep, time
from os import _exit as os_exit

#######################
# Benchmark fucntions #
#######################
logger.add(".//logs//client_{time}.log", rotation="1 week")


def bench(num):
    import integra

    num += 1
    demo = integra.get_service_wait("democlass")
    logger.success(f"{num}: Bench: got demo: {demo}")

    var = demo.some_var()
    logger.success(f"{num}: some_var is: {var}")

    start = time()
    samples = 10_000
    ...
    for n in range(0, samples):
        rnd = demo.awesome_method()
    logger.info(f"{num}: Last awesome_method is: {rnd}, data is {rnd.data}")
    finish = time()
    seconds = finish - start
    speed = int(samples / seconds)
    logger.success(f"{num}: Benchmark: {speed} rec/s")


if __name__ == "__main__":
    from multiprocessing.dummy import Pool as ThreadPool

    WORKERS = 10
    dummy = list(range(0, WORKERS))
    pool = ThreadPool(WORKERS)
    results = pool.map(bench, dummy)
    pool.close()
    pool.join()
    sleep(10)
    os_exit(0)
