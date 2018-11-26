import binascii
from asyncio import ensure_future
from logging import getLogger

from server.base import BaseGPSProtocol
from server.utils import call_later

logger = getLogger(__name__)


class GT06Protocol(BaseGPSProtocol):
    PORT = 5005

    START = '7878'
    START_ANALOG = '7979'
    LOGIN = '01'
    LOCATION = '12'
    STATUS = '13'
    STRING = '15'
    ALARM = '16'
    ADDRESS = '1a'
    COMMAND = '80'
    ANALOG = '94'

    async def start(self):
        logger.info("connection from client {}".format(self._sock))
        while True:
            try:
                packet = await self._reader.read(4096)
                if not packet:
                    logger.warning("device {} client{} connection lost".format(self._imei, self._sock))
                    self._writer.close()
                    self.offline()
                    break

                hexlify = binascii.hexlify(packet).decode('utf-8')
                self._packet = self.parse_packet(hexlify)
                if self._packet.start_bit == self.START_ANALOG:
                    self._packet = self.parse_packet_extended(hexlify)
                logger.info('{}\n{} {}'.format(self._packet.response, self._packet.protocol, self._packet.content))

                if self._packet.protocol == self.LOGIN:
                    self.login(self._packet.content)
                    await self.server_response()

                if self._packet.protocol == self.STATUS:
                    a = self.hex_to_list(self._packet.content)
                    self.status(a)
                    ensure_future(call_later(self.server_response(), 10))

                if self._packet.protocol == self.LOCATION or self._packet.protocol == self.ALARM:
                    self.location(self._packet.content)

                if self._packet.protocol == self.ANALOG:
                    self.analog(self._packet.content)

                # ensure_future(self.send_data())
            except Exception as e:
                logger.error("device {} client{} connection lost\n{}".format(self._imei, self._sock, str(e)))
                self._writer.close()
                self.offline()
                break

    def location(self, hexlify):
        location = dict()
        a = self.hex_to_list(hexlify)
        logger.info("location {}".format(a))
        location['device_time'] = '20%02d-%02d-%02d %02d:%02d:%02d' % tuple([int(x, 16) for x in a[:6]])
        location['satellites'] = int(a[6][1], 16)
        location['gps_tracking'] = self._status.get('gps_tracking')
        # location['gps_tracking'] = True
        lat_value = int(''.join(a[7:11]), 16)
        lng_value = int(''.join(a[11:15]), 16)
        location['lat'] = self.calculate_latlng(lat_value)
        location['lng'] = self.calculate_latlng(lng_value)
        location['speed'] = int(a[15], 16)
        course_bits = self.hex_to_binary(''.join(a[16:18]))
        location['gps_accuracy'] = 'real-time'
        if course_bits[2] == '1':
            location['gps_accuracy'] = 'differential positioning'
        location['gps_positioned'] = False
        if course_bits[3] == '1':
            location['gps_positioned'] = True
        if course_bits[4] == '1':
            location['lat'] = -location['lat']
        if course_bits[5] == '0':
            location['lng'] = -location['lng']
        location['course'] = int(course_bits[6:], 2)
        if self._packet.protocol == self.ALARM:
            self.status(a[26:])
        self._location = location
        logger.info('location: ', location)
        return super().location()

    def status(self, a):
        attr = dict()
        events = dict()
        attr['events'] = dict()
        terminal_info_bits = self.hex_to_binary(a[0])
        logger.info('terminal bit: {}'.format(terminal_info_bits))
        attr['ignition'] = False
        if terminal_info_bits[1] == '1':
            attr['ignition'] = True
        attr['charge'] = False
        if terminal_info_bits[2] == '1':
            attr['charge'] = True
        if terminal_info_bits[3:6] == '100':
            attr['events']['sos'] = True
            events['status'] = 'SOS'
        if terminal_info_bits[3:6] == '011':
            attr['events']['low_battery'] = True
            events['status'] = 'LOW_BATTERY'
        if terminal_info_bits[3:6] == '010':
            attr['events']['power_cut'] = True
            events['status'] = 'TEMPERED'
        if terminal_info_bits[3:6] == '001':
            attr['events']['sock'] = True
            events['status'] = 'SHOCK'
        attr['gps_tracking'] = False
        if terminal_info_bits[6] == '1':
            attr['gps_tracking'] = True
        if terminal_info_bits[7] == '1':
            attr['events']['immobilizer'] = True
            events['status'] = 'ENGINE_CUT'
        attr['voltage_level'] = int(a[1], 16)
        attr['gsm_signal_strength'] = int(a[2], 16)
        if a[4] == '01':
            attr['language'] = 'Chinese'
        if a[4] == '02':
            attr['language'] = 'English'
        self._status = attr
        self._events = events
        return super().status()

    def analog(self, hexlify):
        analog = dict()
        sub_protocol = hexlify[:2]
        if sub_protocol == '00':
            analog['external_voltage'] = int(hexlify[2:6], 16) / 100
        self._events['analog'] = analog
        return super().status()

    def login(self, hexlify):
        self._imei = hexlify[1:]
        # self._data['imei'] = self._imei
        logger.info("login from device: {}".format(self._imei))
        return super().login()

    def parse_packet(self, hexlify):
        self._packet.start_bit = hexlify[:4]
        self._packet.length = hexlify[4:6]
        self._packet.protocol = hexlify[6:8]
        self._packet.content = hexlify[8:-12]
        self._packet.serial_no = hexlify[-12:-8]
        self._packet.error_check = hexlify[-8:-4]
        self._packet.stop_bit = hexlify[-4:]
        self._packet.response = '7878050100059FF80D0A'
        self._serial_no = int(self._packet.serial_no, 16)
        return self._packet

    def parse_packet_extended(self, hexlify):
        self._packet.start_bit = hexlify[:4]
        self._packet.length = hexlify[4:8]
        self._packet.protocol = hexlify[8:10]
        self._packet.content = hexlify[10:-12]
        self._packet.serial_no = hexlify[-12:-8]
        self._packet.error_check = hexlify[-8:-4]
        self._packet.stop_bit = hexlify[-4:]
        self._packet.response = '7878050100059FF80D0A'
        self._serial_no = int(self._packet.serial_no, 16)
        return self._packet

    @staticmethod
    def calculate_latlng(value):
        return (float(value) / 30000) / 60
