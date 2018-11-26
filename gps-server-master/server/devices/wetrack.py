import binascii
import traceback
from logging import getLogger

from server.base import BaseGPSProtocol

logger = getLogger(__name__)


class WeTrackProtocol(BaseGPSProtocol):
    PORT = 5004

    START = '7878'
    LOGIN = '01'
    LOCATION = '12'
    STATUS = '13'
    STRING = '15'
    ALARM = '16'
    ADDRESS = '1a'
    COMMAND = '80'

    async def start(self):
        logger.info("connection from client {}".format(self._sock))
        while True:
            self._reader.at_eof()
            try:
                packet = await self._reader.read(4096)
                if not packet:
                    logger.warning("device {} client{} connection lost".format(self._imei, self._sock))
                    self._writer.close()
                    self.offline()
                    break

                hexlify = binascii.hexlify(packet).decode('utf-8')
                self._packet = self.parse_packet(hexlify)

                logger.info("WeTrack Server -> terminal:\n{}".format(self._packet.response))

                if self._packet.protocol == self.LOGIN:
                    await self.server_response()
                    self.login(self._packet.content)

                if self._packet.protocol == self.STATUS:
                    await self.server_response()
                    a = self.hex_to_list(self._packet.content)
                    self.status(a)

                if self._packet.protocol == self.LOCATION or self._packet.protocol == self.ALARM:
                    self.location(self._packet.content)

            except:
                logger.error("device {} client{} connection lost: {}".format(self._imei,
                                                                             self._sock,
                                                                             traceback.format_exc()))
                self._writer.close()
                self.offline()
                break

    def location(self, hexlify):
        location = dict()
        a = self.hex_to_list(hexlify)
        location['device_time'] = '20%02d-%02d-%02d %02d:%02d:%02d' % tuple([int(x, 16) for x in a[:6]])
        location['satellites'] = int(a[6][1], 16)
        lat_value = int(''.join(a[7:11]), 16)
        lng_value = int(''.join(a[11:15]), 16)
        location['lat'] = self.calculate_latlng(lat_value)
        location['lng'] = self.calculate_latlng(lng_value)
        location['speed'] = int(a[15], 16)
        course_bits = self.hex_to_binary(''.join(a[16:18]))
        location['accuracy'] = 'real-time'
        if course_bits[2] == '1':
            location['accuracy'] = 'differential positioning'
        location['tracking'] = False
        if course_bits[3] == '1':
            location['tracking'] = True
        if course_bits[4] == '1':
            location['lat'] = -location['lat']
        if course_bits[5] == '0':
            location['lng'] = -location['lng']
        location['course'] = int(course_bits[6:], 2)
        if self._packet.protocol == self.ALARM:
            self.status(a[27:])
        self._location = location
        return super().location()

    def status(self, a):
        attr = dict()
        events = dict()
        attr['events'] = dict()
        terminal_info_bits = self.hex_to_binary(a[0])
        attr['engine'] = True
        if terminal_info_bits[0] == '1':
            attr['engine'] = False
        attr['tracking'] = False
        if terminal_info_bits[1] == '1':
            attr['tracking'] = True
        if terminal_info_bits[2:5] == '100':
            attr['events']['sos'] = True
            events['status'] = 'SOS'
        if terminal_info_bits[2:5] == '011':
            attr['events']['low_battery'] = True
            events['status'] = 'LOW_BATTERY'
        if terminal_info_bits[2:5] == '010':
            attr['events']['power_cut'] = True
            events['status'] = 'TEMPERED'
        if terminal_info_bits[2:5] == '001':
            attr['events']['sock'] = True
            events['status'] = 'SHOCK'
        attr['charge'] = False
        if terminal_info_bits[5] == '1':
            attr['charge'] = True
        else:
            events['status'] = 'TEMPERED'
        attr['ignition'] = False
        if terminal_info_bits[6] == '1':
            attr['ignition'] = True
        attr['activated'] = False
        if terminal_info_bits[7] == '1':
            attr['activated'] = True
        attr['voltage_level'] = int(a[1], 16)
        attr['gsm_signal_strength'] = int(a[2], 16)
        if a[3] == '01':
            attr['events']['sos'] = True
        if a[3] == '02':
            attr['events']['power_cut'] = True
        if a[3] == '03':
            attr['events']['shock'] = True
        if a[3] == '04':
            attr['events']['fence_in'] = True
        if a[3] == '05':
            attr['events']['fence_out'] = True
        if a[4] == '01':
            attr['language'] = 'Chinese'
        if a[4] == '02':
            attr['language'] = 'English'
        self._status = attr
        self._events = events
        return super().status()

    def login(self, hexlify):
        self._imei = hexlify[1:]
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
        # self._packet.response = '787805010001D9DC0D0A'
        self._packet.response = self.get_response()
        self._serial_no = int(self._packet.serial_no, 16)
        return self._packet

    @staticmethod
    def calculate_latlng(value):
        return (float(value) / 30000) / 60
