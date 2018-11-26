import binascii
from logging import getLogger

from server.base import BaseGPSProtocol

logger = getLogger(__name__)


class ET300Protocol(BaseGPSProtocol):
    PORT = 5000

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
            try:
                packet = await self._reader.read(4096)
                if not packet:
                    logger.warning("device {} client{} connection lost".format(self._imei, self._sock))
                    self._writer.close()
                    self.offline()
                    break

                hexlify = binascii.hexlify(packet).decode('utf-8')
                self._packet = self.parse_packet(hexlify)

                if self._packet.protocol == self.LOGIN:
                    self._writer.write(binascii.unhexlify(self._packet.response))
                    await self._writer.drain()
                    self.login(self._packet.content)

                if self._packet.protocol == self.STATUS:
                    a = self.hex_to_list(self._packet.content)
                    self.status(a)

                if self._packet.protocol == self.LOCATION or self._packet.protocol == self.ALARM:
                    self.location(self._packet.content)

            except Exception as e:
                logger.error("device {} client{} connection lost\n{}".format(self._imei, self._sock, str(e)))
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
        location['gps_accuracy'] = 'real-time'
        if course_bits[2] == '1':
            location['gps_accuracy'] = 'differential positioning'
        location['gps_tracking'] = False
        if course_bits[3] == '1':
            location['gps_tracking'] = True
        if course_bits[4] == '1':
            location['lat'] = -location['lat']
        if course_bits[5] == '0':
            location['lng'] = -location['lng']
        location['course'] = int(course_bits[6:], 2)
        if self._packet.protocol == self.ALARM:
            location.update(self.status(a[27:]))
        # location['serial_no'] = int(self._packet.serial_no, 16)
        self._location = location
        return super().location()

    def status(self, a):
        events = dict()
        status = dict()
        status['events'] = dict()
        terminal_info_bits = self.hex_to_binary(a[0])
        status['engine'] = True
        if terminal_info_bits[0] == '1':
            status['engine'] = False
        status['gps_tracking'] = False
        if terminal_info_bits[1] == '1':
            status['gps_tracking'] = True
        if terminal_info_bits[2:5] == '100':
            status['events']['sos'] = True
            events['status'] = 'SOS'
        if terminal_info_bits[2:5] == '011':
            status['events']['low_battery'] = True
            events['status'] = 'LOW_BATTERY'
        if terminal_info_bits[2:5] == '010':
            status['events']['power_cut'] = True
            events['status'] = 'TEMPERED'
        if terminal_info_bits[2:5] == '001':
            status['events']['shock'] = True
            events['status'] = 'SHOCK'
        status['charge'] = False
        if terminal_info_bits[5] == '1':
            status['charge'] = True
        status['ignition'] = False
        if terminal_info_bits[6] == '1':
            status['ignition'] = True
        status['activated'] = False
        if terminal_info_bits[7] == '1':
            status['activated'] = True
        status['voltage_level'] = int(a[1], 16)
        status['gsm_signal_strength'] = int(a[2], 16)
        if a[3] == '01':
            status['events']['sos'] = True
        if a[3] == '02':
            status['events']['power_cut'] = True
        if a[3] == '03':
            status['events']['shock'] = True
        if a[3] == '04':
            status['events']['fence_in'] = True
        if a[3] == '05':
            status['events']['fence_out'] = True
        if a[4] == '01':
            status['language'] = 'Chinese'
        if a[4] == '02':
            status['language'] = 'English'
        self._status = status
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
        self._packet.response = hexlify[:8] + hexlify[-12:]
        self._serial_no = int(self._packet.serial_no, 16)
        return self._packet

    @staticmethod
    def calculate_latlng(value):
        return (float(value) / 30000) / 60
