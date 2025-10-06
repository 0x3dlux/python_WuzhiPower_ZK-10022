#!/usr/bin/python3 -B

from collections import OrderedDict
from bleak import BleakClient
from time import sleep

import subprocess
import argparse
import requests
import logging
import asyncio
import json

class WuzhiBT:
	def __init__(self, mac, logger=None):
		self.status = None
		self.mac = mac
		self.retries = 3
		self.logger = logger
		self.client = None
		self.response_cache = {}
		try:
			open_blue = subprocess.Popen(["bluetoothctl"], shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE)
			open_blue.communicate(b"disconnect %s\n" % mac.encode('utf-8'))
			open_blue.kill()
		except:
			pass

	### Class helpers #########################################################

	def calc_crc(self, data: bytes) -> bytes:
		poly = 0x8005
		init_crc = 0xFFFF
		crc = init_crc
		for byte in data:
			byte = self.reflect_bits(byte, 8)
			crc ^= (byte << 8)
			for _ in range(8):
				if crc & 0x8000:
					crc = (crc << 1) ^ poly
				else:
					crc <<= 1
				crc &= 0xFFFF
		crc = self.reflect_bits(crc, 16)
		crc_swapped = ((crc & 0xFF) << 8) | (crc >> 8)
		return crc_swapped.to_bytes(2, byteorder='big')

	@staticmethod
	def reflect_bits(data, width):
		reflection = 0
		for i in range(width):
			if data & (1 << i):
				reflection |= (1 << (width - 1 - i))
		return reflection

	@staticmethod
	def nice_hex(bytearray):
		return f"{bytearray.hex()[0:4]} | {bytearray.hex()[4:6]} | {' '.join(bytearray.hex()[i:i+4] for i in range(6, len(bytearray.hex()), 4))}"

	@staticmethod
	def clamp(n, min_value, max_value):
		return max(min_value, min(n, max_value))

	### Communication #########################################################

	async def connect(self):
		self.client = BleakClient(self.mac)
		self.logger.info(f"Connecting...")

		try:
			await self.client.connect()
			self.logger.info(f"Connected to {self.mac}")
		except:
			self.logger.critical("Connection failed, Wuzhi-Power out of reach or sleeping!")
			exit(1)

		await self.client.start_notify('0000fff1-0000-1000-8000-00805f9b34fb', self.callback)

	async def callback(self, handle, data):
		# self.logger.info(f"Raw callback on {handle}: {data.hex()}")
		self.logger.info(f"Callback: {self.nice_hex(data)}")

		crc = data[-2:]
		data = data[:-2]
		crccheck = self.calc_crc(data)
	
		if crc == crccheck:
			self.logger.info(f"CRC match: {crc.hex()}")
		else:
			self.logger.error(f"CRC mismatch: {crc.hex()} vs. {crccheck.hex()}")
			return False

		settings = OrderedDict()
		if data[2] == 0x3c:
			self.logger.info("Is a 'settings' reply")
			settings['volt_in']    = float(((data[13] & 0xFF) << 8) | (data[14] & 0xFF)) / 100
			settings['volt_set']   = float(((data[3]  & 0xFF) << 8) | (data[4]  & 0xFF)) / 100
			settings['amps_set']   = float(((data[5]  & 0xFF) << 8) | (data[6]  & 0xFF)) / 100
			settings['volt_out']   = float(((data[7]  & 0xFF) << 8) | (data[8]  & 0xFF)) / 100
			settings['amps_out']   = float(((data[9]  & 0xFF) << 8) | (data[10] & 0xFF)) / 100
			settings['w_out']      = float(((data[11] & 0xFF) << 8) | (data[12] & 0xFF)) / 10
			settings['ah_out']     = float(((data[15] & 0xFF) << 8) | (data[16] & 0xFF) | ((data[17] & 0xFF) << 24) | ((data[18] & 0xFF) << 16)) / 1000
			settings['wh_out']     = float(((data[19] & 0xFF) << 8) | (data[20] & 0xFF) | ((data[21] & 0xFF) << 24) | ((data[22] & 0xFF) << 16)) / 1000
			settings['on_time_h']  =       ((data[23] & 0xFF) << 8) | (data[24] & 0xFF)
			settings['on_time_m']  =       ((data[25] & 0xFF) << 8) | (data[26] & 0xFF)
			settings['on_time_s']  =       ((data[27] & 0xFF) << 8) | (data[28] & 0xFF)
			settings['s_temp']     = float(((data[29] & 0xFF) << 8) | (data[30] & 0xFF)) / 10
			settings['p_temp']     = float(((data[31] & 0xFF) << 8) | (data[32] & 0xFF)) / 10
			settings['keylock']    =       ((data[33] & 0xFF) << 8) | (data[34] & 0xFF)
			settings['protection'] =       ((data[35] & 0xFF) << 8) | (data[36] & 0xFF)
			settings['outstate']   =       ((data[37] & 0xFF) << 8) | (data[38] & 0xFF)
			settings['powerbtn']   =       ((data[39] & 0xFF) << 8) | (data[40] & 0xFF)
			settings['reserved']   =       ((data[41] & 0xFF) << 8) | (data[42] & 0xFF)
			settings['backlight']  =       ((data[43] & 0xFF) << 8) | (data[44] & 0xFF)
			settings['timeout']    =       ((data[45] & 0xFF) << 8) | (data[46] & 0xFF)
			settings['product']    =       ((data[47] & 0xFF) << 8) | (data[48] & 0xFF)
		if data[2] == 0x1c:
			self.logger.info("Is a 'limits' reply")
			settings['volt_set']   = float(((data[3]  & 0xFF) << 8) | (data[4]  & 0xFF)) / 100
			settings['amps_set']   = float(((data[5]  & 0xFF) << 8) | (data[6]  & 0xFF)) / 100
			settings['LVP']        = float(((data[7]  & 0xFF) << 8) | (data[8]  & 0xFF)) / 100
			settings['OVP']        = float(((data[9]  & 0xFF) << 8) | (data[10] & 0xFF)) / 100
			settings['OCP']        = float(((data[11] & 0xFF) << 8) | (data[12] & 0xFF)) / 100
			settings['OPP']        = float(((data[13] & 0xFF) << 8) | (data[14] & 0xFF)) / 10
			settings['OHP_h']      =       ((data[15] & 0xFF) << 8) | (data[16] & 0xFF)
			settings['OHP_m']      =       ((data[17] & 0xFF) << 8) | (data[18] & 0xFF)
			settings['OAH']        = float(((data[19] & 0xFF) << 8) | (data[20] & 0xFF) | ((data[21] & 0xFF) << 24) | ((data[22] & 0xFF) << 16)) / 1000
			settings['OWH']        = float(((data[23] & 0xFF) << 8) | (data[24] & 0xFF) | ((data[25] & 0xFF) << 24) | ((data[26] & 0xFF) << 16)) / 100
			settings['OTP']        = float(((data[27] & 0xFF) << 8) | (data[28] & 0xFF)) / 10
			settings['INI']        =       ((data[29] & 0xFF) << 8) | (data[30] & 0xFF)

		if len(settings) > 0:
			self.response_cache[data.hex()[0:2]].set_result(settings)
		else:
			self.response_cache[data.hex()[0:2]].set_result(data)

	async def query(self, cmd):
		response_data = None
		x = None
		for x in range(0, self.retries):
			response_data = await self.write(cmd=cmd)
			if not response_data:
				self.logger.info(f"{x+1}. try failed, retrying...")
				sleep(0.1)
			else:
				break
		if not response_data:
			self.logger.error(f"Command {cmd} failed after {x+1} tries")
			return False
		return response_data

	async def write(self, cmd):
		self.response_cache[cmd[0:2]] = asyncio.Future()
		message_bytes  = bytearray.fromhex(cmd)
		message_bytes += self.calc_crc(message_bytes)

		self.logger.info(f"Command {cmd}, sending: {message_bytes.hex()}")
		await self.client.write_gatt_char('0000fff3-0000-1000-8000-00805f9b34fb', message_bytes)

		try:
			result = await asyncio.wait_for(self.response_cache[cmd[0:2]], 1)
		except asyncio.TimeoutError:
			self.logger.warning(f"Timed out waiting for response to command {cmd}")
			return False

		return result if result else False

	### Getters / Setters #####################################################

	async def get_status(self):
		return await self.query("01030000001e")

	async def get_limits(self):
		return await self.query("01030050000e")

	async def set_off(self):
		self.logger.warning("Switching output off")
		return await self.query("010600120000")

	async def set_on(self):
		self.logger.warning("Switching output on")
		return await self.query("010600120001")

	async def set_volt(self, volt):
		volt = self.clamp(volt, 0, 125)
		hexvolt = int(volt * 100).to_bytes(2, byteorder='big').hex()
		self.logger.warning(f"Setting voltage to {volt}V ({hexvolt})")
		return await self.query("01060000" + hexvolt)

	async def set_amps(self, amps):
		amps = self.clamp(amps, 0, 22)
		hexamps = int(amps * 100).to_bytes(2, byteorder='big').hex()
		self.logger.warning(f"Setting amps to {amps}A ({hexamps})")
		return await self.query("01060001" + hexamps)

	async def set_backlight(self, level):
		level = self.clamp(level, 0, 5)
		self.logger.warning(f"Setting backlight to {level}")
		return await self.query("01060014000" + str(level))

	async def set_buzzer(self, level):
		level = self.clamp(level, 0, 1)
		self.logger.warning(f"Setting buzzer to {level}")
		return await self.query("0106001c000" + str(level))

	async def set_timeout(self, mins):
		mins = self.clamp(mins, 0, 100000)
		hexmins = int(mins).to_bytes(2, byteorder='big').hex()
		self.logger.warning(f"Setting timeout to {mins}min ({hexmins})")
		return await self.query("01060015" + str(hexmins))

	async def restart(self):
		return await self.query("0106002f0001")

### Helpers ###################################################################

def pr(result):
	try:
		logger.warning(json.dumps(result, indent=4))
	except:
		logger.warning("Result: " + WuzhiBT.nice_hex(result))

### Main ######################################################################

parser = argparse.ArgumentParser()
parser.add_argument("-m", "--mac",       help="MAC address",        default="FB:5E:94:63:70:0C", type=str)
parser.add_argument("-s", "--status",    help="show status",        action="store_true")
parser.add_argument("-l", "--limits",    help="show limits",        action="store_true")
parser.add_argument("-0", "--off",       help="turn output off",    action="store_true")
parser.add_argument("-1", "--on",        help="turn output on",     action="store_true")
parser.add_argument("-v", "--volt",      help="set output voltage", action="store", type=float)
parser.add_argument("-a", "--amps",      help="set output current", action="store", type=float)
parser.add_argument("-b", "--backlight", help="set backlight",      action="store", type=int)
parser.add_argument("-z", "--buzzer",    help="set buzzer",         action="store", type=int)
parser.add_argument("-t", "--timeout",   help="set timeout",        action="store", type=int)
parser.add_argument("-r", "--restart",   help="restart PSU",        action="store_true")
parser.add_argument("-c", "--cron",      help="do the cron job",    action="store_true")
parser.add_argument("-d", "--debug",     help="show me the money",  action="store_true")
args = parser.parse_args()

if args.debug:
	log_format = '%(asctime)s.%(msecs)03d %(levelname)-7s [%(filename)s:%(lineno)-3d] %(message)s'
	loglevel = logging.INFO # use logging.DEBUG here to also see the (kind of useless) BlueZ and D-Bus debug output
else:
	log_format = '%(message)s'
	loglevel = logging.WARNING

logging.basicConfig(level=loglevel, format=log_format, datefmt='%H:%M:%S')
logger = logging.getLogger()

async def main(args):
	psu = WuzhiBT(mac=args.mac, logger=logger)
	await psu.connect()

	if args.off:
		pr(await psu.set_off())
	if args.on:
		pr(await psu.set_on())
	if args.volt is not None:
		pr(await psu.set_volt(args.volt))
	if args.amps is not None:
		pr(await psu.set_amps(args.amps))
	if args.backlight is not None:
		pr(await psu.set_backlight(args.backlight))
	if args.buzzer is not None:
		pr(await psu.set_buzzer(args.buzzer))
	if args.timeout is not None:
		pr(await psu.set_timeout(args.timeout))
	if args.restart:
		pr(await psu.restart())

	if args.status:
		pr({"Status": await psu.get_status()})
	if args.limits:
		pr({"Limits": await psu.get_limits()})

	if args.cron:
		logger.warning("TODO: add your cron logic here...")

asyncio.run(main(args))
