import bpy
import re
import os
import ctypes
from types import SimpleNamespace
from ctypes import Structure, c_int, c_ubyte, c_uint32, c_uint
from struct import unpack
from mathutils import Matrix, Vector, Euler, Quaternion
from bpy_extras import image_utils
from math import radians
from . import bz2msh, softimage_pic, bcn

# Define types used by the binary headers
DWORD = c_uint32
DXGI_FORMAT = c_uint32
D3D10_RESOURCE_DIMENSION = c_uint32

class DXTBZ2Header(Structure):
	_fields_ = [
		("m_Sig", c_int),
		("m_DXTLevel", c_int),
		("m_1x1Red", c_ubyte),
		("m_1x1Green", c_ubyte),
		("m_1x1Blue", c_ubyte),
		("m_1x1Alpha", c_ubyte),
		("m_NumMips", c_int),
		("m_BaseHeight", c_int),
		("m_BaseWidth", c_int)
	]

class DDS_PIXELFORMAT(Structure):
	_fields_ = [
		("dwSize", DWORD),
		("dwFlags", DWORD),
		("dwFourCC", DWORD),
		("dwRGBBitCount", DWORD),
		("dwRBitMask", DWORD),
		("dwGBitMask", DWORD),
		("dwBBitMask", DWORD),
		("dwABitMask", DWORD)
	]

class DDS_HEADER(Structure):
	_fields_ = [
		("dwSize", DWORD),
		("dwFlags", DWORD),
		("dwHeight", DWORD),
		("dwWidth", DWORD),
		("dwPitchOrLinearSize", DWORD),
		("dwDepth", DWORD),
		("dwMipMapCount", DWORD),
		("dwReserved1", DWORD*11),
		("ddspf", DDS_PIXELFORMAT),
		("dwCaps", DWORD),
		("dwCaps2", DWORD),
		("dwCaps3", DWORD),
		("dwCaps4", DWORD),
		("dwReserved2", DWORD)
	]

class DDS_HEADER_DXT10(Structure):
	_fields_ = [
		("dxgiFormat", DXGI_FORMAT),
		("resourceDimension", D3D10_RESOURCE_DIMENSION),
		("miscFlag", c_uint),
		("arraySize", c_uint),
		("miscFlags2", c_uint)
	]

# Normals API logic for Blender 4.1+
OLD_NORMALS = not (bpy.app.version[0] >= 4 and bpy.app.version[1] >= 1)

PRINT_TEXTURE_FINDER_INFO = False
PRINT_LOCAL_MATERIAL_REUSE = False
PRINT_MSH_HEADER = True

NODE_NORMALMAP_STRENGTH = 1.0
NODE_EMISSIVE_STRENGTH = 1.0
NODE_DEFAULT_ROUGHNESS = 0.50

USE_RENDER_FLAGS = True
RENDER_FLAGS_RENAME = True 

NODE_SPACING_X, NODE_SPACING_Y = 600, 300
NODE_HEIGHT = {
	"diffuse": NODE_SPACING_Y,
	"specular": 0,
	"emissive": -NODE_SPACING_Y,
	"normal": -(NODE_SPACING_Y*2),
	"teamcolor": NODE_SPACING_Y*2
}

BZ2_TO_BLENDER = Matrix((
	(1.0, 0.0, 0.0, 0.0),
	(0.0, 0.0, 1.0, 0.0),
	(0.0, 1.0, 0.0, 0.0),
	(0.0, 0.0, 0.0, 1.0),
))
BZ2_TO_BLENDER_3 = BZ2_TO_BLENDER.to_3x3()

def find_texture(texture_filepath, search_directories, acceptable_extensions, recursive=False):
	acceptable_extensions = list(acceptable_extensions)
	file_name, original_extension = os.path.splitext(os.path.basename(texture_filepath))
	original_extension_compare = original_extension.lower()
	
	if os.path.exists(texture_filepath):
		return texture_filepath
	
	for ext in acceptable_extensions:
		for directory in search_directories:
			for root, folders, files in os.walk(directory):
				path = os.path.join(root, file_name + ext)
				if os.path.exists(path) and os.path.isfile(path):
					return path
				if not recursive:
					break
	return file_name + original_extension

def read_material_file(filepath, default_diffuse=None):
	"""Texture maps of a BZ2R/BZCC .material file ([texture] section).  Keys are lower case:
	diffuse, specular, normal, emissive and teamcolor (BZCC team colour mask)."""
	re_section = re.compile(r"(?i)\s*\[([^\]]*)\]")
	re_keyval = re.compile(r"(?i)\s*(\w+)\s*=\s*(.+)")
	textures = {"diffuse": default_diffuse, "specular": None, "normal": None, "emissive": None, "teamcolor": None}
	in_texture = False
	with open(filepath, "r") as f:
		for line in f:
			match = re_section.match(line)
			if match:
				if in_texture: break
				if match.group(1).lower() == "texture": in_texture = True
				continue
			if in_texture:
				match = re_keyval.match(line)
				if match:
					key, value = match.group(1).lower(), match.group(2).strip()
					if key in textures: textures[key] = value
	return textures

def verts_of_all_vertex_groups(mesh):
	index_start, vert_start = 0, 0
	for vgroup in mesh.vert_groups:
		index_end = index_start + vgroup.index_count.value
		for index in mesh.indices[index_start:index_end]:
			yield mesh.vertex[vert_start + index]
		vert_start += vgroup.vert_count.value
		index_start = index_end

def is_skinned(block):
	"""A skinned block carries one weight list per block vertex and bind matrices."""
	return bool(block.msh_header.skinned) and len(block.vertices) > 0 and len(block.faces) > 0 \
		and len(block.vert_to_state) == len(block.vertices) and len(block.state_matrices) > 0

def block_parents(block):
	parent = {}
	for mesh, _ in block.walk():
		for child in mesh.meshes:
			parent[child.state_index.value] = mesh.state_index.value
	return parent

def action_fcurves(action):
	"""All F-Curves of an Action (layered Actions in Blender 4.4+, legacy list before)."""
	layers = getattr(action, "layers", None)
	if layers:
		for layer in layers:
			for strip in layer.strips:
				for bag in getattr(strip, "channelbags", []):
					yield from bag.fcurves
	elif hasattr(action, "fcurves"):
		yield from action.fcurves

def key_has_position(key):
	return key.type in (1, 3)

def key_has_rotation(key):
	return key.type in (2, 3)

def key_rotation(key):
	"""Local rotation of an animation key: the stored quaternion is its conjugate
	(the rotation in row-vector form, like the file matrices)."""
	q = Quaternion((key.quat.s, key.quat.x, key.quat.y, key.quat.z))
	return Quaternion((1.0, 0.0, 0.0, 0.0)) if q.magnitude == 0.0 else q.normalized().conjugated()

def key_tracks(anim):
	"""An animation's key tracks, one per node index.  A few meshes store two tracks for one
	node index (all have two nodes of the same name, e.g. the BZ2R pilots' two "handl", so the
	exporter likely matched tracks by name).  Tracks apply in file order, so per channel the
	last track that keys it wins - the rule tests/check_skinned_import.py uses; interleaving
	their keys would give a pose neither track has."""
	by_index = {}
	for track in anim.animations:
		by_index.setdefault(getattr(track.index, "value", track.index), []).append(track)
	tracks = []
	for index, group in by_index.items():
		if len(group) == 1:
			tracks.append(group[0])
			continue
		states = []
		for key_type, has in ((1, key_has_position), (2, key_has_rotation)):
			last = next((t for t in reversed(group) if any(has(k) for k in t.states)), None)
			for k in (last.states if last else []):
				if has(k):
					copy = bz2msh.AnimKey.from_buffer_copy(k)
					copy.type = key_type
					states.append(copy)
		states.sort(key=lambda k: k.frame)
		tracks.append(SimpleNamespace(index=group[0].index, states=states))
	return tracks

def sample_vec(keys, f):
	if f <= keys[0][0]: return keys[0][1]
	for (f0, a), (f1, b) in zip(keys, keys[1:]):
		if f0 <= f <= f1:
			return a.lerp(b, 0.0 if f1 == f0 else (f - f0) / (f1 - f0))
	return keys[-1][1]

def sample_quat(keys, f):
	if f <= keys[0][0]: return keys[0][1]
	for (f0, a), (f1, b) in zip(keys, keys[1:]):
		if f0 <= f <= f1:
			return a.slerp(b, 0.0 if f1 == f0 else (f - f0) / (f1 - f0))
	return keys[-1][1]

def normalized(M):
	"""Drop scale/shear: bones and pose keys are rigid."""
	loc, rot, _ = M.decompose()
	return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()

class Load:
	def __init__(self, operator, context, filepath, as_collection, **opt):
		self.operator = operator
		self.context = context
		self.opt = opt
		self.filepath = filepath
		self.filefolder = os.path.dirname(filepath)
		
		# Define MSH data and tracking dictionaries
		self.msh = bz2msh.MSH(filepath)
		self.all_objects = {}
		self.objects_by_state_index = {}
		self.bpy_objects = []
		self.existing_materials = {}
		
		self.ext_list = self.opt["find_textures_ext"].casefold().split()
		self.tex_dir = self.context.preferences.filepaths.texture_directory
		self.texture_search_directories = [
			self.filefolder,
			os.path.join(self.filefolder, "bitmaps"),
			os.path.join(self.filefolder, "textures"),
		]
		if self.tex_dir:
			self.texture_search_directories.append(self.tex_dir)
		if self.opt.get("texture_search_root"):
			self.texture_search_directories.append(self.opt["texture_search_root"])
			self.texture_search_directories.append(os.path.join(self.opt["texture_search_root"], "bitmaps"))

		# Create Collection if requested
		if as_collection:
			self.collection = bpy.data.collections.new(os.path.basename(filepath))
			context.scene.collection.children.link(self.collection)
		else:
			self.collection = context.scene.collection

		# Hierarchy Root Tracking
		bpy_root_objects = []

		self.armatures = []  # (armature object, block, {state index: bone name}, {state index: raw bind})
		if opt["import_mode"] == "GLOBAL":
			mesh_data = self.create_global_mesh(self.msh.blocks[0])
			bpy_obj = self.create_object(self.msh.blocks[0].name, mesh_data, Matrix.Identity(4))
			bpy_root_objects.append(bpy_obj)
		else:
			for block in self.msh.blocks:
				if self.use_armature(block):
					bpy_root_objects.append(self.create_skinned(block))
				elif block.root:
					root_obj = self.walk(block.root)
					bpy_root_objects.append(root_obj)

		# Apply Global Animations after objects are mapped
		if opt.get("import_animations"):
			existing_actions = set(bpy.data.actions)
			self.apply_global_animations()
			for arm_obj, block, bone_names, bind_raw in self.armatures:
				self.apply_armature_animations(arm_obj, block, bone_names, bind_raw)
			# MSH keys interpolate linearly; Blender's default Bezier would ease between them
			for action in bpy.data.actions:
				if action not in existing_actions:
					for fcurve in action_fcurves(action):
						for point in fcurve.keyframe_points:
							point.interpolation = 'LINEAR'

		# Final Scene Placement
		for bpy_obj in bpy_root_objects:
			if self.opt["place_at_cursor"]:
				bpy_obj.location += context.scene.cursor.location

		for bpy_obj in self.bpy_objects:
			if bpy_obj.name not in self.collection.objects:
				self.collection.objects.link(bpy_obj)

	def dxtbz2_to_dds(self, filepath):
		"""Internal conversion of .dxtbz2 to standard .dds"""
		dds_path = os.path.splitext(filepath)[0] + ".dds"
		if os.path.exists(dds_path): return dds_path
		try:
			with open(filepath, "rb") as f_in:
				header, size = DXTBZ2Header(), c_uint32()
				f_in.readinto(header)
				f_in.readinto(size)
				if header.m_BaseHeight <= 0 or header.m_BaseWidth <= 0:
					return None
				has_alpha = size.value // header.m_BaseHeight == header.m_BaseHeight
				with open(dds_path, "wb") as f_out:
					dh = DDS_HEADER()
					dh.dwSize, dh.dwFlags = 124, 0x1|0x2|0x4|0x1000
					dh.dwHeight, dh.dwWidth = header.m_BaseHeight, header.m_BaseWidth
					dh.dwMipMapCount, dh.dwCaps = header.m_NumMips, 0x1000
					dh.ddspf.dwSize, dh.ddspf.dwFlags = 32, 0x4
					if has_alpha: dh.ddspf.dwFlags |= 0x1
					dh.ddspf.dwFourCC = unpack("I", b"DX10")[0]
					f_out.write(b"DDS ")
					f_out.write(dh)
					d10 = DDS_HEADER_DXT10()
					d10.dxgiFormat = 77 if has_alpha else 71
					d10.resourceDimension, d10.arraySize = 3, 1
					f_out.write(d10)
					f_out.write(f_in.read())
			return dds_path
		except: return None

	def get_existing_pic_image(self, pic_filepath):
		for image in bpy.data.images:
			if image.get("softimage_pic_source") == pic_filepath:
				return image
		return None

	def save_pic_as_png(self, bpy_image, pic_filepath):
		png_filepath = softimage_pic.default_png_path(pic_filepath)
		bpy_image.filepath_raw = png_filepath
		bpy_image.file_format = "PNG"
		bpy_image.save()
		return png_filepath

	def load_softimage_pic(self, pic_filepath):
		if self.opt["convert_pic_textures"]:
			png_filepath = softimage_pic.default_png_path(pic_filepath)
			if os.path.exists(png_filepath) and os.path.getmtime(png_filepath) >= os.path.getmtime(pic_filepath):
				bpy_image = image_utils.load_image(
					png_filepath,
					place_holder=False,
					check_existing=True
				)
				bpy_image["softimage_pic_source"] = pic_filepath
				bpy_image["softimage_pic_png"] = png_filepath
				bpy_image["softimage_pic_format"] = "Softimage PIC"
				return bpy_image

		existing = self.get_existing_pic_image(pic_filepath)
		if existing:
			return existing

		decoded = softimage_pic.read(pic_filepath)
		image_name = os.path.basename(pic_filepath)
		bpy_image = bpy.data.images.new(
			name=image_name,
			width=decoded.width,
			height=decoded.height,
			alpha=decoded.has_alpha
		)
		bpy_image.alpha_mode = "CHANNEL_PACKED"
		bpy_image.pixels.foreach_set([value / 255.0 for value in decoded.pixels])
		bpy_image["softimage_pic_source"] = pic_filepath
		bpy_image["softimage_pic_format"] = "Softimage PIC"

		if self.opt["convert_pic_textures"]:
			png_filepath = self.save_pic_as_png(bpy_image, pic_filepath)
			bpy.data.images.remove(bpy_image)
			bpy_image = image_utils.load_image(
				png_filepath,
				place_holder=False,
				check_existing=True
			)
			bpy_image["softimage_pic_source"] = pic_filepath
			bpy_image["softimage_pic_png"] = png_filepath
			bpy_image["softimage_pic_format"] = "Softimage PIC"

		return bpy_image

	def resolve_texture_path(self, image_filepath):
		resolved_path = find_texture(
			image_filepath,
			self.texture_search_directories,
			self.ext_list,
			self.opt["find_textures"]
		)
		if os.path.exists(resolved_path):
			return resolved_path

		if self.opt["find_textures"]:
			fallback = find_texture(
				image_filepath,
				self.texture_search_directories,
				self.ext_list,
				True
			)
			if os.path.exists(fallback):
				return fallback

		return resolved_path

	def load_texture_image(self, image_filepath):
		resolved_path = self.resolve_texture_path(image_filepath)
		extension = os.path.splitext(resolved_path)[1].casefold()

		if extension == ".dxtbz2" and os.path.exists(resolved_path) and self.opt["auto_convert_dxtbz2"]:
			dds_path = self.dxtbz2_to_dds(resolved_path)
			if dds_path and os.path.exists(dds_path):
				resolved_path = dds_path
				extension = ".dds"

		if extension == ".pic" and os.path.exists(resolved_path):
			return self.load_softimage_pic(resolved_path)

		image = image_utils.load_image(
			resolved_path,
			place_holder=True,
			check_existing=True
		)
		if extension == ".dds" and image is not None and not image.packed_file and tuple(image.size) == (0, 0) and os.path.exists(resolved_path):
			image = self.load_bcn_dds(resolved_path, image) or image
		return image

	def load_bcn_dds(self, dds_path, failed_image):
		"""BC4/BC5 DDS (BZCC normal maps are BC5_SNORM) load as an empty image in Blender:
		decode them here into a packed image, BC5 normals with Z rebuilt."""
		try:
			pixels = bcn.decode_dds(dds_path)
		except (OSError, ValueError) as e:
			print(f"BC4/BC5 decode failed for {dds_path}: {e}")
			return None
		if pixels is None:
			return None
		name = failed_image.name
		bpy.data.images.remove(failed_image)
		height, width = pixels.shape[:2]
		image = bpy.data.images.new(name, width, height, alpha=False, float_buffer=False)
		image.pixels.foreach_set(pixels[::-1].ravel())  # Blender rows run bottom-up
		image.pack()
		image["bcn_source"] = dds_path
		return image

	def walk(self, mesh, bpy_parent=None):
		bpy_obj = self.create_object(
			mesh.name,
			self.create_local_mesh(mesh),
			self.create_matrix(mesh.matrix),
			bpy_parent
		)
		self.all_objects[mesh.name] = bpy_obj
		self.objects_by_state_index[mesh.state_index.value] = bpy_obj
		
		# Process hierarchy
		for msh_sub_mesh in mesh.meshes:
			self.walk(msh_sub_mesh, bpy_obj)
		return bpy_obj

	def use_armature(self, block):
		return self.opt.get("import_skinned_armature", True) and self.opt["import_mode"] != "GLOBAL" and is_skinned(block)

	def apply_global_animations(self):
		"""Object-transform clips: one Action per clip with a slot per animated object.
		The first clip stays assigned; the others keep a fake user.
		A clip also keys the rest value of every channel it leaves unkeyed on objects that any
		clip animates (e.g. location when it keys only rotation), at its first frame, so
		switching clips never leaves a part in the previous clip's pose (the skinned path
		does the same with its bones)."""
		rest = {}
		for bpy_obj in self.objects_by_state_index.values():
			loc, rot, _ = bpy_obj.matrix_basis.decompose()
			rest[bpy_obj.name] = (loc.copy(), rot.copy())
		first = {}
		clips = []
		for block in self.msh.blocks:
			if self.use_armature(block):
				continue
			for anim in getattr(block, "animation_list", []):
				action = bpy.data.actions.new(name=f"{block.name}|{anim.name}")
				action.use_fake_user = True
				keyed, start = {}, None
				for sub_anim in key_tracks(anim):
					bpy_obj = self.find_node_by_index(sub_anim.index)
					if bpy_obj:
						self.apply_keyframes_to_object(bpy_obj, sub_anim, action)
						first.setdefault(bpy_obj.name, (bpy_obj, action))
						kinds = keyed.setdefault(bpy_obj.name, set())
						for state in sub_anim.states:
							if key_has_position(state): kinds.add("location")
							if key_has_rotation(state): kinds.add("rotation_quaternion")
							start = state.frame if start is None else min(start, state.frame)
				clips.append((action, keyed, start or 0.0))
		animated = {name for _, keyed, _ in clips for name in keyed}
		for action, keyed, start in clips:
			for name in animated:
				missing = {"location", "rotation_quaternion"} - keyed.get(name, set())
				if not missing: continue
				bpy_obj = bpy.data.objects[name]
				bpy_obj.rotation_mode = 'QUATERNION'
				bpy_obj.animation_data.action = action
				slot = next((sl for sl in action.slots if sl.name_display == name), None)
				bpy_obj.animation_data.action_slot = slot or action.slots.new(id_type='OBJECT', name=name)
				bpy_obj.location, bpy_obj.rotation_quaternion = rest[name]
				for data_path in sorted(missing):
					bpy_obj.keyframe_insert(data_path=data_path, frame=start)
		# every animated object now has a slot in every clip: show the first clip on all of them
		for bpy_obj, action in first.values():
			self.assign_action(bpy_obj, clips[0][0])

	def assign_action(self, bpy_obj, action):
		if not bpy_obj.animation_data: bpy_obj.animation_data_create()
		bpy_obj.animation_data.action = action
		slot = next((sl for sl in action.slots if sl.name_display == bpy_obj.name), None)
		if slot is not None:
			bpy_obj.animation_data.action_slot = slot

	def apply_keyframes_to_object(self, bpy_obj, sub_anim, action):
		"""MSH keys carry a type: 1 = position only, 2 = rotation only, 3 = both.
		The stored quaternion is the rotation in row-vector form (see key_rotation)."""
		if not bpy_obj.animation_data: bpy_obj.animation_data_create()
		bpy_obj.rotation_mode = 'QUATERNION'
		bpy_obj.animation_data.action = action
		bpy_obj.animation_data.action_slot = action.slots.new(id_type='OBJECT', name=bpy_obj.name)
		for state in sub_anim.states:
			f = state.frame
			if key_has_position(state):
				bpy_obj.location = self.convert_translation(state.vect)
				bpy_obj.keyframe_insert(data_path="location", frame=f)
			if key_has_rotation(state):
				bpy_obj.rotation_quaternion = self.convert_quaternion(state.quat)
				bpy_obj.keyframe_insert(data_path="rotation_quaternion", frame=f)

	def apply_armature_animations(self, arm_obj, block, bone_names, bind_raw):
		"""Skinned clips as pose-bone keys.  A key is the node transform relative to its
		parent node, so pose basis = rest_local^-1 @ key_local (both in Blender space).
		A channel with no keys in a clip holds its rest value."""
		conv = self.conv4()
		parent = block_parents(block)
		rest_local = {}
		for i, B in bind_raw.items():
			rest_local[i] = normalized(B if i not in parent else bind_raw[parent[i]].inverted() @ B)
		first = None
		for anim in getattr(block, "animation_list", []):
			action = bpy.data.actions.new(name=f"{arm_obj.name}|{anim.name}")
			action.use_fake_user = True
			if not arm_obj.animation_data: arm_obj.animation_data_create()
			arm_obj.animation_data.action = action
			arm_obj.animation_data.action_slot = action.slots.new(id_type='OBJECT', name=arm_obj.name)
			first = first or action
			animated = set()
			for sub_anim in key_tracks(anim):
				i = getattr(sub_anim.index, "value", sub_anim.index)
				if i not in bone_names: continue
				animated.add(i)
				pb = arm_obj.pose.bones[bone_names[i]]
				pb.rotation_mode = 'QUATERNION'
				R0 = rest_local[i]
				pos = [(k.frame, Vector((k.vect.x, k.vect.y, k.vect.z))) for k in sub_anim.states if key_has_position(k)]
				rot = [(k.frame, key_rotation(k)) for k in sub_anim.states if key_has_rotation(k)]
				rest_inv = (conv @ R0 @ conv).inverted()
				prev = None
				for f in sorted({k.frame for k in sub_anim.states}):
					t = sample_vec(pos, f) if pos else R0.to_translation()
					q = sample_quat(rot, f) if rot else R0.to_quaternion()
					A = Matrix.Translation(t) @ q.to_matrix().to_4x4()
					loc, quat, _ = (rest_inv @ (conv @ A @ conv)).decompose()
					if prev is not None and prev.dot(quat) < 0: quat.negate()
					prev = quat
					pb.location = loc
					pb.rotation_quaternion = quat
					pb.keyframe_insert(data_path="location", frame=f)
					pb.keyframe_insert(data_path="rotation_quaternion", frame=f)
			# bones the clip does not animate hold their rest pose, so switching
			# actions never leaves them in the previous clip's pose
			for i, name in bone_names.items():
				if i in animated: continue
				pb = arm_obj.pose.bones[name]
				pb.rotation_mode = 'QUATERNION'
				pb.location = (0.0, 0.0, 0.0)
				pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
				pb.keyframe_insert(data_path="location", frame=0)
				pb.keyframe_insert(data_path="rotation_quaternion", frame=0)
		if first:
			self.assign_action(arm_obj, first)

	def find_node_by_index(self, target_index):
		return self.objects_by_state_index.get(getattr(target_index, "value", target_index))

	def conv3(self):
		return BZ2_TO_BLENDER_3 if self.opt["rotate_for_yz"] else Matrix.Identity(3)

	def conv4(self):
		return BZ2_TO_BLENDER if self.opt["rotate_for_yz"] else Matrix.Identity(4)

	def build_mesh(self, name, positions, triangles, loop_normals=None, loop_uvs=None, face_materials=None):
		"""positions: BZ2-space points; triangles: vertex index triples in file order;
		loop_normals / loop_uvs: one per corner in the same order.  The mesh data is
		converted into Blender space here like the object matrices (BZ2 is left-handed,
		so the Y/Z swap also reverses the winding to keep faces pointing outward)."""
		# Drop degenerate triangles (a repeated vertex) and out-of-range indices with their
		# per-corner data: several stock meshes have them, and Blender's custom normals
		# crash on such topology.
		keep = [k for k, tri in enumerate(triangles) if len(set(tri)) == 3 and all(0 <= i < len(positions) for i in tri)]
		if len(keep) != len(triangles):
			pick = lambda seq: None if seq is None else [seq[3 * k + j] for k in keep for j in range(3)]
			loop_normals, loop_uvs = pick(loop_normals), pick(loop_uvs)
			face_materials = None if face_materials is None else [face_materials[k] for k in keep]
			triangles = [triangles[k] for k in keep]
		C = self.conv3()
		order = (0, 2, 1) if C.determinant() < 0 else (0, 1, 2)
		verts = [tuple(C @ Vector(p)) for p in positions]
		faces = [[tri[j] for j in order] for tri in triangles]
		bm = bpy.data.meshes.new(name)
		bm.from_pydata(verts, [], faces)
		reorder = lambda seq: [seq[3 * k + j] for k in range(len(triangles)) for j in order]
		if face_materials is not None:
			for poly, mat in zip(bm.polygons, face_materials):
				if mat is None: continue
				if mat.name not in bm.materials: bm.materials.append(mat)
				poly.material_index = bm.materials.find(mat.name)
		if self.opt["import_mesh_uvmap"] and loop_uvs is not None:
			self.create_uvmap(bm, reorder(loop_uvs))
		if self.opt["import_mesh_normals"] and loop_normals is not None:
			self.create_normals(bm, [tuple((C @ Vector(n)).normalized()) for n in reorder(loop_normals)])
		return bm

	def create_local_mesh(self, mesh):
		if not mesh.vertex: return None
		positions = [(v.pos.x, v.pos.y, v.pos.z) for v in mesh.vertex]
		triangles, face_materials, i_start, v_start = [], [], 0, 0
		for vg in mesh.vert_groups:
			i_end = i_start + vg.index_count.value
			mat = self.create_material(vg.material, vg.texture) if self.opt["import_mesh_materials"] else None
			for i in range(i_start, i_end, 3):
				triangles.append((v_start + mesh.indices[i], v_start + mesh.indices[i+1], v_start + mesh.indices[i+2]))
				face_materials.append(mat)
			v_start += vg.vert_count.value
			i_start = i_end
		corners = [mesh.vertex[i] for tri in triangles for i in tri]
		return self.build_mesh(mesh.name, positions, triangles,
			[tuple(v.norm) for v in corners], [tuple(v.uv) for v in corners], face_materials)

	def global_face_data(self, block):
		"""Block-level geometry from the per-corner face records (vertex / normal / uv
		index triples and a bucky = material index).  For skinned blocks this is the only
		complete geometry: their block index list is empty."""
		triangles = [tuple(face.verts) for face in block.faces]
		normals = [tuple(block.vertex_normals[n]) for face in block.faces for n in face.norms] if block.vertex_normals else None
		uvs = [tuple(block.uvs[u]) for face in block.faces for u in face.uvs] if block.uvs else None
		materials = None
		if self.opt["import_mesh_materials"] and block.buckydescriptions:
			bucky_mats = [self.create_material(b.material, b.texture) for b in block.buckydescriptions]
			materials = [bucky_mats[min(face.buckyIndex, len(bucky_mats) - 1)] for face in block.faces]
		return triangles, normals, uvs, materials

	def create_global_mesh(self, block):
		positions = [tuple(v) for v in block.vertices]
		if block.faces and (self.opt.get("data_from_faces") or not block.indices):
			return self.build_mesh(block.name, positions, *self.global_face_data(block))
		triangles, v_off, i_off = [], 0, 0
		for vg in block.vert_groups:
			for i in range(i_off, i_off + vg.index_count.value, 3):
				triangles.append((block.indices[i]+v_off, block.indices[i+1]+v_off, block.indices[i+2]+v_off))
			v_off += vg.vert_count.value
			i_off += vg.index_count.value
		return self.build_mesh(block.name, positions, triangles)

	def create_skinned(self, block):
		"""Skinned block -> Armature (one bone per node; rest = the block bind matrices)
		plus the block-level mesh weighted by vert_to_state under an Armature modifier.
		The per-node local meshes are skipped: the block mesh already contains them."""
		conv = self.conv4()
		nodes = [mesh for mesh, _ in block.walk()]
		parent = block_parents(block)
		bind_raw = {}
		for mesh in nodes:
			i = mesh.state_index.value
			if i < len(block.state_matrices):
				# state matrices hold the inverse bind in row-vector form
				bind_raw[i] = Matrix(list(block.state_matrices[i])).transposed().inverted()
			else:
				local = Matrix(list(mesh.matrix)).transposed()
				bind_raw[i] = bind_raw[parent[i]] @ local if i in parent else local

		arm = bpy.data.armatures.new(block.name)
		arm_obj = bpy.data.objects.new(block.name, arm)
		self.collection.objects.link(arm_obj)
		self.bpy_objects.append(arm_obj)
		view_layer = self.context.view_layer
		prev_active = view_layer.objects.active
		view_layer.objects.active = arm_obj
		bpy.ops.object.mode_set(mode='EDIT')
		bone_names, heads = {}, {}
		for mesh in nodes:
			i = mesh.state_index.value
			eb = arm.edit_bones.new(mesh.name)
			eb.head = (0.0, 0.0, 0.0)
			eb.tail = (0.0, 0.1, 0.0)
			eb.matrix = normalized(conv @ bind_raw[i] @ conv)
			bone_names[i] = eb.name
			heads[i] = eb.head.copy()
		for mesh in nodes:
			i = mesh.state_index.value
			eb = arm.edit_bones[bone_names[i]]
			if i in parent:
				eb.parent = arm.edit_bones[bone_names[parent[i]]]
			gaps = [(heads[c.state_index.value] - heads[i]).length for c in mesh.meshes]
			gaps = [g for g in gaps if g > 1e-3]
			eb.length = max(0.02, min(gaps)) if gaps else 0.05
		bpy.ops.object.mode_set(mode='OBJECT')
		view_layer.objects.active = prev_active

		name = block.name + "_skin"
		skin_obj = self.create_object(name, self.build_mesh(name, [tuple(v) for v in block.vertices], *self.global_face_data(block)),
			Matrix.Identity(4), arm_obj)
		groups = {}
		for vi, entry in enumerate(block.vert_to_state):
			for a in entry.array:
				bone = bone_names.get(a.index)
				if bone is None or a.weight <= 0.0: continue
				if bone not in groups: groups[bone] = skin_obj.vertex_groups.new(name=bone)
				groups[bone].add([vi], a.weight, 'REPLACE')
		skin_obj.modifiers.new("Armature", 'ARMATURE').object = arm_obj
		for i in bone_names:
			self.objects_by_state_index.setdefault(i, arm_obj)
		self.armatures.append((arm_obj, block, bone_names, bind_raw))
		return arm_obj

	def create_material(self, msh_mat, msh_tex):
		"""MSH material -> Principled BSDF.  BZ2R/BZCC meshes name a .material file
		(e.g. "fvtank_skel_1.material") whose [texture] section lists the diffuse, specular,
		normal, emissive and team-colour maps; older meshes carry a single texture name.
		Colours come from the msh material.  Unnamed materials differ only by colour, so they
		are keyed by it rather than collapsed into one."""
		name = msh_mat.name if msh_mat and msh_mat.name else None
		tname = msh_tex.name if msh_tex else None
		if name is None:
			name = "Default" if msh_mat is None else "Solid_%02x%02x%02x" % tuple(
				min(255, max(0, int(round(c * 255)))) for c in tuple(msh_mat.diffuse)[:3])
			if tname: name += "_" + tname
		if name in self.existing_materials: return self.existing_materials[name]

		bpy_mat = bpy.data.materials.new(name=name)
		if getattr(bpy_mat, "node_tree", None) is None:
			bpy_mat.use_nodes = True
		bpy_mat.blend_method = "HASHED"
		tree = bpy_mat.node_tree
		bsdf = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
		inputs = lambda *names: next((bsdf.inputs[n] for n in names if n in bsdf.inputs), None)
		if msh_mat:
			bsdf.inputs["Base Color"].default_value = tuple(msh_mat.diffuse)[:3] + (1.0,)
			emissive = tuple(msh_mat.emissive)[:3]
			if any(emissive):
				inputs("Emission Color", "Emission").default_value = emissive + (1.0,)
				inputs("Emission Strength").default_value = NODE_EMISSIVE_STRENGTH
		bsdf.inputs["Roughness"].default_value = NODE_DEFAULT_ROUGHNESS

		maps = {}
		if name.casefold().endswith(".material"):
			mat_path = find_texture(os.path.join(self.filefolder, name), self.texture_search_directories,
				[".material"], self.opt["find_textures"])
			if os.path.exists(mat_path):
				maps = read_material_file(mat_path)
			elif PRINT_TEXTURE_FINDER_INFO:
				print(f"material file not found: {name}")
		if tname and not maps.get("diffuse"):
			maps["diffuse"] = tname

		for which, tex in maps.items():
			if not tex: continue
			path = self.resolve_texture_path(tex)
			if not os.path.exists(path): continue
			image = self.load_texture_image(path)
			if image is None: continue
			node = tree.nodes.new("ShaderNodeTexImage")
			node.image = image
			node.label = f"{which}: {os.path.basename(path)}"
			node.location = (-NODE_SPACING_X, NODE_HEIGHT.get(which, 0))
			if which == "diffuse":
				tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
			elif which == "normal":
				image.colorspace_settings.name = "Non-Color"
				normal_map = tree.nodes.new("ShaderNodeNormalMap")
				normal_map.location = (-NODE_SPACING_X / 2, NODE_HEIGHT[which])
				normal_map.inputs["Strength"].default_value = NODE_NORMALMAP_STRENGTH
				tree.links.new(node.outputs["Color"], normal_map.inputs["Color"])
				tree.links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
			elif which == "specular":
				# colour = specular tint; alpha = glossiness (roughness = 1 - gloss)
				image.colorspace_settings.name = "Non-Color"
				tint = inputs("Specular Tint", "Specular")
				if tint is not None:
					tree.links.new(node.outputs["Color"], tint)
				invert = tree.nodes.new("ShaderNodeInvert")
				invert.location = (-NODE_SPACING_X / 2, NODE_HEIGHT[which])
				tree.links.new(node.outputs["Alpha"], invert.inputs["Color"])
				tree.links.new(invert.outputs["Color"], bsdf.inputs["Roughness"])
			elif which == "emissive":
				tree.links.new(node.outputs["Color"], inputs("Emission Color", "Emission"))
				inputs("Emission Strength").default_value = NODE_EMISSIVE_STRENGTH
			# teamcolor: no Principled input; kept as an unlinked node for baking a faction tint

		self.existing_materials[name] = bpy_mat
		return bpy_mat

	def create_normals(self, bm, normals):
		try:
			bm.polygons.foreach_set("use_smooth", [True] * len(bm.polygons))
			if len(normals) == len(bm.loops):
				bm.normals_split_custom_set(normals)
			elif len(normals) == len(bm.vertices):
				bm.normals_split_custom_set_from_vertices(normals)
		except: pass

	def create_uvmap(self, bm, uvs):
		uvl = bm.uv_layers.new().data
		for i, uv in enumerate(uvs): uvl[i].uv = Vector((uv[0], 1.0 - uv[1]))

	def create_matrix(self, m):
		raw = Matrix(list(m)).transposed()
		if not self.opt["rotate_for_yz"]:
			return raw
		return BZ2_TO_BLENDER @ raw @ BZ2_TO_BLENDER

	def convert_translation(self, vect):
		raw = Vector((vect.x, vect.y, vect.z))
		if not self.opt["rotate_for_yz"]:
			return raw
		return BZ2_TO_BLENDER_3 @ raw

	def convert_quaternion(self, quat):
		w = getattr(quat, "s", getattr(quat, "w", 1.0))
		raw = Quaternion((w, quat.x, quat.y, quat.z))
		if raw.magnitude == 0.0:
			return Quaternion((1.0, 0.0, 0.0, 0.0))
		raw = raw.normalized().conjugated()  # stored in row-vector form
		if not self.opt["rotate_for_yz"]:
			return raw
		rot = raw.to_matrix().to_4x4()
		return (BZ2_TO_BLENDER @ rot @ BZ2_TO_BLENDER).to_quaternion().normalized()

	def create_object(self, name, data, mat, parent=None):
		obj = bpy.data.objects.new(name, data)
		obj.matrix_local = mat
		if parent: obj.parent = parent
		self.bpy_objects.append(obj)
		return obj

def load(operator, context, filepath="", **opt):
	multi_select = opt.pop("multi_select", None) or []
	if multi_select:
		for path in multi_select:
			Load(operator, context, path, True, **opt)
	else:
		Load(operator, context, filepath, opt["import_collection"], **opt)
	return {"FINISHED"}
