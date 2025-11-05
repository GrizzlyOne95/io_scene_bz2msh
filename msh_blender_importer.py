import bpy
import re  # Reading .material files
from mathutils import Matrix, Vector, Euler, Quaternion
from bpy_extras import image_utils
from math import radians

from . import bz2msh
from . import undxtbz2
import os

# Normals changed in 4.1 from 4.0
OLD_NORMALS = not (bpy.app.version[0] >= 4 and bpy.app.version[1] >= 1)

PRINT_TEXTURE_FINDER_INFO = False
PRINT_LOCAL_MATERIAL_REUSE = False
PRINT_MSH_HEADER = True

# texture files
IMAGE_DIFFUSE = ("base", "diffuse", "albedo",)
IMAGE_SPECULAR = ("spec", "specular")
IMAGE_EMISSIVE = ("emissive", "glow")  # maybe?
IMAGE_NORMAL = ("normal", "normals", "bump", "bumpmap")  # maybe?
IMAGE_TEXTURE_SUFFIX = {
	"diffuse": IMAGE_DIFFUSE,
	"specular": IMAGE_SPECULAR,
	"emissive": IMAGE_EMISSIVE,
	"normal": IMAGE_NORMAL
}
DEFAULT_SUFFIXES = {
	"diffuse": "diffuse",
	"specular": "specular",
	"emissive": "emissive",
	"normal": "normal"
}

NODE_NORMALMAP_STRENGTH = 1.0
NODE_EMISSIVE_STRENGTH = 1.0
NODE_DEFAULT_ROUGHNESS = 0.50

# Emulate mesh render flags
USE_RENDER_FLAGS = True
RENDER_FLAGS_RENAME = True  # add __h2cg etc to object name

# Visual placement for material nodes in the blender node editor
NODE_SPACING_X, NODE_SPACING_Y = 600, 300
NODE_HEIGHT = {
	"diffuse": NODE_SPACING_Y,
	"specular": 0,
	"emissive": -NODE_SPACING_Y,
	"normal": -(NODE_SPACING_Y * 2)
}


def find_texture(texture_filepath, search_directories, acceptable_extensions, recursive=False):
	acceptable_extensions = list(acceptable_extensions)
	
	file_name, original_extension = os.path.splitext(os.path.basename(texture_filepath))
	original_extension_compare = original_extension.lower()
	is_material_file = bool(original_extension_compare == ".material")
	
	# Exact path as specified
	if os.path.exists(texture_filepath):
		if PRINT_TEXTURE_FINDER_INFO:
			print("TEXTURE FINDER %r:" % file_name, "original path %r was exact match." % texture_filepath)
		return texture_filepath
	
	if is_material_file:
		# Only look for .material files
		acceptable_extensions = [original_extension_compare]
	else:
		while original_extension_compare in acceptable_extensions:
			# Remove if already present, so we don't look twice
			del acceptable_extensions[acceptable_extensions.index(original_extension_compare)]
		
		# Originally specified extension will be searched for first
		if original_extension_compare in acceptable_extensions:
			acceptable_extensions.insert(0, acceptable_extensions.pop(acceptable_extensions.index(original_extension_compare)))
	
	# Look for file with same name+ext in current directory
	same_name_same_ext = (("%s%s" % (file_name, ext)) for ext in acceptable_extensions)
	for file in same_name_same_ext:
		if os.path.exists(file):
			if PRINT_TEXTURE_FINDER_INFO:
				print("TEXTURE FINDER %r:" % file_name, "local path %r was exact match." % file)
			return file
	
	# Look for same name+matching ext in search paths
	for directory in search_directories:
		for file in acceptable_extensions:
			file = os.path.join(directory, file_name + file)
			if os.path.exists(file):
				if PRINT_TEXTURE_FINDER_INFO:
					print("TEXTURE FINDER %r:" % file_name, "local with subdirs %r was exact match." % file)
				return file
	
	if PRINT_TEXTURE_FINDER_INFO:
		print("TEXTURE FINDER %r" % file_name, "was not an exact match in initial search")
	
	# Recursive option looks in all directories and subdirectories of search directories
	if recursive:
		for directory in search_directories:
			for root, subdirectories, filenames in os.walk(directory):
				for filename in filenames:
					base, extension = os.path.splitext(filename)
					if base == file_name and extension in acceptable_extensions:
						fullpath = os.path.join(root, filename)
						if os.path.exists(fullpath):
							if PRINT_TEXTURE_FINDER_INFO:
								print("TEXTURE FINDER %r:" % file_name, "recursive was exact match, found in %r" % fullpath)
							return fullpath
	
	print("TEXTURE FINDER %r: WARNING: original path %r not found, and not found in %r." % (file_name, texture_filepath, search_directories))
	
	return texture_filepath


def verts_of_all_vertex_groups(mesh):
	index_start = 0
	vert_start = 0
	for vgroup in mesh.vert_groups:
		index_end = index_start + vgroup.index_count.value
		for index in mesh.indices[index_start:index_end]:
			yield mesh.vertex[vert_start + index]
		vert_start += vgroup.vert_count.value
		index_start = index_end


class Load:
	def __init__(self, operator, context, filepath="", as_collection=False, **opt):
		self.opt = opt
		self.context = context
		
		self.name = os.path.basename(filepath)
		self.filefolder = os.path.dirname(filepath)
		self.ext_list = self.opt["find_textures_ext"].casefold().split()
		self.tex_dir = self.context.preferences.filepaths.texture_directory
		
		self.bpy_objects = []
		bpy_root_objects = []
		
		# Animation mapping and options
		self.block_to_object = {}
		self.mesh_to_object = {}
		self.import_animations = self.opt.get("import_animations", False)
		self.animation_mode = self.opt.get("animation_mode", "AUTO")
		self.auto_convert_dxtbz2 = self.opt.get("auto_convert_dxtbz2", False)
		
		# Entire .msh file is read into this object first
		msh = bz2msh.MSH(filepath)
		
		collection = self.context.view_layer.active_layer_collection.collection
		if as_collection:
			collection = bpy.data.collections.new(os.path.basename(filepath))
			bpy.context.scene.collection.children.link(collection)
		
		if PRINT_MSH_HEADER:
			print("\nMSH %r" % os.path.basename(filepath))
			for block in msh.blocks:
				print("\nBlock %r MSH Header:" % block.name)
				print("- dummy:", block.msh_header.dummy)
				print("- scale:", block.msh_header.scale)
				print("- indexed:", block.msh_header.indexed)
				print("- moveAnim:", block.msh_header.moveAnim)
				print("- oldPipe:", block.msh_header.oldPipe)
				print("- isSingleGeometry:", block.msh_header.isSingleGeometry)
				print("- skinned:", block.msh_header.skinned, "\n")
		
		# Deselect all objects in blender
		for bpy_obj in context.scene.objects:
			bpy_obj.select_set(False)
		
		if opt["import_mode"] == "GLOBAL":
			for block in msh.blocks:
				bpy_obj = self.create_object(
					block.name,
					self.create_global_mesh(block),
					self.create_matrix(Matrix()),
					None
				)
				
				# Remember which Blender object came from which block (for animation)
				self.block_to_object[block] = bpy_obj
				
				scale = block.msh_header.scale
				bpy_obj.scale = Vector((scale, scale, scale))
				bpy_root_objects.append(bpy_obj)
		
		elif opt["import_mode"] == "LOCAL":
			# Reuse same-named materials for each local mesh
			self.existing_materials = {}  # {str(name of msh material): bpy.types.Material(blender material object)}
			for block in msh.blocks:
				bpy_root_objects.append(self.walk(block.root))
		
		for bpy_obj in bpy_root_objects:
			if self.opt["rotate_for_yz"]:
				bpy_obj.rotation_euler[0] = radians(90)
				bpy_obj.rotation_euler[2] = radians(180)
				bpy_obj.location[1], bpy_obj.location[2] = bpy_obj.location[2], bpy_obj.location[1]
			
			if self.opt["place_at_cursor"]:
				bpy_obj.location += context.scene.cursor.location
		
		# Import animations after all geometry is created
		if self.import_animations:
			self.import_animations_from_msh(msh)
		
		for bpy_obj in self.bpy_objects[::-1]:
			collection.objects.link(bpy_obj)
			bpy_obj.select_set(True)
			self.context.view_layer.objects.active = bpy_obj
	
	def walk(self, mesh, bpy_parent=None):
		bpy_obj = self.create_object(
			mesh.name,
			self.create_local_mesh(mesh),
			self.create_matrix(mesh.matrix),
			bpy_parent
		)
		
		# Remember mapping Mesh -> Blender object for animation
		self.mesh_to_object[mesh] = bpy_obj
		
		if USE_RENDER_FLAGS and bpy_obj.data:
			ignore_hidden = bool(mesh.name.split("_")[0].casefold() in ("flame",))
			append_flags = ""
			
			if mesh.renderflags.value & bz2msh.RS_HIDDEN and not ignore_hidden:
				bpy_obj.hide_render = True
				bpy_obj.display_type = "WIRE"
				append_flags += "h"
			
			if mesh.renderflags.value & bz2msh.RS_COLLIDABLE and not ignore_hidden:
				bpy_obj.hide_render = True
				bpy_obj.display_type = "WIRE"
				append_flags += "2"
			
			if mesh.renderflags.value & bz2msh.RS_ADDITIVE:
				append_flags += "a"
			
			if mesh.renderflags.value & bz2msh.RS_DONOTLIGHT:
				append_flags += "e"
			
			if mesh.renderflags.value & bz2msh.RS_ALPHACUTOFF:
				append_flags += "c"
			
			if mesh.renderflags.value & bz2msh.RS_2SIDED:
				append_flags += "h"
			
			if mesh.renderflags.value & bz2msh.RS_DST_ONE:
				# Not supported in BZCC I think?
				# append_flags += "g"
				pass
			
			if RENDER_FLAGS_RENAME and append_flags:
				bpy_obj.name = bpy_obj.name + "__" + append_flags
		
		if not bpy_parent:
			scale = mesh.block.msh_header.scale
			bpy_obj.scale = Vector((scale, scale, scale))
		
		if not bpy_obj.data:
			bpy_obj.empty_display_type = "SINGLE_ARROW"
		
		for msh_sub_mesh in mesh.meshes:
			self.walk(msh_sub_mesh, bpy_obj)
		
		return bpy_obj
	
	def create_normals(self, bpy_mesh, normals):
		try:
			# Note: Setting invalid normals causes a crash when going into edit mode.
			# If possible, at this point we should check for invalid normals that might cause blender to crash.
			bpy_mesh.normals_split_custom_set(normals)
			if OLD_NORMALS:
				bpy_mesh.use_auto_smooth = True
		
		except RuntimeError as msg:
			print("MSH importer failed to import normals for %r:" % bpy_mesh.name, msg)
			if OLD_NORMALS:
				bpy_mesh.use_auto_smooth = False
	
	def create_uvmap(self, bpy_mesh, uvs):
		bpy_uvmap = bpy_mesh.uv_layers.new().data
		for index, uv in enumerate(uvs):
			bpy_uvmap[index].uv = Vector((uv[0], -uv[1] + 1.0))
	
	def create_vertex_colors(self, bpy_mesh, colors):
		bpy_vcol = bpy_mesh.vertex_colors.new().data
		
		if colors:
			loop_colors = []
			for poly in bpy_mesh.polygons:
				for loop_index in poly.loop_indices:
					loop_colors += [colors[loop_index]]
			
			for index, color in enumerate(loop_colors):
				bpy_vcol[index].color = [value/255 for value in (color.r, color.g, color.b, color.a)]
				# BZ2 style alternative commented out
	
	def create_matrix(self, msh_matrix):
		return Matrix(list(msh_matrix)).transposed()
	
	def create_object(self, name, data, matrix, bpy_obj_parent=None):
		bpy_obj = bpy.data.objects.new(name=name, object_data=data)
		
		if bpy_obj_parent:
			bpy_obj.parent = bpy_obj_parent
		
		bpy_obj.matrix_local = matrix
		
		self.bpy_objects.append(bpy_obj)
		
		return bpy_obj
	
	def create_global_mesh(self, block):
		if len(block.vertices) <= 0:
			return None
		
		vertices = [tuple(v) for v in block.vertices]
		faces = [tuple(faceobj.verts) for faceobj in block.faces]
		bucky_indices = [int(faceobj.buckyIndex) for faceobj in block.faces]
		
		bpy_mesh = bpy.data.meshes.new(block.name)
		bpy_mesh.from_pydata(vertices, [], faces)
		
		if self.opt["import_mesh_materials"]:
			bpy_materials = []
			for bucky in block.buckydescriptions:
				bpy_materials += [self.create_material(bucky.material, bucky.texture)]
				bpy_mesh.materials.append(bpy_materials[-1])
			
			for index, material_index in enumerate(bucky_indices):
				bpy_mesh.polygons[index].material_index = material_index
		
		if self.opt["import_mesh_uvmap"]:
			if self.opt["data_from_faces"]:
				uvs = []
				for faceobj in block.faces:
					for uv_index in faceobj.uvs:
						uvs += [tuple(block.uvs[uv_index])]
				
				self.create_uvmap(bpy_mesh, uvs)
			
			else:
				self.create_uvmap(bpy_mesh, ((tuple(block.uvs[index])) for index in block.indices))
		
		if self.opt["import_mesh_normals"]:
			if self.opt["data_from_faces"]:
				normals = []
				for faceobj in block.faces:
					for norm_index in faceobj.norms:
						normals += [tuple(block.vertex_normals[norm_index])]
				
				self.create_normals(bpy_mesh, normals)
			
			else:
				self.create_normals(bpy_mesh, [(tuple(block.vertex_normals[index])) for index in block.indices])
		
		if self.opt["import_mesh_vertcolor"]:
			if self.opt["data_from_faces"]:
				colors = []
				if block.vert_colors:
					for faceobj in block.faces:
						for index in faceobj.verts:
							colors += [block.vert_colors[index]]
				
				self.create_vertex_colors(bpy_mesh, colors)
			
			else:
				self.create_vertex_colors(bpy_mesh, [block.vert_colors[index] for index in block.indices])
		
		return bpy_mesh
	
	# 7-10-2024: Import logic improved by ZerothDivision and tested by GrizzlyOne95
	def create_local_mesh(self, mesh):
		if len(mesh.vertex) <= 0:
			return None
		
		vertices = [(vert.pos.x, vert.pos.y, vert.pos.z) for vert in mesh.vertex]
		
		faces = []
		index_start = 0
		vert_start = 0
		for vgindex, vgroup in enumerate(mesh.vert_groups):
			triangle = []
			index_end = index_start + vgroup.index_count.value
			for index in mesh.indices[index_start:index_end]:
				triangle += [vert_start + index]
				if len(triangle) >= 3:
					faces += [triangle]
					triangle = [triangle[0], triangle[-1]]
			
			index_start = index_end
			vert_start += vgroup.vert_count.value
		
		bpy_mesh = bpy.data.meshes.new(mesh.name)
		bpy_mesh.from_pydata(vertices, [], faces)
		
		if self.opt["import_mesh_materials"]:
			bpy_materials = []
			
			verts_processed = 0
			face_start = 0
			
			for local_vert_group in mesh.vert_groups:
				bucky = mesh.block.buckydescriptions[local_vert_group.flags.value]
				lmat = bucky.material
				ltex = bucky.texture
				
				if PRINT_LOCAL_MATERIAL_REUSE:
					print("VertGroup %r uses material from block bucky[%d]" % (mesh.name, local_vert_group.flags.value))
				
				if lmat and lmat.name in self.existing_materials:
					bpy_materials += [self.existing_materials[lmat.name]]
					if PRINT_LOCAL_MATERIAL_REUSE:
						print("Reusing material:", lmat.name)
				
				else:
					bpy_materials += [self.create_material(lmat, ltex)]
					self.existing_materials[lmat.name] = bpy_materials[-1]
					if PRINT_LOCAL_MATERIAL_REUSE:
						print("New Material %r" % lmat.name)
				
				mat_index = len(bpy_mesh.materials)
				bpy_mesh.materials.append(bpy_materials[-1])
				
				face_end = face_start + local_vert_group.index_count.value // 3  # Index count should be divisible by 3
				for index in range(face_start, face_end):
					bpy_mesh.polygons[index].material_index = mat_index
				
				face_start = face_end
		
		if self.opt["import_mesh_uvmap"]:
			self.create_uvmap(bpy_mesh, [tuple(vertex.uv) for vertex in verts_of_all_vertex_groups(mesh)])
		
		if self.opt["import_mesh_normals"]:
			self.create_normals(bpy_mesh, [tuple(vertex.norm) for vertex in verts_of_all_vertex_groups(mesh)])
		
		if self.opt["import_mesh_vertcolor"]:
			colors = []
			if mesh.vert_colors:
				for face in faces:
					for index in face:
						colors += [mesh.vert_colors[index]]
			
			self.create_vertex_colors(bpy_mesh, colors)
		
		return bpy_mesh
	
	def create_material_vcolnodes(self, bpy_material, bpy_node_bsdf, bpy_node_texture):
		bpy_node_attribute = bpy_material.node_tree.nodes.new("ShaderNodeAttribute")
		bpy_node_attribute.attribute_name = "Col"
		bpy_node_attribute.attribute_type = "GEOMETRY"
		bpy_node_attribute.location = (-NODE_SPACING_X, NODE_HEIGHT["diffuse"] + NODE_SPACING_Y)
		
		bpy_node_mixrgb = bpy_material.node_tree.nodes.new("ShaderNodeMixRGB")
		bpy_node_mixrgb.inputs[0].default_value = 1.0  # Factor
		bpy_node_mixrgb.blend_type = "MULTIPLY"
		bpy_node_mixrgb.location = (-NODE_SPACING_X / 2, NODE_HEIGHT["diffuse"] + NODE_SPACING_Y / 2)
		
		bpy_material.node_tree.links.new(
			bpy_node_attribute.outputs["Color"],
			bpy_node_mixrgb.inputs["Color1"]
		)
		
		bpy_material.node_tree.links.new(
			bpy_node_texture.outputs["Color"],
			bpy_node_mixrgb.inputs["Color2"]
		)
		
		bpy_material.node_tree.links.new(
			bpy_node_mixrgb.outputs["Color"],
			bpy_node_bsdf.inputs["Base Color"]
		)

	def maybe_convert_dxtbz2(self, path):
		"""If option enabled and path is .dxtbz2, convert to .dds and return the .dds path."""
		if not self.auto_convert_dxtbz2:
			return path
		if not path:
			return path
		base, ext = os.path.splitext(path)
		if ext.lower() != ".dxtbz2":
			return path
		
		dds_path = path + ".dds"
		try:
			if not os.path.exists(dds_path):
				print(f"Converting DXTbz2 texture {path} -> {dds_path}")
				undxtbz2.dxtbz2_to_dds(path, dds_path)
			return dds_path
		except Exception as e:
			print(f"Failed to convert {path} to DDS: {e}")
			return path
	
	def create_material(self, msh_material=None, msh_texture=None):
		find_in = (self.filefolder, self.tex_dir)
		recursive = self.opt["find_textures"]
		
		material_name = msh_material.name if msh_material else None
		texture_name = msh_texture.name if msh_texture else None
		image_is_material_file = bool(os.path.splitext(material_name)[1].casefold() == ".material" if material_name else None)
		
		bpy_material = bpy.data.materials.new(name=material_name)
		bpy_material.use_nodes = True
		# Needed for diffuse channel due to backfacing z-order issues with other blend modes
		bpy_material.blend_method = "HASHED"
		bpy_node_bsdf = bpy_material.node_tree.nodes["Principled BSDF"]
		
		bpy_node_bsdf.inputs["Base Color"].default_value = tuple(
			value / 255 for value in (
				msh_material.diffuse.r,
				msh_material.diffuse.g,
				msh_material.diffuse.b,
				msh_material.diffuse.a
			)
		) if msh_material else (1.0, 1.0, 1.0, 1.0)
		
		bpy_node_bsdf.inputs["Emission Color"].default_value = tuple(
			value / 255 for value in (
				msh_material.emissive.r,
				msh_material.emissive.g,
				msh_material.emissive.b,
				msh_material.emissive.a
			)
		) if msh_material else (0.0, 0.0, 0.0, 1.0)
		
		bpy_node_bsdf.inputs["Emission Strength"].default_value = NODE_EMISSIVE_STRENGTH
		bpy_node_bsdf.inputs["Roughness"].default_value = NODE_DEFAULT_ROUGHNESS
		
		if image_is_material_file and material_name:
			# Blender material files
			image_filepath = find_texture(material_name, find_in, (".blend",), recursive)
			with bpy.data.libraries.load(image_filepath) as (data_from, data_to):
				data_to.materials = [material_name]
			
			if data_to.materials:
				return data_to.materials[0]
		
		if msh_texture:
			texture_names = {
				"diffuse": None,
				"specular": None,
				"emissive": None,
				"normal": None
			}
			
			if texture_name:
				# material and texture info in file
				if image_is_material_file:
					# BZCC style .material files
					image_filepath = find_texture(material_name, find_in, (".material",), recursive)
					try:
						with open(image_filepath, "r") as f:
							material_file = f.read()
					except Exception:
						material_file = ""
						print("Warning: Failed to open material file %r." % image_filepath)
					
					if material_file:
						if re.search("Material.*shader: normal", material_file, re.IGNORECASE | re.DOTALL):
							textures = re.findall(
								"\nTexture \"([^\"]*?)\" type: (.*?)$",
								material_file,
								re.IGNORECASE | re.MULTILINE
							)
							
							for texture_name, texture_type in textures:
								if "diffuse" in texture_type:
									texture_names["diffuse"] = texture_name
								
								elif "bump" in texture_type:
									texture_names["normal"] = texture_name
								
								elif "specular" in texture_type:
									texture_names["specular"] = texture_name
								
								elif "emissive" in texture_type:
									texture_names["emissive"] = texture_name
						
						else:
							print("Warning: Material file %r does not use 'normal' shader-node and is not supported." % image_filepath)
					
					if not any(texture_names.values()):
						print("Warning: Failed to locate valid textures in material file %r." % image_filepath)
				
				else:
					# Basic Blinn style .material files (e.g. pre-BZCC)
					texture_base_name, extension = os.path.splitext(texture_name)
					texture_names = {
						"diffuse": texture_name,
						"specular": "%s_%s%s" % (texture_base_name, DEFAULT_SUFFIXES["specular"], extension),
						"normal": "%s_%s%s" % (texture_base_name, DEFAULT_SUFFIXES["normal"], extension)
					}
			
			# Try to find textures matching the names specified in the material file
			if msh_texture and not any(texture_names.values()):
				texture_base_name, extension = os.path.splitext(msh_texture.name)
				
				for which in texture_names.keys():
					for suffix in IMAGE_TEXTURE_SUFFIX[which]:
						texture_name = "%s_%s%s" % (texture_base_name, suffix, extension)
						
						if os.path.exists(texture_name):
							texture_names[which] = texture_name
							break
				
				if not any(texture_names.values()):
					print("Warning: Failed to find textures using path %r." % msh_texture.name)
			
			if any(texture_names.values()):
				texture_paths = {
					which: find_texture(name, find_in, self.ext_list, recursive)
					for (which, name) in texture_names.items() if name
				}
				
				if PRINT_TEXTURE_FINDER_INFO:
					print(texture_names)
					print(texture_paths)
				
				for which, path in texture_paths.items():
					# If enabled, auto-convert .dxtbz2 to .dds before loading
					path = self.maybe_convert_dxtbz2(path)
					
					image = image_utils.load_image(path, place_holder=True, check_existing=True)
					image.colorspace_settings.name = "sRGB"
					
					bpy_node_texture = bpy_material.node_tree.nodes.new("ShaderNodeTexImage")
					bpy_node_texture.label = os.path.basename(path)
					bpy_node_texture.image = image
					bpy_node_texture.location = (-NODE_SPACING_X, NODE_HEIGHT[which])
					
					if which == "diffuse":
						if self.opt.get("use_vertex_color_multiply", False):
							self.create_material_vcolnodes(bpy_material, bpy_node_bsdf, bpy_node_texture)
						else:
							bpy_material.node_tree.links.new(
								bpy_node_texture.outputs["Color"],
								bpy_node_bsdf.inputs["Base Color"]
							)
					
					elif which == "normal":
						bpy_node_normalmap = bpy_material.node_tree.nodes.new("ShaderNodeNormalMap")
						bpy_node_normalmap.inputs["Strength"].default_value = NODE_NORMALMAP_STRENGTH
						bpy_node_normalmap.location = (-NODE_SPACING_X / 3, NODE_HEIGHT["normal"])
						
						bpy_material.node_tree.links.new(
							bpy_node_texture.outputs["Color"],
							bpy_node_normalmap.inputs["Color"]
						)
						
						bpy_material.node_tree.links.new(
							bpy_node_normalmap.outputs["Normal"],
							bpy_node_bsdf.inputs["Normal"]
						)
					
					elif which == "specular":
						bpy_node_invert = bpy_material.node_tree.nodes.new("ShaderNodeInvert")
						bpy_node_invert.location = (-NODE_SPACING_X / 2, NODE_HEIGHT[which])
						
						bpy_material.node_tree.links.new(
							bpy_node_texture.outputs["Alpha"],
							bpy_node_invert.inputs["Color"]
						)
						
						bpy_material.node_tree.links.new(
							bpy_node_invert.outputs["Color"],
							bpy_node_bsdf.inputs["Roughness"]
						)
						
						bpy_material.node_tree.links.new(
							bpy_node_invert.outputs["Color"],
							bpy_node_bsdf.inputs["Metallic"]
						)
						
						bpy_material.node_tree.links.new(
							bpy_node_texture.outputs["Color"],
							bpy_node_bsdf.inputs["Specular IOR Level"]
						)
					
					elif which == "emissive":
						bpy_material.node_tree.links.new(
							bpy_node_bsdf.inputs["Emission Color"],
							bpy_node_texture.outputs["Color"]
						)
			
		elif texture_name:
			# Simple pre-bzcc mode
			image_filepath = find_texture(texture_name, find_in, self.ext_list, recursive)
			image_filepath = self.maybe_convert_dxtbz2(image_filepath)
			
			bpy_node_texture = bpy_material.node_tree.nodes.new("ShaderNodeTexImage")
			bpy_node_texture.label = os.path.basename(image_filepath)
			bpy_node_texture.image = image = image_utils.load_image(
				image_filepath,
				place_holder=True,
				check_existing=True
			)
			bpy_node_texture.location = (-NODE_SPACING_X, 0)
			
			bpy_material.node_tree.links.new(
				bpy_node_texture.outputs["Color"],
				bpy_node_bsdf.inputs["Base Color"]
			)
		
		return bpy_material

	def import_animations_from_msh(self, msh):
		"""Import animations from the parsed .msh into Blender as either armature or object animations."""
		mode = (self.animation_mode or "AUTO").upper()
		import_mode = self.opt.get("import_mode", "LOCAL").upper()
		
		if mode == "AUTO":
			if any(block.msh_header.skinned for block in msh.blocks):
				mode = "ARMATURE"
			else:
				mode = "OBJECT"
		
		# If we don't have a global mesh, fall back to object animation
		if mode == "ARMATURE" and import_mode != "GLOBAL":
			mode = "OBJECT"
		
		for block in msh.blocks:
			if not getattr(block, "animation_list", None):
				continue
			
			if mode == "ARMATURE":
				if not block.msh_header.skinned:
					continue
				arm_obj = self.create_armature_for_block(block)
				if arm_obj:
					self.import_armature_animations_for_block(block, arm_obj)
			elif mode == "OBJECT":
				self.import_object_animations_for_block(block)
		
	def create_armature_for_block(self, block):
		"""Create a simple armature from block.state_matrices and hook it up to the global mesh object."""
		if not getattr(block, "state_matrices", None) or len(block.state_matrices) == 0:
			return None
		
		arm_data = bpy.data.armatures.new(block.name + "_Arm")
		arm_obj = bpy.data.objects.new(block.name + "_Arm", arm_data)
		self.bpy_objects.append(arm_obj)
		
		bpy.context.view_layer.objects.active = arm_obj
		bpy.ops.object.mode_set(mode='EDIT')
		
		scale = block.msh_header.scale
		for state_index, msh_matrix in enumerate(block.state_matrices):
			bone = arm_data.edit_bones.new(f"State_{state_index}")
			m = self.create_matrix(msh_matrix)
			head = m.to_translation()
			bone.head = head
			bone.tail = head + Vector((0.0, 0.0, 0.5 * scale))
		
		bpy.ops.object.mode_set(mode='OBJECT')
		
		mesh_obj = self.block_to_object.get(block)
		if mesh_obj and mesh_obj.type == 'MESH':
			mod = mesh_obj.modifiers.new(name="Armature", type='ARMATURE')
			mod.object = arm_obj
			
			for state_index, vts in enumerate(block.vert_to_state):
				vg = mesh_obj.vertex_groups.new(name=f"State_{state_index}")
				for i in range(vts.count):
					vi = vts.array[i]
					vg.add([int(vi.index)], float(vi.weight), 'ADD')
		
		return arm_obj
		
	def import_armature_animations_for_block(self, block, arm_obj):
		"""Convert AnimList entries into Actions on an armature's bones."""
		if not getattr(block, "animation_list", None) or not arm_obj:
			return
		
		if not arm_obj.animation_data:
			arm_obj.animation_data_create()
		
		for animlist in block.animation_list:
			action = bpy.data.actions.new(name=f"{block.name}_{animlist.name}")
			arm_obj.animation_data.action = action
			
			for anim in animlist.animations:
				bone_name = f"State_{int(anim.index.value)}"
				pbone = arm_obj.pose.bones.get(bone_name)
				if not pbone:
					continue
				
				for key in anim.states:
					frame = key.frame
					loc = Vector((key.vect.x, key.vect.y, key.vect.z))
					quat = Quaternion((key.quat.s, key.quat.x, key.quat.y, key.quat.z))
					
					pbone.location = loc
					pbone.rotation_mode = 'QUATERNION'
					pbone.rotation_quaternion = quat
					pbone.keyframe_insert(data_path="location", frame=frame)
					pbone.keyframe_insert(data_path="rotation_quaternion", frame=frame)
		
	def import_object_animations_for_block(self, block):
		"""Animate Blender objects directly based on mesh.state_index and AnimList data."""
		if not getattr(block, "animation_list", None):
			return
		
		if not self.mesh_to_object:
			return
		
		state_to_objects = {}
		for mesh, obj in self.mesh_to_object.items():
			if getattr(mesh, "block", None) is block:
				state_idx = int(mesh.state_index.value)
				state_to_objects.setdefault(state_idx, []).append(obj)
		
		for animlist in block.animation_list:
			for anim in animlist.animations:
				state_index = int(anim.index.value)
				objs = state_to_objects.get(state_index, [])
				if not objs:
					continue
				
				for obj in objs:
					if not obj.animation_data:
						obj.animation_data_create()
					
					action = bpy.data.actions.new(name=f"{obj.name}_{animlist.name}_{state_index}")
					obj.animation_data.action = action
					
					for key in anim.states:
						frame = key.frame
						loc = Vector((key.vect.x, key.vect.y, key.vect.z))
						quat = Quaternion((key.quat.s, key.quat.x, key.quat.y, key.quat.z))
						
						obj.rotation_mode = 'QUATERNION'
						obj.location = loc
						obj.rotation_quaternion = quat
						obj.keyframe_insert(data_path="location", frame=frame)
						obj.keyframe_insert(data_path="rotation_quaternion", frame=frame)


def load(operator, context, filepath="", **opt):
	multiple_files = opt["multi_select"]
	as_collection = opt["import_collection"] or multiple_files
	
	if not multiple_files:
		Load(operator, context, filepath, as_collection, **opt)
	else:
		for index, filepath in enumerate(multiple_files):
			try:
				print("Importing file %d of %d (%r)" % (index + 1, len(multiple_files), filepath))
				Load(operator, context, filepath, as_collection, **opt)
			except Exception as msg:
				print("Exception occurred importing MSH file %r." % filepath)
	
	return {"FINISHED"}
