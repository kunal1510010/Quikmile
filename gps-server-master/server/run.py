import asyncio
from functools import partial
from multiprocessing import Process

from .base import start_gps_server
from .devices import *


def protocol_server(protocol):
    loop = asyncio.get_event_loop()
    try:
        future = start_gps_server(loop, protocol)
        loop.run_until_complete(future)
        loop.run_forever()
    finally:
        loop.close()


def start():
    workers = []
    for protocol in BaseGPSProtocol.__subclasses__():
        process = Process(target=partial(protocol_server, protocol))
        process.start()
        workers.append(process)

    for p in workers:
        p.join()


if __name__ == '__main__':
    start()
