"""Decode BC4 / BC5 DDS textures (one and two channel, unsigned or signed) with numpy.

Blender's image loader returns an empty 0x0 image for these. BZCC / BZ2 Redux store every
normal map as BC5_SNORM ("BC5S"), so without this they cannot be shown.
decode_dds(path) -> float32 array (height, width, 4), top row first, values 0..1, or None when the
file is not BC4/BC5. BC5 normals get their Z rebuilt (z = sqrt(1 - x^2 - y^2)) into blue.
"""
import struct
import numpy as np

# fourcc / DXGI format -> (channels, signed)
FOURCC = {b"ATI1": (1, False), b"BC4U": (1, False), b"BC4S": (1, True),
          b"ATI2": (2, False), b"BC5U": (2, False), b"BC5S": (2, True)}
DXGI = {79: (1, False), 80: (1, False), 81: (1, True), 82: (2, False), 83: (2, False), 84: (2, True)}


def bcn_format(header):
	"""(channels, signed) for a BC4/BC5 DDS header, else None."""
	if len(header) < 128 or header[:4] != b"DDS ":
		return None
	fourcc = header[84:88]
	if fourcc == b"DX10":
		if len(header) < 148:
			return None
		return DXGI.get(struct.unpack("<I", header[128:132])[0])
	return FOURCC.get(fourcc)


def decode_bc4_blocks(blocks, signed):
	"""blocks: (n, 8) uint8 -> (n, 16) float32 in 0..1 (unsigned) or -1..1 (signed)."""
	if signed:
		e = blocks[:, :2].view(np.int8).astype(np.float32)
		e = np.maximum(e, -127.0) / 127.0
	else:
		e = blocks[:, :2].astype(np.float32) / 255.0
	r0, r1 = e[:, 0:1], e[:, 1:2]
	lo, hi = (-1.0, 1.0) if signed else (0.0, 1.0)
	t8 = np.arange(1, 7, dtype=np.float32) / 7.0
	t6 = np.arange(1, 5, dtype=np.float32) / 5.0
	pal8 = np.concatenate([r0, r1, r0 * (1 - t8) + r1 * t8], axis=1)
	pal6 = np.concatenate([r0, r1, r0 * (1 - t6) + r1 * t6,
	                       np.full_like(r0, lo), np.full_like(r0, hi)], axis=1)
	palette = np.where(r0 > r1, pal8, pal6)
	bits = np.zeros(len(blocks), dtype=np.uint64)
	for k in range(6):
		bits |= blocks[:, 2 + k].astype(np.uint64) << np.uint64(8 * k)
	idx = np.stack([(bits >> np.uint64(3 * i)) & np.uint64(7) for i in range(16)], axis=1).astype(np.intp)
	return np.take_along_axis(palette, idx, axis=1)


def decode_dds(path):
	with open(path, "rb") as f:
		data = f.read()
	fmt = bcn_format(data[:148])
	if fmt is None:
		return None
	channels, signed = fmt
	height, width = struct.unpack("<II", data[12:20])
	offset = 148 if data[84:88] == b"DX10" else 128
	bw, bh = max(1, (width + 3) // 4), max(1, (height + 3) // 4)
	block_size = 8 * channels
	count = bw * bh
	raw = np.frombuffer(data, dtype=np.uint8, count=count * block_size, offset=offset).reshape(count, block_size)
	planes = []
	for c in range(channels):
		v = decode_bc4_blocks(raw[:, 8 * c:8 * c + 8], signed)  # (count, 16), texel i = row i//4, col i%4
		v = v.reshape(bh, bw, 4, 4).transpose(0, 2, 1, 3).reshape(bh * 4, bw * 4)[:height, :width]
		planes.append(v)
	out = np.ones((height, width, 4), dtype=np.float32)
	if channels == 1:
		g = planes[0] * 0.5 + 0.5 if signed else planes[0]
		out[..., 0] = out[..., 1] = out[..., 2] = g
		return out
	x, y = planes
	if not signed:
		x, y = x * 2.0 - 1.0, y * 2.0 - 1.0
	z = np.sqrt(np.clip(1.0 - x * x - y * y, 0.0, 1.0))
	out[..., 0], out[..., 1], out[..., 2] = x * 0.5 + 0.5, y * 0.5 + 0.5, z * 0.5 + 0.5
	return out
