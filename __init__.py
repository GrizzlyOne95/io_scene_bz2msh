bl_info = {
	"name": "BZ2 MSH format",
	"author": "FruteSoftware@gmail.com & GrizzlyOne95",
	"version": (1, 2, 0),
	"blender": (4, 5, 0),
	"location": "File > Import-Export",
	"description": "Battlezone II/CC MSH Importer",
	"category": "Import-Export"
}

import os
import bpy

from bpy.props import (
	StringProperty,
	BoolProperty,
	FloatProperty,
	EnumProperty,
	CollectionProperty
)

from bpy.types import (
	OperatorFileListElement,
)

from bpy_extras.io_utils import (
	ImportHelper,
	ExportHelper,
	orientation_helper,
	axis_conversion
)

if "bpy" in locals():
	import importlib
	if "bz2msh" in locals(): importlib.reload(bz2msh)
	if "bz2pak" in locals(): importlib.reload(bz2pak)
	if "softimage_pic" in locals(): importlib.reload(softimage_pic)
	if "msh_blender_importer" in locals(): importlib.reload(msh_blender_importer)

def pak_msh_items(self, context):
	filepath = getattr(self, "filepath", "")
	if not filepath or not filepath.casefold().endswith(".pak") or not os.path.exists(filepath):
		return [("", "Select a .pak file", "")]

	try:
		from . import bz2pak
		archive = bz2pak.PakArchive.read(filepath)
		paths = archive.list_paths(extension=".msh")
		if not paths:
			return [("", "No .msh assets in archive", "")]
		return [(path, path, "") for path in paths]
	except Exception as exc:
		return [("", f"PAK read failed: {exc}", "")]

class ImportMSH(bpy.types.Operator, ImportHelper):
	"""Import BZ2 MSH file"""
	bl_idname = "import_scene.io_scene_bz2msh"
	bl_label = "Import MSH"
	bl_options = {"UNDO", "PRESET"}
	
	directory: StringProperty(subtype="DIR_PATH")
	filename_ext = ".msh"
	filter_glob: StringProperty(default="*.msh;*.pak", options={"HIDDEN"})
	texture_image_ext_default = ".pic .png .bmp .jpg .jpeg .gif .tga .dds .dxtbz2"

	pak_msh_path: EnumProperty(
		name="Archive Asset",
		description="MSH asset inside the selected PAK archive",
		items=pak_msh_items
	)

	pak_cache_dir: StringProperty(
		name="PAK Cache",
		description="Optional directory used to cache extracted PAK contents",
		subtype="DIR_PATH",
		default=""
	)
	
	files: CollectionProperty(
		name="File Path",
		type=OperatorFileListElement,
	)
	
	import_collection: BoolProperty(
		name="Create Collection",
		description="Import into collection",
		default=False
	)
	
	import_mode: EnumProperty(
		items=(
			("GLOBAL", "Global Mesh", "Import the global mesh"),
			("LOCAL", "Local Meshes", "Import local meshes (with object hierarchy)")
		),
		default="LOCAL",
		name="Import Mode",
		description="Each import mode has a compromise."
	)
	
	data_from_faces: BoolProperty(
		name="Data from faces",
		description="Import mesh data from loop indices instead of raw block data",
		default=False
	)
		
	import_mesh_normals: BoolProperty(
		name="Normals",
		description="Import mesh normals",
		default=True
	)
	
	import_mesh_vertcolor: BoolProperty(
		name="Vertex Colors",
		description="Import mesh vertex colors",
		default=True
	)
	
	import_mesh_materials: BoolProperty(
		name="Materials",
		description="Import mesh face materials",
		default=True
	)
	
	import_mesh_uvmap: BoolProperty(
		name="UV Maps",
		description="Import mesh texture coordinates",
		default=True
	)
	
	find_textures: BoolProperty(
		name="Recursive Image Search",
		description="Search subdirectories for any associated images (Slow for big directories)",
		default=False
	)
	
	find_textures_ext: StringProperty(
		name="Formats",
		description="Additional file extensions to check for",
		default=texture_image_ext_default
	)

	auto_convert_dxtbz2: BoolProperty(
		name="Auto-convert .dxtbz2",
		description="Automatically strip headers from .dxtbz2 files to create .dds files",
		default=True,
	)

	convert_pic_textures: BoolProperty(
		name="Convert PIC to PNG",
		description="Decode Softimage PIC textures and save PNG copies next to the source images",
		default=True
	)
	
	place_at_cursor: BoolProperty(
		name="Place at Cursor",
		description="Imported objects are placed at cursor if enabled, otherwise at center",
		default=False
	)
	
	rotate_for_yz: BoolProperty(
		name="Rotate Root Frames",
		description="Rotate root frames so they match blender's world orientation",
		default=True
	)
	
	import_animations: BoolProperty(
		name="Import Animations",
		description="Import object transform animations from MSH (if present)",
		default=False
	)
	
	def multi_select_files(self):
		multi_select = [os.path.join(self.directory, file_elem.name) for file_elem in self.files]
		multi_select = [path for path in multi_select if os.path.isfile(path)]
		return multi_select if len(multi_select) >= 2 else []
	
	def draw(self, context):
		layout = self.layout
		is_pak = self.filepath.casefold().endswith(".pak")
		multi_select = self.multi_select_files()

		if is_pak:
			pak_layout = layout.box()
			pak_layout.label(text="PAK Asset Selection", icon="PACKAGE")
			pak_layout.prop(self, "pak_msh_path")
			pak_layout.prop(self, "pak_cache_dir")
			layout.separator()
		
		layout.prop(self, "import_mode", expand=True)
		if self.import_mode == "GLOBAL":
			layout.prop(self, "data_from_faces")
		
		sub = layout.column()
		if multi_select:
			layout.label(text="%d files will be imported as collections." % len(multi_select))
		else:
			sub.prop(self, "import_collection", icon="COLLECTION_NEW")
		
		layout.separator()
		
		mesh_layout = layout.box()
		mesh_layout.label(text="Mesh Data", icon='MESH_DATA')
		sub = mesh_layout.column()
		sub.prop(self, "import_mesh_normals", icon="NORMALS_VERTEX")
		sub.prop(self, "import_mesh_vertcolor", icon="GROUP_VCOL")
		sub.prop(self, "import_mesh_materials", icon="MATERIAL_DATA")
		sub.prop(self, "import_mesh_uvmap", icon="GROUP_UVS")
		
		layout.separator()
		
		texture_layout = layout.box()
		texture_layout.label(text="Texture Settings", icon='TEXTURE_DATA')
		sub = texture_layout.column()
		sub.enabled = self.import_mesh_materials
		sub.prop(self, "find_textures", icon="TEXTURE_DATA")
		sub.prop(self, "find_textures_ext")
		sub.prop(self, "convert_pic_textures", icon="FILE_IMAGE")
		sub.prop(self, "auto_convert_dxtbz2", icon="FILE_REFRESH")

		layout.separator()
		
		anim_layout = layout.box()
		anim_layout.label(text="Animations", icon='ACTION')
		sub = anim_layout.column()
		sub.prop(self, "import_animations", icon="ACTION")
		
		layout.separator()
		
		layout.prop(self, "place_at_cursor", icon="PIVOT_CURSOR")
		layout.prop(self, "rotate_for_yz", icon="ORIENTATION_GLOBAL")
	
	def execute(self, context):
		from . import msh_blender_importer
		keywords = self.as_keywords(ignore=("filter_glob", "directory", "pak_msh_path", "pak_cache_dir"))
		keywords["multi_select"] = self.multi_select_files()

		if self.filepath.casefold().endswith(".pak"):
			from . import bz2pak

			if not self.pak_msh_path:
				self.report({"ERROR"}, "Select an MSH asset inside the PAK archive")
				return {"CANCELLED"}

			cache_dir = self.pak_cache_dir.strip() if self.pak_cache_dir else None
			archive, extract_root = bz2pak.ensure_extracted(self.filepath, cache_dir or None)
			extracted_path = archive.extract_entry(self.pak_msh_path, extract_root, overwrite=False)
			keywords["filepath"] = extracted_path
			keywords["find_textures"] = True
			keywords["texture_search_root"] = extract_root

		return msh_blender_importer.load(self, context, **keywords)

class ExtractPAK(bpy.types.Operator, ImportHelper):
	"""Extract Battlezone II PAK archive"""
	bl_idname = "import_scene.io_scene_bz2pak_extract_msh"
	bl_label = "Extract PAK"
	bl_options = {"PRESET"}

	filename_ext = ".pak"
	filter_glob: StringProperty(default="*.pak", options={"HIDDEN"})

	output_dir: StringProperty(
		name="Output Directory",
		description="Directory to extract the archive contents into",
		subtype="DIR_PATH",
		default=""
	)

	def draw(self, context):
		layout = self.layout
		layout.prop(self, "output_dir")

	def execute(self, context):
		from . import bz2pak

		output_dir = self.output_dir.strip() if self.output_dir else ""
		if not output_dir:
			output_dir = os.path.join(
				os.path.dirname(self.filepath),
				os.path.splitext(os.path.basename(self.filepath))[0]
			)

		archive = bz2pak.PakArchive.read(self.filepath)
		archive.extract_all(output_dir, overwrite=True)
		self.report({"INFO"}, f"Extracted {len(archive.entries)} files to {output_dir}")
		return {"FINISHED"}

def menu_func_import(self, context):
	self.layout.operator(ImportMSH.bl_idname, text="BZ2 MSH / PAK (.msh, .pak)")
	self.layout.operator(ExtractPAK.bl_idname, text="Battlezone II PAK Extractor (.pak)")

def register():
	bpy.utils.register_class(ImportMSH)
	bpy.utils.register_class(ExtractPAK)
	bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
	bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
	bpy.utils.unregister_class(ExtractPAK)
	bpy.utils.unregister_class(ImportMSH)

if __name__ == "__main__":
	register()
