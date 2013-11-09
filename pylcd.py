'''
Copyright (C) 2012 Matthew Skolaut

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and 
associated documentation files (the "Software"), to deal in the Software without restriction, 
including without limitation the rights to use, copy, modify, merge, publish, distribute, 
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is 
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial
portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE 
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
'''

import smbus
from time import *

backlight = 0x08

# General i2c device class so that other devices can be added easily
class i2c_device:
	def __init__(self, addr, port):
		self.addr = addr
		self.bus = smbus.SMBus(port)

	def write(self, byte):
		self.bus.write_byte(self.addr, byte)

	def read(self):
		return self.bus.read_byte(self.addr)

	def read_nbytes_data(self, data, n): # For sequential reads > 1 byte
		return self.bus.read_i2c_block_data(self.addr, data, n)


class lcd:
	#initializes objects and lcd
	'''
	Reverse Codes:
	0: lower 4 bits of expander are commands bits
	1: top 4 bits of expander are commands bits AND P0-4 P1-5 P2-6
	2: top 4 bits of expander are commands bits AND P0-6 P1-5 P2-4
	
	
	// Command definitions, see page 24 of the datasheet for more info

	HD44780_CMD_CLEAR_DISPLAY               0x01
	HD44780_CMD_RETURN_HOME                 0x02
	HD44780_CMD_DISPLAY_SHIFT_ON            0x07
	HD44780_CMD_DISPLAY_SHIFT_OFF           0x06
	HD44780_CMD_DISPLAY_ON_CURSOR_BLINK     0x0F
	HD44780_CMD_DISPLAY_ON_BLINK            0x0D
	HD44780_CMD_DISPLAY_ON_CURSOR           0x0E
	HD44780_CMD_DISPLAY_ON                  0x0C
	HD44780_CMD_DISPLAY_OFF                 0x08
	HD44780_CMD_DISPLAY_SHIFT_RIGHT         0x1C
	HD44780_CMD_DISPLAY_SHIFT_LEFT          0x18
	HD44780_CMD_1_LINE_MODE                 0x20
	HD44780_CMD_2_LINE_MODE                 0x28
	HD44780_CMD_SETDDRAMADDR 				0x80

	'''
	def __init__(self, addr, port, reverse=0, col = 20, row = 4):
		self.reverse = reverse
		self.lcd_device = i2c_device(addr, port)
		self.m_col = 0
		self.m_row = 0
		self.num_row = row
		self.num_col = col
		if self.reverse:
			self.lcd_device.write(0x30)
			self.lcd_strobe()
			sleep(0.0005)
			self.lcd_strobe()
			sleep(0.0005)
			self.lcd_strobe()
			sleep(0.0005)
			self.lcd_device.write(0x20|backlight)
			self.lcd_strobe()
			sleep(0.0005)
		else:
			self.lcd_device.write(0x03)
			self.lcd_strobe()
			sleep(0.0005)
			self.lcd_strobe()
			sleep(0.0005)
			self.lcd_strobe()
			sleep(0.0005)
			self.lcd_device.write(0x02|backlight)
			self.lcd_strobe()
			sleep(0.0005)

		self.lcd_write(0x28)
		self.lcd_write(0x08)
		self.lcd_write(0x01)
		self.lcd_write(0x06)
		self.lcd_write(0x0C)
		#self.lcd_write(0x0F)

	# clocks EN to latch command
	def lcd_strobe(self):
		if self.reverse == 1:
			self.lcd_device.write(self.lcd_device.read() | 0x04 | backlight)
			self.lcd_device.write((self.lcd_device.read() & 0xFB)|backlight)
		elif self.reverse == 2:
			self.lcd_device.write(self.lcd_device.read() | 0x01)
			self.lcd_device.write(self.lcd_device.read() & 0xFE)
		else:
			self.lcd_device.write(self.lcd_device.read() | 0x10)
			self.lcd_device.write(self.lcd_device.read() & 0xEF)

	# write a command to lcd
	def lcd_write(self, cmd):
		if self.reverse:
			self.lcd_device.write(((cmd >> 4)<<4)|backlight)
			self.lcd_strobe()
			self.lcd_device.write(((cmd & 0x0F)<<4)|backlight)
			self.lcd_strobe()
			self.lcd_device.write(backlight)
		else:
			self.lcd_device.write((cmd >> 4)|backlight)
			self.lcd_strobe()
			self.lcd_device.write((cmd & 0x0F)|backlight)
			self.lcd_strobe()
			self.lcd_device.write(backlight)

	# write a character to lcd (or character rom)
	def lcd_write_char(self, charvalue):
		if self.reverse == 1:
			self.lcd_device.write((0x01 | backlight | (charvalue >> 4)<<4))
			self.lcd_strobe()
			self.lcd_device.write((0x01 | backlight | (charvalue & 0x0F)<<4))
			self.lcd_strobe()
			self.lcd_device.write(backlight)
		elif self.reverse == 2:
			self.lcd_device.write((0x04 | backlight | (charvalue >> 4)<<4))
			self.lcd_strobe()
			self.lcd_device.write((0x04 | backlight | (charvalue & 0x0F)<<4))
			self.lcd_strobe()
			self.lcd_device.write(backlight)
		else:
			self.lcd_device.write((0x40 | backlight | (charvalue >> 4)))
			self.lcd_strobe()
			self.lcd_device.write((0x40 | backlight (charvalue & 0x0F)))
			self.lcd_strobe()
			self.lcd_device.write(backlight)

	# put char function
	def putc(self, char):
		if self.m_row < self.num_row and self.m_col < self.num_col:
			self.lcd_write_char(ord(char))
			self.m_col = self.m_col + 1
			if (self.m_col == self.num_col):
				self.m_col = 0
				self.m_row = self.m_row+1
				if self.m_row == self.num_row:
					self.m_row = 0
				self.setCursor(self.m_col,self.m_row)

	# put string function
	def puts(self, string):
		for char in string:
			self.putc(char)

	# clear lcd and set to home
	def clear(self):
		self.lcd_write(0x1)
		sleep(0.001)	
	#	

	# add custom characters (0 - 7)
	def lcd_load_custom_chars(self, fontdata):
		self.lcd_device.bus.write(0x40);
		for char in fontdata:
			for line in char:
				self.lcd_write_char(line)
				
	def setCursor(self,col,row):
	
		row_offsets = [ 0x00, 0x40, 0x14, 0x54 ]
		self.m_col = col
		self.m_row = row
		self.lcd_write(0x80 | (col + row_offsets[row]))
			
class tmp102:
	def __init__(self, addr, port):
		self.sensor = i2c_device(addr, port)

	# read a register
	def read_reg(self, reg):
		return self.sensor.read_nbytes_data(reg, 2)

	# read the current temp in celsius
	def read_temp(self):
		tempraw = self.read_reg(0)
		return tempraw[0] + (tempraw[1] >> 4) * 0.0625

