"""Headless: per-object world bbox after import (LOCAL mode, no animation).
usage: blender -b --factory-startup -P tests/blender_objects.py -- <file.msh>"""
import bpy, sys, os
from mathutils import Vector
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(REPO))
from importlib import import_module
imp = import_module(os.path.basename(REPO) + ".msh_blender_importer")
path = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
imp.load(None, bpy.context, filepath=path, import_collection=False, import_mode="LOCAL", data_from_faces=False,
         import_mesh_normals=True, import_mesh_vertcolor=True, import_mesh_materials=False, import_mesh_uvmap=True,
         find_textures=False, find_textures_ext=".dds", auto_convert_dxtbz2=False, convert_pic_textures=False,
         place_at_cursor=False, rotate_for_yz=True, import_animations=False)
bpy.context.view_layer.update()
for ob in bpy.context.scene.objects:
    if ob.type != "MESH": continue
    P = [ob.matrix_world @ v.co for v in ob.data.vertices]
    lo = [round(min(p[k] for p in P), 2) for k in range(3)]; hi = [round(max(p[k] for p in P), 2) for k in range(3)]
    print("OBJ", ob.name, "parent", ob.parent.name if ob.parent else None, len(P), lo, hi)
