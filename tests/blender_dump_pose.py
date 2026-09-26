"""Headless: import a skinned .msh with animations and dump evaluated skin vertices.
usage: blender -b --factory-startup -P tests/blender_dump_pose.py -- <file.msh> <out.npz> <clip:frame,clip:frame,...>"""
import bpy, sys, os
import numpy as np
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(REPO))
from importlib import import_module
imp = import_module(os.path.basename(REPO) + ".msh_blender_importer")
a = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
imp.load(None, bpy.context, filepath=a[0], import_collection=False, import_mode="LOCAL", data_from_faces=False,
         import_mesh_normals=False, import_mesh_vertcolor=False, import_mesh_materials=False, import_mesh_uvmap=False,
         find_textures=False, find_textures_ext=".dds", auto_convert_dxtbz2=False, convert_pic_textures=False,
         place_at_cursor=False, rotate_for_yz=True, import_animations=True)
sc = bpy.context.scene
arm = next(o for o in sc.objects if o.type == "ARMATURE"); skin = next(o for o in sc.objects if o.type == "MESH")
out = {}
for item in a[2].split(","):
    clip, fr = item.split(":"); fr = float(fr)
    act = next(x for x in bpy.data.actions if x.name.endswith("|" + clip))
    arm.animation_data.action = act; arm.animation_data.action_slot = act.slots[0]
    sc.frame_set(int(fr), subframe=fr - int(fr)); bpy.context.view_layer.update()
    ev = skin.evaluated_get(bpy.context.evaluated_depsgraph_get()); me = ev.to_mesh()
    P = np.array([tuple(ev.matrix_world @ v.co) for v in me.vertices]); ev.to_mesh_clear()
    out[item] = P
np.savez(a[1], **out)
print("DUMPED", list(out))
