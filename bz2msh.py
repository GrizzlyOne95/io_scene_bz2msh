"""This module provides a parser and writer for BZ2 .msh files."""
VERSION = 1.11

import io
import json
import struct
from math import isfinite
from ctypes import sizeof, Structure, Array
from ctypes import c_ubyte, c_int32, c_uint16, c_uint32, c_uint16, c_float

MSH_END_OF_OPTIONALS = 0x9709513F
MSH_MATERIAL = 0x9709513E
MSH_TEXTURE = 0x7951FC0B
MSH_CHILD = 0xF74C51EE
MSH_SIBLING = 0xB8990880
MSH_END = 0xA93EB864
MSH_EOF = 0xE3BB47F1
MSH_SKINNED_SECTION = 0xF18F2BDE

# From "renderflags.txt"
DP_WAIT = 0x1
RS_NOVTXCHECK = 0x2
DP_DONOTCLIP = 0x4
DP_DONOTUPDATEEXTENTS = 0x8
DP_DONOTLIGHT = 0x10 # __e
RS_DRAWTEXT = 0x20
RS_NOALPHA = 0x40
RS_RESERVED1 = 0x80
RS_COLLIDABLE = 0x100 # __c
RS_2SIDED = 0x200 # __2
RS_HIDDEN = 0x400 # __h
RS_NOFOG = 0x800
RS_BLACKFOG = 0x1000
RS_NOSORT = 0x2000
RS_TEXMIRROR = 0x4000
RS_TEXCLAMP = 0x8000
RS_SRC_ZERO = 0x10000
RS_SRC_ONE = 0x20000
RS_SRC_SRCCOLOR = 0x30000
RS_SRC_INVSRCCOLOR = 0x40000
RS_SRC_SRCALPHA = 0x50000
RS_SRC_INVSRCALPHA = 0x60000
RS_SRC_DSTALPHA = 0x70000
RS_SRC_INVDSTALPHA = 0x80000
RS_SRC_DSTCOLOR = 0x90000
RS_SRC_INVDSTCOLOR = 0xa0000
RS_SRC_SRCALPHASAT = 0xb0000
RS_DST_ZERO = 0x100000
RS_DST_ONE = 0x200000 # __g (doesn't seem to work in BZCC)
RS_DST_SRCCOLOR = 0x300000
RS_DST_INVSRCCOLOR = 0x400000
RS_DST_SRCALPHA = 0x500000
RS_DST_INVSRCALPHA = 0x600000
RS_DST_DSTALPHA = 0x700000
RS_DST_INVDSTALPHA = 0x800000
RS_DST_DSTCOLOR = 0x900000
RS_DST_INVDSTCOLOR = 0xa00000
RS_DST_SRCALPHASAT = 0xb00000
RS_RESERVED2 = 0x1000000
RS_RESERVED3 = 0x2000000
RS_RESERVED4 = 0x4000000
RS_RESERVED5 = 0x8000000
RS_TEX_DECAL = 0x10000000
RS_TEX_MODULATE = 0x20000000
RS_TEX_DECALALPHA = 0x30000000
RS_TEX_MODULATEALPHA = 0x40000000
RS_TEX_DECALMASK = 0x50000000
RS_TEX_MODULATEMASK = 0x60000000
RS_TEX_ADD = 0x80000000
DP_MASK = 0x1d
RS_TEXBORDER = 0xc000
RS_NOZWRITE = 0x80000000
RS_SRC_MASK = 0xf0000
RS_DST_MASK = 0xf00000
RS_TEX_MASK = 0xf0000000
RS_BLEND_MASK = 0xf0ff0000
RS_BLEND_DEF = 0x40650000
RS_BLEND_GLOW = 0x40250000
RS_SRC_NONE = 0x0
RS_DST_NONE = 0x0
RS_BLEND_STENCIL_INC = 0x40000000
RS_BLEND_STENCIL_DEC = 0x40100000
RS_BLEND_STENCIL_USE = 0x40010000
RS_BLEND_NODRAW = 0x40210000

class ZeroLengthName(Exception): pass
class UnknownBlock(Exception): pass
class InvalidFormat(Exception): pass

def peek_u32(f):
	value = c_uint32()
	start = f.tell()
	f.readinto(value)
	f.seek(start)
	return value.value

def make_identity_matrix():
	matrix = Matrix()
	for attr, values in (
		("right", (1.0, 0.0, 0.0, 0.0)),
		("up", (0.0, 1.0, 0.0, 0.0)),
		("front", (0.0, 0.0, 1.0, 0.0)),
		("posit", (0.0, 0.0, 0.0, 1.0)),
	):
		row = getattr(matrix, attr)
		for index, value in enumerate(values):
			row[index] = value
	return matrix

def looks_like_null_terminated_ascii(name_bytes):
	return (
		len(name_bytes) > 1
		and name_bytes.endswith(b"\0")
		and all(32 <= byte < 127 for byte in name_bytes[:-1])
	)

def looks_like_mesh_header(data, name_offset):
	if name_offset + sizeof(c_uint16) > len(data):
		return False
	
	name_length = int.from_bytes(data[name_offset:name_offset + 2], "little")
	if not (1 < name_length < 256):
		return False
	
	name_end = name_offset + 2 + name_length
	if name_end + 12 + sizeof(Matrix) > len(data):
		return False
	
	name_bytes = data[name_offset + 2:name_end]
	if not looks_like_null_terminated_ascii(name_bytes):
		return False
	
	is_single_geom = struct.unpack_from("<i", data, name_end + 4)[0]
	if is_single_geom not in (-1, 0, 1):
		return False
	
	matrix_values = struct.unpack_from("<16f", data, name_end + 12)
	return all(isfinite(value) and abs(value) < 1e20 for value in matrix_values)

def read_optional_blocks(f):
	block_type_check = c_uint32()
	
	material = None
	f.readinto(block_type_check)
	if block_type_check.value == MSH_MATERIAL:
		material = Material(f)
	else:
		f.seek(f.tell() - sizeof(c_uint32))
	
	texture = None
	f.readinto(block_type_check)
	if block_type_check.value == MSH_TEXTURE:
		texture = Texture(f)
	else:
		f.seek(f.tell() - sizeof(c_uint32))
	
	had_end_marker = False
	f.readinto(block_type_check)
	if block_type_check.value == MSH_END_OF_OPTIONALS:
		had_end_marker = True
	else:
		f.seek(f.tell() - sizeof(c_uint32))
	
	return material, texture, had_end_marker

# This class provides a function that returns a recursive JSON represenation of its data.
class StructureJSON(Structure):
	def json(self):
		json_handled_types = (int, str, float, list, tuple, bool)
		j = {}
		
		for field_name, field_type in self._fields_:
			field_value = getattr(self, field_name)
			
			if issubclass(field_type, __class__):
				# The field is an object of a class that inherits from this class
				field_value = field_value.json()
			
			elif type(field_value) in json_handled_types:
				pass # Primitives handled by python's JSON serializer
			
			elif type(field_value) in (bytes, bytearray):
				field_value = field_value.decode("ascii", "ignore")
			
			else:
				try:
					# Iterable (e.g. float or index array)
					field_value = [value for value in field_value]
				except TypeError:
					field_value = str(field_value)
			
			j[field_name] = field_value
		
		return j

class UVPair(StructureJSON):
	_fields_ = [
		("u", c_float),
		("v", c_float)
	]
	
	def __iter__(self):
		yield self.u
		yield self.v

class Vector(StructureJSON):
	_fields_ = [
		("x", c_float),
		("y", c_float),
		("z", c_float)
	]
	
	def __iter__(self):
		yield self.x
		yield self.y
		yield self.z

class Vertex(StructureJSON):
	_fields_ = [
		("pos", Vector),
		("norm", Vector),
		("uv", UVPair)
	]

class ColorValue(StructureJSON):
	_fields_ = [
		("r", c_float),
		("g", c_float),
		("b", c_float),
		("a", c_float)
	]
	
	def __iter__(self):
		yield self.r
		yield self.g
		yield self.b
		yield self.a

class Color(StructureJSON):
	_fields_ = [
		("b", c_ubyte),
		("g", c_ubyte),
		("r", c_ubyte),
		("a", c_ubyte)
	]
	
	def __iter__(self):
		yield self.b
		yield self.g
		yield self.r
		yield self.a

class Matrix(StructureJSON):
	_fields_ = [
		("right", c_float * 4),
		("up", c_float * 4),
		("front", c_float * 4),
		("posit", c_float * 4)
	]
	
	def __iter__(self):
		yield [f for f in self.right]
		yield [f for f in self.up]
		yield [f for f in self.front]
		yield [f for f in self.posit]

class Quaternion(StructureJSON):
	_fields_ = [
		("s", c_float),
		("x", c_float),
		("y", c_float),
		("z", c_float)
	]
	
	def __iter__(self):
		yield s
		yield x
		yield y
		yield z

class AnimKey(StructureJSON):
	_fields_ = [
		("frame", c_float),
		("type", c_uint32),
		("quat", Quaternion),
		("vect", Vector)
	]

class BlockHeader(StructureJSON):
	_fields_ = [
		("fileType", c_ubyte * 4),
		("verID", c_uint32),
		("blockCount", c_uint32),
		("notUsed", c_ubyte * 32)
	]

class BlockInfo(StructureJSON):
	_fields_ = [
		("key", c_uint32),
		("size", c_uint32)
	]

class Sphere(StructureJSON):
	_fields_ = [
		("radius", c_float),
		("matrix", Matrix),
		("Width", c_float),
		("Height", c_float),
		("Breadth", c_float)
	]

class MSH_Header(StructureJSON):
	_fields_ = [
		("dummy", c_float),
		("scale", c_float),
		("indexed", c_uint32),
		("moveAnim", c_uint32),
		("oldPipe", c_uint32),
		("isSingleGeometry", c_uint32),
		("skinned", c_uint32)
	]

class FaceObj(StructureJSON):
	_fields_ = [
		("buckyIndex", c_uint16),
		("verts", c_uint16 * 3),
		("norms", c_uint16 * 3),
		("uvs", c_uint16 * 3)
	]

class VertIndex(StructureJSON):
	_fields_ = [
		("weight", c_float),
		("index", c_uint16),
	]

class VertIndexContainer:
	def __init__(self, count, array):
		self.count = count
		self.array = array
	
	def json(self):
		return {
			"count": self.count,
			"array": [item.json() for item in self.array],
		}

class Plane(StructureJSON):
	_fields_ = [
		("d", c_float),
		("x", c_float),
		("y", c_float),
		("z", c_float)
	]
	
	def __iter__(self):
		yield d
		yield x
		yield y
		yield z

class BuckyDesc:
	def __init__(self, f=None):
		self.flags = c_uint32()
		self.vert_count = c_uint32()
		self.index_count = c_uint32()
		
		self.material = None
		self.texture = None
		self.end_marker = False
		
		if f:
			self.read(f)
	
	def read(self, f):
		f.readinto(self.flags)
		f.readinto(self.index_count)
		f.readinto(self.vert_count)
		self.material, self.texture, self.end_marker = read_optional_blocks(f)
	
	def json(self):
		j = {
			"flags": self.flags.value,
			"indexCount": self.vert_count.value,
			"vertCount": self.index_count.value
		}
		
		if self.material:
			j["matBlock"] = self.material.json()
		
		if self.texture:
			j["matTexture"] = self.texture.json()
		
		return j

class VertGroup:
	def __init__(self, f=None):
		self.state_index = c_uint32()
		self.vert_count = c_uint32()
		self.index_count = c_uint32()
		self.plane_index = c_uint32()
		
		self.material = None
		self.texture = None
		self.end_marker = False
		
		if f:
			self.read(f)
	
	def read(self, f):
		f.readinto(self.state_index)
		f.readinto(self.vert_count)
		f.readinto(self.index_count)
		f.readinto(self.plane_index)
		self.material, self.texture, self.end_marker = read_optional_blocks(f)
	
	def json(self):
		j = {
			"stateIndex": self.state_index.value,
			"vertCount": self.vert_count.value,
			"indexCount": self.index_count.value,
			"planeIndex": self.plane_index.value
		}
		
		if self.material:
			j["matBlock"] = self.material.json()
		
		if self.texture:
			j["matTexture"] = self.texture.json()
		
		return j

class Material:
	def __init__(self, f=None):
		# Default material names are generated with a CRC function
		# from diffuse, specular, etc inputs into an unsigned 32 bit integer,
		# which is then turned into a hex string appended to "mat".
		self.name = ""
		self.diffuse = ColorValue()
		self.specular = ColorValue()
		self.specular_power = c_float()
		self.emissive = ColorValue()
		self.ambient = ColorValue()
		
		if f:
			self.read(f)
	
	def read(self, f):
		name_length = c_uint16()
		f.readinto(name_length)
		self.name = f.read(name_length.value)[0:-1].decode("ascii", "ignore")
		f.readinto(self.diffuse)
		f.readinto(self.specular)
		f.readinto(self.specular_power)
		f.readinto(self.emissive)
		f.readinto(self.ambient)
	
	def json(self):
		return {
			"name": {
				"string": self.name,
				"length": len(self.name)+1,
			},
		
			"diffuse": self.diffuse.json(),
			"specular": self.specular.json(),
			"specularPower": self.specular_power.value,
			"emissive": self.emissive.json(),
			"ambient": self.ambient.json()
		}

class Texture:
	def __init__(self, f=None):
		self.name = ""
		self.texture_type = c_uint32()
		self.mipmaps = c_uint32()
		
		if f:
			self.read(f)
	
	def read(self, f):
		name_length = c_uint16()
		f.readinto(name_length)
		self.name = f.read(name_length.value)[0:-1].decode("ascii", "ignore")
		f.readinto(self.texture_type)
		f.readinto(self.mipmaps)
	
	def json(self):
		return {
			"name": {
				"string": self.name,
				"length": len(self.name)+1,
			},
			
			"mipMapCount": self.mipmaps.value,
			"type": self.texture_type.value
		}

class Anim:
	def __init__(self, f=None):
		self.index = c_uint32()
		self.max_frame = c_float()
		self.states = []
		
		if f:
			self.read(f)
	
	def read(self, f):
		f.readinto(self.index)
		f.readinto(self.max_frame)
		
		count = c_uint32()
		f.readinto(count)
		self.states = (AnimKey * count.value)()
		f.readinto(self.states)
	
	def json(self):
		return {
			"index": self.index.value,
			"maxFrame": self.max_frame.value,
			"keys": [state.json() for state in self.states]
		}

class AnimList:
	def __init__(self, f=None):
		self.name = ""
		self.anim_type = c_uint32()
		self.max_frame = c_float()
		self.end_frame = c_float()
		
		self.states = []
		self.animations = []
		
		if f:
			self.read(f)
	
	def read(self, f):
		count = c_uint32()
		name_length = c_uint16()
		f.readinto(name_length)
		self.name = f.read(name_length.value)[0:-1].decode("ascii", "ignore")
		
		f.readinto(self.anim_type)
		f.readinto(self.max_frame)
		f.readinto(self.end_frame)
		
		f.readinto(count)
		self.states = (AnimKey * count.value)()
		f.readinto(self.states)
		
		f.readinto(count)
		self.animations = []
		for animation_index in range(count.value):
			self.animations += [Anim(f)]
	
	def json(self):
		return {
			"name": {
				"string": self.name,
				"length": len(self.name)+1,
			},
			
			"type": self.anim_type.value,
			"maxFrame": self.max_frame.value,
			"endFrame": self.end_frame.value,
			
			"animations": [animation.json() for animation in self.animations],
			"states": [animkey.json() for animkey in self.states]
		}

class SkinnedSection:
	def __init__(self, f=None, start_offset=0):
		self.start_offset = start_offset
		self.marker = MSH_SKINNED_SECTION
		self.vertex_count = 0
		self.face_count = 0
		self.normal_count = 0
		self.uv_count = 0
		self.extra_count = 0
		self.hierarchy_offset = 0
		self.hierarchy_marker = 0
		
		if f:
			self.read(f)
	
	def read(self, f):
		fields = [c_uint32() for _ in range(6)]
		for field in fields:
			f.readinto(field)
		self.marker = fields[0].value
		self.vertex_count = fields[1].value
		self.face_count = fields[2].value
		self.normal_count = fields[3].value
		self.uv_count = fields[4].value
		self.extra_count = fields[5].value
	
	def json(self):
		return {
			"startOffset": self.start_offset,
			"marker": self.marker,
			"vertexCount": self.vertex_count,
			"faceCount": self.face_count,
			"normalCount": self.normal_count,
			"uvCount": self.uv_count,
			"extraCount": self.extra_count,
			"hierarchyOffset": self.hierarchy_offset,
			"hierarchyMarker": self.hierarchy_marker,
		}

class Mesh:
	def __init__(self, f, block, level=0):
		self.block = block
		
		self.name = ""
		self.state_index = c_uint32()
		self.is_single_geom = c_int32()
		self.renderflags = c_uint32()
		self.matrix = Matrix()
		
		self.vert_colors = (Color * 0)()
		self.planes = (Plane * 0)()
		self.vertex = (Vertex * 0)()
		self.vert_groups = []
		self.indices = (c_uint16 * 0)()
		self.alt_vertices = (Vertex * 0)()
		self.alt_unknown = (0.0, 0.0, 0.0)
		self.alt_tail = []
		
		self.child = None
		self.sibling = None
		self.partial = False
		
		# Used to hierarchize like an XSI
		self.meshes = []
		self.level = level
		
		if f:
			self.read(f)
	
	def read(self, f):
		count = c_uint32()
		name_length = c_uint16()
		
		f.readinto(name_length)
		self.name = f.read(name_length.value)[0:-1].decode("ascii", "ignore")
		
		if len(self.name) <= 0:
			raise ZeroLengthName()
		
		f.readinto(self.state_index)
		f.readinto(self.is_single_geom)
		f.readinto(self.renderflags)
		f.readinto(self.matrix)
		
		f.readinto(count)
		self.vert_colors = (Color * count.value)()
		f.readinto(self.vert_colors)
		
		f.readinto(count)
		self.planes = (Plane * count.value)()
		f.readinto(self.planes)
		
		f.readinto(count)
		self.vertex = (Vertex * count.value)()
		f.readinto(self.vertex)
		
		f.readinto(count)
		self.vert_groups = []
		for i in range(count.value):
			self.vert_groups += [VertGroup(f)]
		
		f.readinto(count)
		self.indices = (c_uint16 * count.value)()
		f.readinto(self.indices)
	
	def walk(self, indentation_level=1):
		for mesh in self.meshes:
			yield mesh, indentation_level
			yield from mesh.walk(indentation_level+1)
	
	def json(self):
		j = {
			"name": {
				"string": self.name,
				"length": len(self.name)+1
			},
			
			"isSingleGeometry": self.is_single_geom.value,
			"renderFlags": self.renderflags.value,
			"stateIndex": self.state_index.value,
			"objectMatrix": self.matrix.json(),
			
			"localColors": [color.json() for color in self.vert_colors],
			"localGroups": [group.json() for group in self.vert_groups],
			"localIndices": [index for index in self.indices],
			"localPlanes": [plane.json() for plane in self.planes],
			"localVertex": [vertex.json() for vertex in self.vertex]
		}
		
		if self.alt_vertices:
			j["altLocalVertex"] = [vertex.json() for vertex in self.alt_vertices]
			j["altUnknown"] = list(self.alt_unknown)
		
		if self.alt_tail:
			j["altTail"] = list(self.alt_tail)
		
		if self.child:
			j["child"] = self.child.json()
		
		if self.sibling:
			j["siblings"] = [self.sibling.json()]
		
		if self.partial:
			j["partialRead"] = True
		
		return j

def find_next_mesh_marker(f, block_end):
	start = f.tell()
	if start >= block_end:
		return None
	
	data = f.read(block_end - start)
	f.seek(start)
	candidates = []
	
	for marker in (MSH_CHILD, MSH_SIBLING):
		marker_bytes = marker.to_bytes(4, "little")
		offset = data.find(marker_bytes)
		while offset >= 0:
			name_offset = offset + 4
			if name_offset + sizeof(c_uint16) <= len(data):
				if looks_like_mesh_header(data, name_offset):
					cursor = f.tell()
					valid = True
					try:
						f.seek(start + name_offset)
						Mesh(f, None, 0)
						valid = f.tell() <= block_end
					except Exception:
						pass
					finally:
						f.seek(cursor)
					if valid:
						candidates += [(start + offset, marker)]
			offset = data.find(marker_bytes, offset + 1)
	
	if not candidates:
		return None
	return min(candidates, key=lambda item: item[0])

def read_mesh_or_placeholder(f, block, level, block_end):
	start = f.tell()
	try:
		return Mesh(f, block, level)
	except Exception as original_error:
		f.seek(start)
		alt_mesh = read_alternate_mesh(f, block, level, block_end)
		if alt_mesh:
			return alt_mesh
		
		f.seek(start)
		name_length = c_uint16()
		f.readinto(name_length)
		name_bytes = f.read(name_length.value)
		if not looks_like_null_terminated_ascii(name_bytes):
			raise original_error
		
		placeholder = Mesh(None, block, level)
		placeholder.partial = True
		placeholder.name = name_bytes[:-1].decode("ascii", "ignore")
		f.readinto(placeholder.state_index)
		f.readinto(placeholder.is_single_geom)
		f.readinto(placeholder.renderflags)
		f.readinto(placeholder.matrix)
		
		next_marker = find_next_mesh_marker(f, block_end)
		if next_marker:
			f.seek(next_marker[0])
		else:
			f.seek(block_end - sizeof(c_uint32))
		return placeholder

def plane_coefficients(plane):
	# Plane records in these meshes are stored as x, y, z, d in file order.
	return plane.d, plane.x, plane.y, plane.z

def dot3(a, b):
	return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]

def sub3(a, b):
	return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

def cross3(a, b):
	return (
		a[1]*b[2] - a[2]*b[1],
		a[2]*b[0] - a[0]*b[2],
		a[0]*b[1] - a[1]*b[0],
	)

def normalize3(v):
	length = (v[0]*v[0] + v[1]*v[1] + v[2]*v[2]) ** 0.5
	if length <= 1e-12:
		return (0.0, 0.0, 1.0)
	return (v[0] / length, v[1] / length, v[2] / length)

def unique_vertex_indices(indices, positions, tolerance=1e-6):
	unique = []
	for index in indices:
		position = positions[index]
		if not any(all(abs(a - b) <= tolerance for a, b in zip(position, positions[other])) for other in unique):
			unique += [index]
	return unique

def triangulate_plane_vertices(indices, positions, normal):
	if len(indices) < 3:
		return []
	if len(indices) == 3:
		return [tuple(indices)]
	
	centroid = (
		sum(positions[index][0] for index in indices) / len(indices),
		sum(positions[index][1] for index in indices) / len(indices),
		sum(positions[index][2] for index in indices) / len(indices),
	)
	
	if abs(normal[0]) < 0.9:
		tangent = normalize3(cross3(normal, (1.0, 0.0, 0.0)))
	else:
		tangent = normalize3(cross3(normal, (0.0, 1.0, 0.0)))
	bitangent = cross3(normal, tangent)
	
	ordered = sorted(
		indices,
		key=lambda index: __import__("math").atan2(
			dot3(sub3(positions[index], centroid), bitangent),
			dot3(sub3(positions[index], centroid), tangent),
		),
	)
	
	return [(ordered[0], ordered[i], ordered[i + 1]) for i in range(1, len(ordered) - 1)]

def reconstruct_indices_from_planes(mesh, tolerance=1e-5):
	positions = [(vertex.pos.x, vertex.pos.y, vertex.pos.z) for vertex in mesh.vertex]
	triangles = []
	seen = set()
	
	for plane in mesh.planes:
		nx, ny, nz, d = plane_coefficients(plane)
		candidate_indices = []
		for index, position in enumerate(positions):
			distance = nx*position[0] + ny*position[1] + nz*position[2] + d
			if abs(distance) <= tolerance:
				candidate_indices += [index]
		
		candidate_indices = unique_vertex_indices(candidate_indices, positions)
		for triangle in triangulate_plane_vertices(candidate_indices, positions, normalize3((nx, ny, nz))):
			key = tuple(sorted(triangle))
			if key not in seen:
				seen.add(key)
				triangles += [triangle]
	
	if not triangles:
		return False
	
	flat_indices = []
	for triangle in triangles:
		flat_indices += list(triangle)
	mesh.indices = (c_uint16 * len(flat_indices))(*flat_indices)
	if mesh.vert_groups:
		mesh.vert_groups[0].index_count = c_uint32(len(flat_indices))
	return True

def finish_alternate_mesh(f, mesh, block_end):
	count = c_uint32()
	f.readinto(count)
	mesh.vert_groups = []
	for _ in range(count.value):
		mesh.vert_groups += [VertGroup(f)]
	
	expected_indices = sum(group.index_count.value for group in mesh.vert_groups)
	mesh.indices = (c_uint16 * 0)()
	mesh.alt_tail = []
	
	while f.tell() + sizeof(c_uint32) <= block_end:
		next_word = peek_u32(f)
		if next_word in (MSH_CHILD, MSH_SIBLING, MSH_END, MSH_EOF):
			break
		if expected_indices and next_word == expected_indices:
			f.readinto(count)
			mesh.indices = (c_uint16 * count.value)()
			f.readinto(mesh.indices)
			break
		
		tail_word = c_uint32()
		f.readinto(tail_word)
		mesh.alt_tail += [tail_word.value]
		if len(mesh.alt_tail) > 8:
			return None
	
	if len(mesh.indices) == 0 and expected_indices:
		reconstruct_indices_from_planes(mesh)
	
	mesh.partial = len(mesh.indices) == 0 and expected_indices > 0
	return mesh

def read_alternate_mesh_variant_1(f, block, level, block_end):
	start = f.tell()
	try:
		mesh = Mesh(None, block, level)
		name_length = c_uint16()
		f.readinto(name_length)
		name_bytes = f.read(name_length.value)
		if not looks_like_null_terminated_ascii(name_bytes):
			return None
		
		mesh.name = name_bytes[:-1].decode("ascii", "ignore")
		f.readinto(mesh.state_index)
		f.readinto(mesh.is_single_geom)
		f.readinto(mesh.renderflags)
		f.readinto(mesh.matrix)
		
		count = c_uint32()
		f.readinto(count)
		if count.value <= 0 or f.tell() + (count.value * sizeof(Vertex)) > block_end:
			return None
		mesh.alt_vertices = (Vertex * count.value)()
		f.readinto(mesh.alt_vertices)
		
		alt_unknown = (c_float * 3)()
		f.readinto(alt_unknown)
		mesh.alt_unknown = tuple(alt_unknown)
		
		f.readinto(count)
		if f.tell() + (count.value * sizeof(Plane)) > block_end:
			return None
		mesh.planes = (Plane * count.value)()
		f.readinto(mesh.planes)
		
		f.readinto(count)
		if count.value <= 0 or f.tell() + (count.value * sizeof(Vertex)) > block_end:
			return None
		mesh.vertex = (Vertex * count.value)()
		f.readinto(mesh.vertex)
		
		return finish_alternate_mesh(f, mesh, block_end)
	except Exception:
		f.seek(start)
		return None

def read_alternate_mesh_variant_2(f, block, level, block_end):
	start = f.tell()
	try:
		mesh = Mesh(None, block, level)
		name_length = c_uint16()
		f.readinto(name_length)
		name_bytes = f.read(name_length.value)
		if not looks_like_null_terminated_ascii(name_bytes):
			return None
		
		mesh.name = name_bytes[:-1].decode("ascii", "ignore")
		f.readinto(mesh.state_index)
		f.readinto(mesh.is_single_geom)
		f.readinto(mesh.renderflags)
		f.readinto(mesh.matrix)
		
		count = c_uint32()
		f.readinto(count)
		if count.value <= 0 or f.tell() + (count.value * sizeof(Vertex)) > block_end:
			return None
		mesh.alt_vertices = (Vertex * count.value)()
		f.readinto(mesh.alt_vertices)
		
		alt_unknown = (c_float * 2)()
		f.readinto(alt_unknown)
		mesh.alt_unknown = tuple(alt_unknown)
		
		f.readinto(count)
		if count.value <= 0 or f.tell() + (count.value * sizeof(Color)) > block_end:
			return None
		mesh.vert_colors = (Color * count.value)()
		f.readinto(mesh.vert_colors)
		
		f.readinto(count)
		if f.tell() + (count.value * sizeof(Plane)) > block_end:
			return None
		mesh.planes = (Plane * count.value)()
		f.readinto(mesh.planes)
		
		f.readinto(count)
		if count.value <= 0 or f.tell() + (count.value * sizeof(Vertex)) > block_end:
			return None
		mesh.vertex = (Vertex * count.value)()
		f.readinto(mesh.vertex)
		
		return finish_alternate_mesh(f, mesh, block_end)
	except Exception:
		f.seek(start)
		return None

def read_alternate_mesh(f, block, level, block_end):
	start = f.tell()
	for reader in (read_alternate_mesh_variant_1, read_alternate_mesh_variant_2):
		f.seek(start)
		mesh = reader(f, block, level, block_end)
		if mesh:
			return mesh
	f.seek(start)
	return None

class Block:
	def __init__(self, f, msh):
		self.msh = msh
		
		self.block_info = BlockInfo()
		self.sphere = Sphere()
		self.msh_header = MSH_Header()
		self.name = ""
		
		self.vertices = (Vector * 0)()
		self.vertex_normals = (Vector * 0)()
		self.uvs = (UVPair * 0)()
		self.vert_colors = (Color * 0)()
		self.faces = (FaceObj * 0)()
		self.buckydescriptions = []
		self.vert_to_state = []
		self.vert_groups = []
		self.indices = (c_uint16 * 0)()
		self.planes = (Plane * 0)()
		self.state_matrices = (Matrix * 0)()
		self.states = (AnimKey * 0)()
		self.anim_list = []
		self.root = None
		self.skinned_section = None
		self.synthetic_root = False
		
		if f:
			self.read(f)
	
	def read(self, f):
		f.readinto(self.block_info)
		block_end = f.tell() + self.block_info.size
		
		count = c_uint32()
		block_type = c_uint32()
		name_length = c_uint16()
		f.readinto(name_length)
		self.name = f.read(name_length.value)[0:-1].decode("ascii", "ignore")
		f.readinto(self.sphere)
		f.readinto(self.msh_header)
		
		f.readinto(count)
		self.vertices = (Vector * count.value)()
		f.readinto(self.vertices)
		
		f.readinto(count)
		self.vertex_normals = (Vector * count.value)()
		f.readinto(self.vertex_normals)
		
		f.readinto(count)
		self.uvs = (UVPair * count.value)()
		f.readinto(self.uvs)
		
		f.readinto(count)
		self.vert_colors = (Color * count.value)()
		f.readinto(self.vert_colors)
		
		f.readinto(count)
		self.faces = (FaceObj * count.value)()
		f.readinto(self.faces)
		
		f.readinto(count)
		for index in range(count.value):
			self.buckydescriptions += [BuckyDesc(f)]
		
		f.readinto(count)
		self.vert_to_state = []
		array_count = c_uint32()
		for index in range(count.value):
			f.readinto(array_count)
			array = []
			for count_index in range(array_count.value):
				# f.readinto() for VertIndex causes 8 byte read.
				weight = c_float()
				vertex_index = c_uint16()
				f.readinto(weight)
				f.readinto(vertex_index)
				array += [VertIndex(weight, vertex_index)]
			
			self.vert_to_state += [VertIndexContainer(array_count.value, array)]
		
		f.readinto(count)
		self.vert_groups = []
		for i in range(count.value):
			self.vert_groups += [VertGroup(f)]
		
		f.readinto(count)
		self.indices = (c_uint16 * count.value)()
		f.readinto(self.indices)
		
		f.readinto(count)
		self.planes = (Plane * count.value)()
		f.readinto(self.planes)
		
		f.readinto(count)
		self.state_matrices = (Matrix * count.value)()
		f.readinto(self.state_matrices)
		
		f.readinto(count)
		self.states = (AnimKey * count.value)()
		f.readinto(self.states)
		
		f.readinto(count)
		self.animation_list = []
		for animlist_index in range(count.value):
			self.animation_list += [AnimList(f)]
		
		if peek_u32(f) == MSH_SKINNED_SECTION:
			self.skinned_section = SkinnedSection(f, f.tell())
			hierarchy_info = find_next_mesh_marker(f, block_end)
			if not hierarchy_info:
				raise UnknownBlock("Unhandled skinned mesh payload with no recoverable hierarchy.")
			hierarchy_offset, hierarchy_marker = hierarchy_info
			self.skinned_section.hierarchy_offset = hierarchy_offset
			self.skinned_section.hierarchy_marker = hierarchy_marker
			f.seek(hierarchy_offset)
			
			self.root = Mesh(None, self, 0)
			self.root.name = self.name or "skinned_root"
			self.root.matrix = make_identity_matrix()
			self.synthetic_root = True
		else:
			self.root = read_mesh_or_placeholder(f, self, 0, block_end)
		
		self.meshes = [self.root]
		indentation_level = 0 # 0 is root level
		mesh_at = [self.root]
		
		while True:
			while f.tell() + sizeof(c_uint32) <= block_end and peek_u32(f) == 0:
				f.seek(sizeof(c_uint32), io.SEEK_CUR)
			
			f.readinto(block_type)
			if block_type.value == MSH_CHILD:
				this_mesh = read_mesh_or_placeholder(f, self, indentation_level + 1, block_end)
				if mesh_at[indentation_level].child is None:
					mesh_at[indentation_level].child = this_mesh
				mesh_at[indentation_level].meshes += [this_mesh]
				
				indentation_level += 1
				
				if len(mesh_at) < indentation_level+1:
					mesh_at += [this_mesh]
				else:
					mesh_at[indentation_level] = this_mesh
			
			elif block_type.value == MSH_SIBLING:
				if indentation_level <= 0:
					parent_level = 0
					this_level = 1 if self.synthetic_root else 0
					previous = mesh_at[1] if self.synthetic_root and len(mesh_at) > 1 else mesh_at[0]
				else:
					parent_level = indentation_level - 1
					this_level = indentation_level
					previous = mesh_at[indentation_level]
				
				this_mesh = read_mesh_or_placeholder(f, self, this_level, block_end)
				if previous:
					previous.sibling = this_mesh
				mesh_at[parent_level].meshes += [this_mesh]
				
				if len(mesh_at) < this_level + 1:
					mesh_at += [this_mesh]
				else:
					mesh_at[this_level] = this_mesh
				indentation_level = this_level
			
			elif block_type.value == MSH_END:
				if indentation_level > 0:
					indentation_level -= 1
			
			elif block_type.value == MSH_EOF:
				break
			
			else:
				raise UnknownBlock("Unhandled Mesh Block %s - Note that oldpoop is not supported." % hex(block_type.value))
	
	def walk(self):
		if self.root:
			yield self.root, 0 # 0 indentation level
			yield from self.root.walk()
	
	def json(self):
		j = {
			"name": {
				"string": self.name,
				"length": len(self.name)+1
			},
			
			"bigSphere": self.sphere.json(),
			"blockInfo": self.block_info.json(),
			
			"vertices": [vertex.json() for vertex in self.vertices],
			"normals": [nomral.json() for nomral in self.vertex_normals],
			"uvs": [uv.json() for uv in self.uvs],
			"colors": [color.json() for color in self.vert_colors],
			"faces": [face.json() for face in self.faces],
			"buckys": [bucky.json() for bucky in self.buckydescriptions],
			"vertToState": [vts.json() for vts in self.vert_to_state],
			"groups": [vg.json() for vg in self.vert_groups],
			"indices": [index for index in self.indices],
			"planes": [plane.json() for plane in self.planes],
			"stateMats": [state_mat.json() for state_mat in self.state_matrices],
			"States": [state.json() for state in self.states],
			"animList": [al.json() for al in self.animation_list],
			
			"mesh": self.root.json()
		}
		
		if self.skinned_section:
			j["skinnedSection"] = self.skinned_section.json()
		
		j.update(self.msh_header.json())
		
		return j

class MSH:
	def __init__(self, file_path):
		self.block_header = BlockHeader()
		self.blocks = []
		
		with open(file_path, "rb") as f:
			self.read(f)
	
	def read(self, f):
		"""Read from MSH open in binary read mode."""
		f.readinto(self.block_header)
		
		for block_index in range(self.block_header.blockCount):
			self.blocks += [Block(f, self)]
	
	def write(self, f):
		"""Write MSH to file open in binary write mode, write to a file path or writable object."""
		DISABLE_END_OF_OPTIONALS = True # Prevent older .msh parsers from crashing (e.g. OMDL1 viewer)
		
		locally_opened = False
		if not hasattr(f, "write"):
			f = open(f, "wb")
			locally_opened = True
		
		def write_name(f, name):
			written_name = name.encode() + b"\0"
			f.write(c_uint16(len(written_name)))
			f.write(written_name)
		
		def write_optionals(f, optionals_container):
			if optionals_container.material:
				f.write(c_uint32(MSH_MATERIAL))
				write_name(f, optionals_container.material.name)
				f.write(optionals_container.material.diffuse)
				f.write(optionals_container.material.specular)
				f.write(optionals_container.material.specular_power)
				f.write(optionals_container.material.emissive)
				f.write(optionals_container.material.ambient)
			
			if optionals_container.texture:
				f.write(c_uint32(MSH_TEXTURE))
				write_name(f, optionals_container.texture.name)
				f.write(optionals_container.texture.texture_type)
				f.write(optionals_container.texture.mipmaps)
			
			if optionals_container.end_marker and not DISABLE_END_OF_OPTIONALS:
				f.write(c_uint32(MSH_END_OF_OPTIONALS))
		
		def write_vert_group(f, vert_group):
			f.write(vert_group.state_index)
			f.write(vert_group.vert_count)
			f.write(vert_group.index_count)
			f.write(vert_group.plane_index)
			write_optionals(f, vert_group)
		
		def write_mesh(f, mesh):
			write_name(f, mesh.name)
			f.write(mesh.state_index)
			f.write(mesh.is_single_geom)
			f.write(mesh.renderflags)
			f.write(mesh.matrix)
			f.write(c_uint32(len(mesh.vert_colors)))
			f.write(mesh.vert_colors)
			f.write(c_uint32(len(mesh.planes)))
			f.write(mesh.planes)
			f.write(c_uint32(len(mesh.vertex)))
			f.write(mesh.vertex)
			
			f.write(c_uint32(len(mesh.vert_groups)))
			for vert_group in mesh.vert_groups:
				write_vert_group(f, vert_group)
			
			f.write(c_uint32(len(mesh.indices)))
			f.write(mesh.indices)
			
			if mesh.child:
				f.write(c_uint32(MSH_CHILD))
				write_mesh(f, mesh.child)
			
			f.write(c_uint32(MSH_END))
			
			if mesh.sibling:
				f.write(c_uint32(MSH_SIBLING))
				write_mesh(f, mesh.sibling)
		
		self.block_header.blockCount = len(self.blocks)
		f.write(self.block_header)
		for block in self.blocks:
			f.write(block.block_info)
			write_name(f, block.name)
			f.write(block.sphere)
			f.write(block.msh_header)
			
			f.write(c_uint32(len(block.vertices)))
			f.write(block.vertices)
			f.write(c_uint32(len(block.vertex_normals)))
			f.write(block.vertex_normals)
			f.write(c_uint32(len(block.uvs)))
			f.write(block.uvs)
			f.write(c_uint32(len(block.vert_colors)))
			f.write(block.vert_colors)
			f.write(c_uint32(len(block.faces)))
			f.write(block.faces)
			
			f.write(c_uint32(len(block.buckydescriptions)))
			for bucky in block.buckydescriptions:
				f.write(bucky.flags)
				f.write(bucky.index_count)
				f.write(bucky.vert_count)
				write_optionals(f, bucky)
			
			f.write(c_uint32(len(block.vert_to_state)))
			for vts_container in block.vert_to_state:
				f.write(c_uint32(vts_container.count))
				for vts in vts_container.array:
					f.write(c_float(vts.weight))
					f.write(c_uint16(vts.index))
			
			f.write(c_uint32(len(block.vert_groups)))
			for vert_group in block.vert_groups:
				write_vert_group(f, vert_group)
			
			f.write(c_uint32(len(block.indices)))
			f.write(block.indices)
			f.write(c_uint32(len(block.planes)))
			f.write(block.planes)
			f.write(c_uint32(len(block.state_matrices)))
			f.write(block.state_matrices)
			f.write(c_uint32(len(block.states)))
			f.write(block.states)
			
			f.write(c_uint32(len(block.animation_list)))
			for al in block.animation_list:
				write_name(f, al.name)
				f.write(al.anim_type)
				f.write(al.max_frame)
				f.write(al.end_frame)
				f.write(c_uint32(len(al.states)))
				f.write(al.states)
				f.write(c_uint32(len(al.animations)))
				for a in al.animations:
					f.write(a.index)
					f.write(a.max_frame)
					f.write(c_uint32(len(a.states)))
					f.write(a.states)
			
			if block.root:
				write_mesh(f, block.root)
			
			f.write(c_uint32(MSH_EOF))
		
		if locally_opened:
			f.close()
	
	def walk(self):
		for block in self.blocks:
			yield from block.walk()
	
	def to_json(self, file_path, indent=None):
		with open(file_path, "w") as f:
			j = {
				"verID": self.block_header.verID,
				"blockCount": self.block_header.blockCount,
				"fileType": bytearray(self.block_header.fileType).decode("ascii", "ignore"),
				"notUsed": " ".join(["%02X" % x for x in self.block_header.notUsed])
			}
			
			j["meshRoot"] = [block.json() for block in self.blocks]
			
			# If you want improved performance in writing & parsing JSON data, do not sort keys or indent.
			f.write(json.dumps(j, sort_keys=bool(indent), indent=indent))

# Dump .msh data into humanly readable JSON file
if __name__ == "__main__":
	import sys, os
	for msh_file in sys.argv[1::]:
		msh = MSH(msh_file)
		json_file = os.path.join(os.path.dirname(msh_file), os.path.basename(msh_file) + ".json")
		if not os.path.exists(json_file):
			msh.to_json(json_file, "\t")
