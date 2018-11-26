from logging import getLogger

from server.base import BaseGPSProtocol

logger = getLogger(__name__)


class GT02Protocol(BaseGPSProtocol):
    PORT = 5003

    START = '('
    END = ')'
    LOGIN = 'BP05'
    LOCATION = 'BR00'

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

                self._packet = self.parse_packet(packet.decode('utf-8'))
                self._serial_no = i

                if self._packet.imei:
                    self.login()

                if self._packet.protocol == self.LOCATION:
                    self.parse_message_body(self._packet.content)

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
        self._packet.start_bit = packet[0]
        self._packet.end_bit = packet[-1]
        self._packet.protocol = packet[13:17]
        self._packet.imei = packet[1:13]
        self._packet.content = packet[17:-1]
        self._imei = self._packet.imei
        return self._packet

    @staticmethod
    def calculate_latlng(degree, min):
        degree = int(degree)
        coordinate = degree + (float(min) / 60)
        return coordinate

    def parse_message_body(self, body):
        data = dict()
        data['lat'] = self.calculate_latlng(body[7:9], body[9:16])
        if body[16] == 'S':
            data['lat'] = -data['lat']
        data['lng'] = self.calculate_latlng(body[17:20], body[20:27])
        if body[27] == 'W':
            data['lng'] = -data['lng']
        data['speed'] = float(body[28:33])

        data['voltage_level'] = 6
        data['course'] = float(body[39:45])
        data['device_time'] = '20{}-{}-{} {}:{}:{}'.format(body[:2], body[2:4], body[4:6], body[33:35], body[35:37],
                                                           body[37:39])
        data['gps_tracking'] = False
        if body[6] == 'A':
            data['gps_tracking'] = True
        io_state = body[45:53]
        data['charge'] = False
        if io_state[0] == '0':
            data['charge'] = True
        data['ignition'] = False
        if io_state[1] == '1':
            data['ignition'] = True
        data['temperature'] = io_state[2:5]
        data['voltage_input'] = self.calculate_voltage(io_state[5:])
        data['total_distance'] = float(int(body[54:62], 16)) / 1000

        self._location = data
        return super().location()

    @staticmethod
    def calculate_voltage(bits):
        return (int(bits[0], 16) * 16 * 16 + int(bits[1], 16) * 16 + int(bits[2], 16)) / 100
