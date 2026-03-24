"""Softimage PIC image decoder used by the XSI importer.

The format details are based on the documented Softimage PIC layout and
validated against the original Photoshop plugin bundled with the sample assets.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass


MAGIC_MIN = 0x5380F634
MAGIC_MAX = 0x5380F645
PICT_MAGIC = b"PICT"

TYPE_UNCOMPRESSED = 0x00
TYPE_PURE_RUN_LENGTH = 0x01
TYPE_MIXED_RUN_LENGTH = 0x02

CHANNEL_RED = 0x80
CHANNEL_GREEN = 0x40
CHANNEL_BLUE = 0x20
CHANNEL_ALPHA = 0x10


class SoftimagePICError(Exception):
	pass


@dataclass
class Channel:
	size: int
	channel_type: int
	channels: int

	@property
	def compression(self):
		return self.channel_type & 0x0F

	@property
	def offsets(self):
		offsets = []
		if self.channels & CHANNEL_RED:
			offsets.append(0)
		if self.channels & CHANNEL_GREEN:
			offsets.append(1)
		if self.channels & CHANNEL_BLUE:
			offsets.append(2)
		if self.channels & CHANNEL_ALPHA:
			offsets.append(3)
		return offsets


@dataclass
class SoftimagePICImage:
	width: int
	height: int
	has_alpha: bool
	pixels: bytearray


def _read_exact(f, size):
	data = f.read(size)
	if len(data) != size:
		raise SoftimagePICError("Unexpected end of file")
	return data


def _read_u8(f):
	return _read_exact(f, 1)[0]


def _read_u16_be(f):
	return struct.unpack(">H", _read_exact(f, 2))[0]


def _read_u32_be(f):
	return struct.unpack(">I", _read_exact(f, 4))[0]


def _decode_raw(f, pixels, row_start, width, stride, offsets):
	for x in range(width):
		base = row_start + x * stride
		for offset in offsets:
			pixels[base + offset] = _read_u8(f)


def _decode_pure_rle(f, pixels, row_start, width, stride, offsets):
	x = 0
	while x < width:
		count = min(_read_u8(f), width - x)
		values = [_read_u8(f) for _ in offsets]
		for _ in range(count):
			base = row_start + x * stride
			for offset, value in zip(offsets, values):
				pixels[base + offset] = value
			x += 1


def _decode_mixed_rle(f, pixels, row_start, width, stride, offsets):
	x = 0
	while x < width:
		count = _read_u8(f)
		if count >= 128:
			if count == 128:
				count = _read_u16_be(f)
			else:
				count -= 127
			if x + count > width:
				raise SoftimagePICError("Mixed RLE repeat overruns scanline")
			values = [_read_u8(f) for _ in offsets]
			for _ in range(count):
				base = row_start + x * stride
				for offset, value in zip(offsets, values):
					pixels[base + offset] = value
				x += 1
			continue

		count += 1
		if x + count > width:
			raise SoftimagePICError("Mixed RLE raw overruns scanline")
		for _ in range(count):
			base = row_start + x * stride
			for offset in offsets:
				pixels[base + offset] = _read_u8(f)
			x += 1


def read(filepath):
	with open(filepath, "rb") as f:
		magic = _read_u32_be(f)
		if not MAGIC_MIN <= magic <= MAGIC_MAX:
			raise SoftimagePICError("Invalid Softimage PIC magic")

		# Version is present but unused here.
		_read_exact(f, 4)
		_read_exact(f, 80)

		if _read_exact(f, 4) != PICT_MAGIC:
			raise SoftimagePICError("Missing PICT section")

		width = _read_u16_be(f)
		height = _read_u16_be(f)
		_read_exact(f, 4)  # aspect ratio
		_read_exact(f, 2)  # fields
		_read_exact(f, 2)  # padding

		channels = []
		has_alpha = False
		while True:
			chained = _read_u8(f)
			channel = Channel(
				size=_read_u8(f),
				channel_type=_read_u8(f),
				channels=_read_u8(f),
			)
			channels.append(channel)
			has_alpha = has_alpha or bool(channel.channels & CHANNEL_ALPHA)
			if not chained:
				break

		if width <= 0 or height <= 0:
			raise SoftimagePICError("Invalid image dimensions")

		stride = 4
		pixels = bytearray(width * height * stride)
		for index in range(3, len(pixels), stride):
			pixels[index] = 255

		for y in range(height - 1, -1, -1):
			row_start = y * width * stride
			for channel in channels:
				offsets = channel.offsets
				if not offsets:
					raise SoftimagePICError("Unsupported channel mask")
				if channel.size != 8:
					raise SoftimagePICError("Only 8-bit Softimage PIC channels are supported")

				if channel.compression == TYPE_UNCOMPRESSED:
					_decode_raw(f, pixels, row_start, width, stride, offsets)
				elif channel.compression == TYPE_PURE_RUN_LENGTH:
					_decode_pure_rle(f, pixels, row_start, width, stride, offsets)
				elif channel.compression == TYPE_MIXED_RUN_LENGTH:
					_decode_mixed_rle(f, pixels, row_start, width, stride, offsets)
				else:
					raise SoftimagePICError("Unsupported Softimage PIC compression type")

		return SoftimagePICImage(width=width, height=height, has_alpha=has_alpha, pixels=pixels)


def default_png_path(pic_filepath):
	root, _ = os.path.splitext(pic_filepath)
	return root + ".png"
