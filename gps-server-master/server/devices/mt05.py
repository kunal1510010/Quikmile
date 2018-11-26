import binascii
from logging import getLogger

from server.base import BaseGPSProtocol

logger = getLogger(__name__)


class MT05Protocol(BaseGPSProtocol):
    PORT = 5002

    LOGIN = '5000'
    LOCATION = '9955'

    async def start(self):
        logger.info("connection from client {}".format(self._sock))

        i = 1
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
                self._serial_no = i

                if self._packet.protocol == self.LOGIN:
                    response = '40400012' + self._imei + '4000' + self._packet.end_bit
                    self._writer.write(binascii.unhexlify(response))
                    await self._writer.drain()

                    self.login()

                if self._packet.protocol == self.LOCATION:
                    content = binascii.unhexlify(self._packet.content).decode()
                    self.location(content)

                i += 1
            except Exception as e:
                logger.error("device {} client{} connection lost\n{}".format(self._imei, self._sock, str(e)))
                self._writer.close()
                self.offline()
                break

    async def login(self):
        logger.info("login from device: {}".format(self._imei))
        await super().login()

    def parse_packet(self, packet):
        self._packet.start_bit = packet[:4]
        self._packet.length = packet[4:8]
        self._packet.end_bit = packet[-8:]
        self._packet.protocol = packet[22:26]
        self._packet.imei = packet[8:22]
        self._packet.content = packet[26:-8]
        self._imei = self._packet.imei
        return self._packet

    def location(self, body):
        data = dict()
        events = dict()

        gps_data = [c.split(',') for c in body.split('|')]
        gprmc = gps_data[0]

        data['charge'] = True
        data['voltage_level'] = 6
        data['gps_tracking'] = False
        if gprmc[1] == 'A':
            data['gps_tracking'] = True

            data['events'] = dict()
            data['hdop'] = float(gps_data[1][0])
            data['alt'] = float(gps_data[2][0])
            data['odometer'] = float(gps_data[5][0][0])
            data['voltage_level'] = self.calculate_voltage(gps_data[4][1]) // 4
            data['gps_battery_level'] = self.calculate_voltage(gps_data[4][0])
            status_bits = self.hex_to_binary(gps_data[3][0])

            if status_bits[0] == '1':
                data['events']['immobilizer'] = True
                events['status'] = 'ENGINE_CUT'
            if status_bits[1] == '1':
                data['events']['alarm'] = True
            if status_bits[8] == '1':
                data['events']['sos'] = True
                events['status'] = 'SOS'
            if status_bits[9] == '1':
                data['events']['power_cut'] = True
                data['charge'] = False
                events['status'] = 'TEMPERED'

            data['ignition'] = False
            if status_bits[12] == '1':
                data['ignition'] = True

            data['datetime'] = '{}-{}-{} {}:{}:{}'.format(gprmc[8][4:], gprmc[8][2:4], gprmc[8][:2], gprmc[0][:2],
                                                          gprmc[0][2:4],
                                                          gprmc[0][4:10])

            data['lat'] = self.calculate_latlng(gprmc[2][:2], gprmc[2][2:])
            if gprmc[3] == 'S':
                data['lat'] = -data['lat']
            data['lng'] = self.calculate_latlng(gprmc[4][:3], gprmc[4][3:])
            if gprmc[5] == 'W':
                data['lng'] = -data['lng']
            data['speed'] = float(gprmc[6]) * 1.852
            data['course'] = float(gprmc[7])

        self._events = events
        self._location = data
        return super().location()

    @staticmethod
    def calculate_latlng(degree, min):
        coordinate = float(degree)
        coordinate += float(min) / 60
        return coordinate

    @staticmethod
    def calculate_voltage(hex):
        return (int(hex, 16) * 6) // 1024
