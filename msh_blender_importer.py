import bpy
import re
import os
import ctypes
from ctypes import Structure, c_int, c_ubyte, c_uint32, c_uint
from struct import unpack
from mathutils import Matrix, Vector, Euler, Quaternion
from bpy_extras import image_utils
from math import radians
from . import bz2msh

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
	"normal": -(NODE_SPACING_Y*2)
}

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
	re_section = re.compile(r"(?i)\s*\[([^\]]*)\]")
	re_keyval = re.compile(r"(?i)\s*(\w+)\s*=\s*(.+)")
	textures = {"diffuse": default_diffuse, "specular": None, "normal": None, "emissive": None}
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
					key, value = match.group(1).lower(), match.group(2)
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
		self.bpy_objects = []
		self.existing_materials = {}
		
		self.tex_dir = os.path.join(self.filefolder, "bitmaps")
		self.ext_list = [".tga", ".pic", ".png", ".bmp", ".dds"]

		# Create Collection if requested
		if as_collection:
			self.collection = bpy.data.collections.new(os.path.basename(filepath))
			context.scene.collection.children.link(self.collection)
		else:
			self.collection = context.scene.collection

		# Hierarchy Root Tracking
		bpy_root_objects = []

		if opt["import_mode"] == "GLOBAL":
			mesh_data = self.create_global_mesh(self.msh.blocks[0])
			bpy_obj = self.create_object(self.msh.blocks[0].name, mesh_data, Matrix.Identity(4))
			bpy_root_objects.append(bpy_obj)
		else:
			for block in self.msh.blocks:
				if block.root:
					root_obj = self.walk(block.root)
					bpy_root_objects.append(root_obj)

		# Apply Global Animations after objects are mapped
		if opt.get("import_animations"):
			self.apply_global_animations()

		# Final Scene Placement
		for bpy_obj in bpy_root_objects:
			if self.opt["rotate_for_yz"]:
				bpy_obj.rotation_euler[0] = radians(90)
				bpy_obj.rotation_euler[2] = radians(180)
				bpy_obj.location[1], bpy_obj.location[2] = bpy_obj.location[2], bpy_obj.location[1]
			
			if self.opt["place_at_cursor"]:
				bpy_obj.location += context.scene.cursor.location

		for bpy_obj in self.bpy_objects:
			if bpy_obj.name not in self.collection.objects:
				self.collection.objects.link(bpy_obj)

	def dxtbz2_to_dds(self, filepath):
		"""Internal conversion of .dxtbz2 to standard .dds"""
		dds_path = filepath.replace(".dxtbz2", ".dds")
		if os.path.exists(dds_path): return dds_path
		try:
			with open(filepath, "rb") as f_in:
				header, size = DXTBZ2Header(), c_uint32()
				f_in.readinto(header)
				f_in.readinto(size)
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

	def walk(self, mesh, bpy_parent=None):
		bpy_obj = self.create_object(
			mesh.name,
			self.create_local_mesh(mesh),
			self.create_matrix(mesh.matrix),
			bpy_parent
		)
		self.all_objects[mesh.name] = bpy_obj
		
		# Process hierarchy
		for msh_sub_mesh in mesh.meshes:
			self.walk(msh_sub_mesh, bpy_obj)
		return bpy_obj

	def apply_global_animations(self):
		if not hasattr(self.msh, 'animation_list'): return
		for anim in self.msh.animation_list:
			for sub_anim in anim.animations:
				target_node = self.find_node_by_index(sub_anim.index)
				if target_node:
					bpy_obj = self.all_objects.get(target_node.name)
					if bpy_obj:
						self.apply_keyframes_to_object(bpy_obj, sub_anim, anim.name)

	def apply_keyframes_to_object(self, bpy_obj, sub_anim, action_name):
		if not bpy_obj.animation_data: bpy_obj.animation_data_create()
		bpy_obj.rotation_mode = 'QUATERNION'
		action = bpy.data.actions.new(name=f"{bpy_obj.name}_{action_name}")
		bpy_obj.animation_data.action = action
		slot = action.slots.new(name=bpy_obj.name, id_type='OBJECT')
		bpy_obj.animation_data.action_slot = slot
		for state in sub_anim.states:
			f = state.frame
			bpy_obj.location = (state.vect.x, state.vect.y, state.vect.z)
			bpy_obj.keyframe_insert(data_path="location", frame=f)
			bpy_obj.rotation_quaternion = (state.quat.s, state.quat.x, state.quat.y, state.quat.z)
			bpy_obj.keyframe_insert(data_path="rotation_quaternion", frame=f)

	def find_node_by_index(self, target_index):
		idx = 0
		for block in self.msh.blocks:
			nodes = [block.root] if block.root else []
			while nodes:
				curr = nodes.pop(0)
				if idx == target_index: return curr
				idx += 1
				nodes.extend(curr.meshes)
		return None

	def create_local_mesh(self, mesh):
		if not mesh.vertex: return None
		verts = [(v.pos.x, v.pos.y, v.pos.z) for v in mesh.vertex]
		faces, i_start, v_start = [], 0, 0
		for vg in mesh.vert_groups:
			i_end = i_start + vg.index_count.value
			for i in range(i_start, i_end, 3):
				faces.append([v_start + mesh.indices[i], v_start + mesh.indices[i+1], v_start + mesh.indices[i+2]])
			v_start += vg.vert_count.value
			i_start = i_end
		bm = bpy.data.meshes.new(mesh.name)
		bm.from_pydata(verts, [], faces)
		
		if self.opt["import_mesh_materials"]:
			f_idx = 0
			for vg in mesh.vert_groups:
				mat = self.create_material(vg.material, vg.texture)
				if mat.name not in bm.materials: bm.materials.append(mat)
				m_idx = bm.materials.find(mat.name)
				count = vg.index_count.value // 3
				for i in range(f_idx, f_idx + count):
					bm.polygons[i].material_index = m_idx
				f_idx += count
		
		if self.opt["import_mesh_uvmap"]:
			self.create_uvmap(bm, [tuple(v.uv) for v in verts_of_all_vertex_groups(mesh)])
		if self.opt["import_mesh_normals"]:
			self.create_normals(bm, [tuple(v.norm) for v in verts_of_all_vertex_groups(mesh)])
		return bm

	def create_global_mesh(self, block):
		verts = [tuple(v) for v in block.vertices]
		faces, v_off, i_off = [], 0, 0
		for vg in block.vert_groups:
			for i in range(i_off, i_off + vg.index_count.value, 3):
				faces.append((block.indices[i]+v_off, block.indices[i+1]+v_off, block.indices[i+2]+v_off))
			v_off += vg.vert_count.value
			i_off += vg.index_count.value
		bm = bpy.data.meshes.new(block.name)
		bm.from_pydata(verts, [], faces)
		return bm

	def create_material(self, msh_mat, msh_tex):
		name = msh_mat.name if msh_mat else "Default"
		if name in self.existing_materials: return self.existing_materials[name]
		
		bpy_mat = bpy.data.materials.new(name=name)
		bpy_mat.use_nodes = True
		bpy_mat.blend_method = "HASHED"
		nodes = bpy_mat.node_tree.nodes
		bsdf = nodes["Principled BSDF"]
		
		def get_tex_path(tname):
			p = find_texture(tname, (self.filefolder, self.tex_dir), self.ext_list, self.opt["find_textures"])
			if (not p or not os.path.exists(p)) and self.opt["auto_convert_dxtbz2"]:
				dxt = find_texture(tname, (self.filefolder, self.tex_dir), [".dxtbz2"], self.opt["find_textures"])
				if os.path.exists(dxt): return self.dxtbz2_to_dds(dxt)
			return p

		tname = msh_tex.name if msh_tex else None
		if tname:
			path = get_tex_path(tname)
			if path and os.path.exists(path):
				tex_node = nodes.new("ShaderNodeTexImage")
				tex_node.image = image_utils.load_image(path, place_holder=True)
				bpy_mat.node_tree.links.new(tex_node.outputs["Color"], bsdf.inputs["Base Color"])
		
		self.existing_materials[name] = bpy_mat
		return bpy_mat

	def create_normals(self, bm, normals):
		try:
			bm.polygons.foreach_set("use_smooth", [True] * len(bm.polygons))
			bm.normals_split_custom_set_from_vertices(normals)
		except: pass

	def create_uvmap(self, bm, uvs):
		uvl = bm.uv_layers.new().data
		for i, uv in enumerate(uvs): uvl[i].uv = Vector((uv[0], 1.0 - uv[1]))

	def create_matrix(self, m):
		return Matrix(list(m)).transposed()

	def create_object(self, name, data, mat, parent=None):
		obj = bpy.data.objects.new(name, data)
		obj.matrix_local = mat
		if parent: obj.parent = parent
		self.bpy_objects.append(obj)
		return obj

def load(operator, context, filepath="", **opt):
	Load(operator, context, filepath, opt["import_collection"], **opt)
	return {"FINISHED"}