import asyncio
import binascii
import logging
import os
import re
import traceback
import ujson
from asyncio import ensure_future
from collections import namedtuple
from time import time

import consul
from aiohttp import ClientSession
from aiokafka import AIOKafkaProducer
from geopy.distance import vincenty

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Packet = namedtuple('Packet', 'start_bit length protocol content serial_no error_check stop_bit response end_bit imei')
KAFKA_BROKER = os.environ.get('KAFKA_BROKER', 'localhost:9092')
EVENT_TOPIC = 'events'
LOCATION_TOPIC = 'location'
STATUS_TOPIC = 'status'


class IOTClient:
    def __init__(self):
        self._access_token = None
        self._iot_address = self._get_service_address('iot-service')
        self._auth_address = self._get_service_address('auth-service')
        self._username = os.environ.get('ADMIN_USERNAME', 'admin@quikmile.com')
        self._password = os.environ.get('ADMIN_PASSWORD', 'admin')

    async def _auth(self):
        if self._auth_address:
            api = self._auth_address + '/login/'
            data = {'username': self._username, 'password': self._password}
            async with ClientSession() as session:
                async with session.post(api, json=data) as r:
                    if r.status == 200:
                        result = await r.json()
                        self._access_token = result['access_token']
                        return self._access_token

    def _get_service_address(self, service_name):
        c = consul.Consul()
        index, services = c.health.service(service_name)
        address = ''
        for service_info in services:
            service = service_info['Service']
            address = '{}:{}'.format(service['Address'], service['Port'])
        return address

    async def get_gps_registry_by_imei(self, imei):
        if self._iot_address:
            if not self._access_token:
                token = await self._auth()
                if not token:
                    return

            header = {'authorization': 'x-token {}'.format(self._access_token)}
            api = self._iot_address + '/gps/{}/'.format(imei)
            async with ClientSession(headers=header) as session:
                async with session.get(api) as r:
                    if r.status == 200:
                        return await r.json()

                    if r.status == 401:
                        await self._auth()
                        await self.get_gps_registry_by_imei(imei)


class GPSServer:
    def __init__(self, loop=None, gps_protocol=None, producer=None):
        if not loop:
            self._loop = asyncio.get_event_loop()
        else:
            self._loop = loop
        self._protocol = gps_protocol
        self._host = self._protocol.HOST
        self._port = self._protocol.PORT
        self._connected_clients = dict()
        self._producer = producer

    async def connection_cb(self, reader, writer):
        sock = writer.get_extra_info('peername')

        if not self._connected_clients.get(sock):
            self._connected_clients[sock] = dict()
            self._connected_clients[sock]['is_connected'] = True
            self._connected_clients[sock]['protocol'] = None

        self._connected_clients[sock]['protocol'] = self._protocol(server=self, reader=reader, writer=writer, sock=sock,
                                                                   producer=self._producer)
        await self._connected_clients[sock]['protocol'].start()

    def client_disconnected(self, sock):
        self._connected_clients[sock]['is_connected'] = False
        self._connected_clients[sock]['protocol'] = None

    def run(self):
        return asyncio.start_server(self.connection_cb, self._host, self._port, loop=self._loop)


async def start_gps_server(loop, gps_protocol):
    producer = AIOKafkaProducer(loop=loop, bootstrap_servers=KAFKA_BROKER)
    await producer.start()
    gps_server = GPSServer(gps_protocol=gps_protocol, producer=producer)
    try:
        server = await gps_server.run()
        logger.info("Started Serving {} on {}".format(gps_protocol.__name__,
                                                      server.sockets[0].getsockname()))
    except:
        logger.error(traceback.print_exc())


class BaseGPSProtocol:
    HOST = '0.0.0.0'

    def __init__(self, server, reader, writer, sock=None, producer=None):
        self._producer = producer
        self._server = server
        self._reader = reader
        self._writer = writer
        self._sock = sock
        self._imei = None
        self._serial_no = None
        self._status = dict()
        self._location = dict()
        self._events = dict()
        self._packet = Packet

    def login(self, *args, **kwargs):
        if self._imei and self.is_valid_imei():
            self._events['imei'] = self._imei
            self._events['status'] = 'ONLINE'
            return self.publish(EVENT_TOPIC, self._events)

    def offline(self):
        self._events['imei'] = self._imei
        self._events['status'] = 'OFFLINE'
        return self.publish(EVENT_TOPIC, self._events)

    def location(self, *args, **kwargs):
        if self._location.get('tracking'):
            self.publish(LOCATION_TOPIC, self._location)
        else:
            self.publish(EVENT_TOPIC, {'status': 'INVALID_LOCATION'})

    def status(self, *args, **kwargs):
        self.publish(STATUS_TOPIC, self._status)
        if self._events:
            self.publish(EVENT_TOPIC, self._events)

    def publish(self, topic, message):
        if self._imei:
            # message['vehicle_id'] = self._vehicle_id
            # message['sim_number'] = self._sim_number
            if not message.get('imei'):
                message['imei'] = self._imei
            if not message.get('timestamp'):
                message['timestamp'] = int(time())
            if not message.get('serial_no') and self._serial_no:
                message['serial_no'] = self._serial_no

            logger.info("publishing {}: {}".format(topic, message))
            message = ujson.dumps(message).encode('utf-8')
            ensure_future(self._producer.send_and_wait(topic, message))
        else:
            logger.warning("unknown device: {} {}".format(topic, message))

    async def server_response(self):
        if len(self._packet.response) % 2 == 0:
            self._writer.write(binascii.unhexlify(self._packet.response))
            await self._writer.drain()
        else:
            logger.error('invalid server response: {}'.format(self._packet.response))

    @staticmethod
    def hex_to_binary(hexlify):
        binary_suffix = bin(int(hexlify, 16))[2:]
        leading_zeros = int(8 * (len(hexlify) / 2) - len(binary_suffix))
        return '{}{}'.format('0' * leading_zeros, binary_suffix)

    @staticmethod
    def hex_to_decimal(hexlify):
        return ''.join([str(int(x, 16)) for x in hexlify])

    @staticmethod
    def calculate_distance(p1, p2):
        if p1 and p2:
            return vincenty(p1, p2).km
        else:
            return 0

    @staticmethod
    def hex_to_list(hexlify):
        return [hexlify[i] + hexlify[i + 1] for i in range(0, len(hexlify), 2)]

    @staticmethod
    def get_tentative_distance(seconds):
        speed = 27.7778 * 5  # m/sec
        distance = (speed * abs(seconds)) / 1000
        return distance

    def get_response(self):
        res = '787805' + self._packet.protocol + self._packet.serial_no
        checksum = '05' + self._packet.protocol + self._packet.serial_no
        res += hex(self.crc16(checksum))[2:]
        res += '0D0A'
        return res

    def crc16(self, data):
        crc_table = [
            0X0000, 0X1189, 0X2312, 0X329B, 0X4624, 0X57AD, 0X6536, 0X74BF, 0X8C48, 0X9DC1, 0XAF5A,
            0XBED3, 0XCA6C, 0XDBE5, 0XE97E, 0XF8F7, 0X1081, 0X0108, 0X3393, 0X221A, 0X56A5, 0X472C,
            0X75B7, 0X643E, 0X9CC9, 0X8D40, 0XBFDB, 0XAE52, 0XDAED, 0XCB64, 0XF9FF, 0XE876, 0X2102,
            0X308B, 0X0210, 0X1399, 0X6726, 0X76AF, 0X4434, 0X55BD, 0XAD4A, 0XBCC3, 0X8E58, 0X9FD1,
            0XEB6E, 0XFAE7, 0XC87C, 0XD9F5, 0X3183, 0X200A, 0X1291, 0X0318, 0X77A7, 0X662E, 0X54B5,
            0X453C, 0XBDCB, 0XAC42, 0X9ED9, 0X8F50, 0XFBEF, 0XEA66, 0XD8FD, 0XC974, 0X4204, 0X538D,
            0X6116, 0X709F, 0X0420, 0X15A9, 0X2732, 0X36BB, 0XCE4C, 0XDFC5, 0XED5E, 0XFCD7, 0X8868,
            0X99E1, 0XAB7A, 0XBAF3, 0X5285, 0X430C, 0X7197, 0X601E, 0X14A1, 0X0528, 0X37B3, 0X263A,
            0XDECD, 0XCF44, 0XFDDF, 0XEC56, 0X98E9, 0X8960, 0XBBFB, 0XAA72, 0X6306, 0X728F, 0X4014,
            0X519D, 0X2522, 0X34AB, 0X0630, 0X17B9, 0XEF4E, 0XFEC7, 0XCC5C, 0XDDD5, 0XA96A, 0XB8E3,
            0X8A78, 0X9BF1, 0X7387, 0X620E, 0X5095, 0X411C, 0X35A3, 0X242A, 0X16B1, 0X0738, 0XFFCF,
            0XEE46, 0XDCDD, 0XCD54, 0XB9EB, 0XA862, 0X9AF9, 0X8B70, 0X8408, 0X9581, 0XA71A, 0XB693,
            0XC22C, 0XD3A5, 0XE13E, 0XF0B7, 0X0840, 0X19C9, 0X2B52, 0X3ADB, 0X4E64, 0X5FED, 0X6D76,
            0X7CFF, 0X9489, 0X8500, 0XB79B, 0XA612, 0XD2AD, 0XC324, 0XF1BF, 0XE036, 0X18C1, 0X0948,
            0X3BD3, 0X2A5A, 0X5EE5, 0X4F6C, 0X7DF7, 0X6C7E, 0XA50A, 0XB483, 0X8618, 0X9791, 0XE32E,
            0XF2A7, 0XC03C, 0XD1B5, 0X2942, 0X38CB, 0X0A50, 0X1BD9, 0X6F66, 0X7EEF, 0X4C74, 0X5DFD,
            0XB58B, 0XA402, 0X9699, 0X8710, 0XF3AF, 0XE226, 0XD0BD, 0XC134, 0X39C3, 0X284A, 0X1AD1,
            0X0B58, 0X7FE7, 0X6E6E, 0X5CF5, 0X4D7C, 0XC60C, 0XD785, 0XE51E, 0XF497, 0X8028, 0X91A1,
            0XA33A, 0XB2B3, 0X4A44, 0X5BCD, 0X6956, 0X78DF, 0X0C60, 0X1DE9, 0X2F72, 0X3EFB, 0XD68D,
            0XC704, 0XF59F, 0XE416, 0X90A9, 0X8120, 0XB3BB, 0XA232, 0X5AC5, 0X4B4C, 0X79D7, 0X685E,
            0X1CE1, 0X0D68, 0X3FF3, 0X2E7A, 0XE70E, 0XF687, 0XC41C, 0XD595, 0XA12A, 0XB0A3, 0X8238,
            0X93B1, 0X6B46, 0X7ACF, 0X4854, 0X59DD, 0X2D62, 0X3CEB, 0X0E70, 0X1FF9, 0XF78F, 0XE606,
            0XD49D, 0XC514, 0XB1AB, 0XA022, 0X92B9, 0X8330, 0X7BC7, 0X6A4E, 0X58D5, 0X495C, 0X3DE3,
            0X2C6A, 0X1EF1, 0X0F78]

        crc_x = int("FFFF", 16)
        cr1 = int("FF", 16)
        cr2 = int("FFFF", 16)
        i = 0
        while i < len(data):
            cr_str = data[i:i + 2]
            cr_hex = int(cr_str, 16)
            j = (crc_x ^ cr_hex) & cr1
            crc_x = (crc_x >> 8) ^ crc_table[j]
            i = i + 2

        return crc_x ^ 0xffff

    def is_valid_imei(self):
        """ Return True if imei is numeric else False. """
        value = re.compile(r'^[0-9]+$')  # regex for numeric validation
        bool = False
        if value.match(self._imei):
            bool = True
        return bool
