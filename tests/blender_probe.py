"""Headless probe: import .msh files with this checkout and print what came in.
usage: blender -b --factory-startup -P tests/blender_probe.py -- <file.msh> [LOCAL|GLOBAL] [anim]"""
import bpy, sys, os
from mathutils import Vector
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(REPO))
mod = __import__(os.path.basename(REPO))
from importlib import import_module
imp = import_module(os.path.basename(REPO) + ".msh_blender_importer")
argv = sys.argv[sys.argv.index("--") + 1:]
path = argv[0]; mode = argv[1] if len(argv) > 1 else "LOCAL"; anim = len(argv) > 2 and argv[2] == "anim"
bpy.ops.wm.read_factory_settings(use_empty=True)
opt = dict(import_collection=False, import_mode=mode, data_from_faces=False, import_mesh_normals=True,
           import_mesh_vertcolor=True, import_mesh_materials=True, import_mesh_uvmap=True, find_textures=False,
           find_textures_ext=".dds .tga .png .pic .dxtbz2", auto_convert_dxtbz2=False, convert_pic_textures=False,
           place_at_cursor=False, rotate_for_yz=True, import_animations=anim)
imp.load(None, bpy.context, filepath=path, **opt)
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
lo = Vector((1e9,) * 3); hi = Vector((-1e9,) * 3); nv = 0
for ob in bpy.context.scene.objects:
    if ob.type != "MESH": continue
    ev = ob.evaluated_get(dg); me = ev.to_mesh()
    for v in me.vertices:
        w = ev.matrix_world @ v.co; nv += 1
        lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
    ev.to_mesh_clear()
print("PROBE", os.path.basename(path), mode, "objects", len(bpy.context.scene.objects),
      "types", sorted({o.type for o in bpy.context.scene.objects}), "verts", nv,
      "bbox", [round(x, 3) for x in lo], [round(x, 3) for x in hi])
for ob in bpy.context.scene.objects:
    if ob.type == "ARMATURE":
        print("ARMATURE", ob.name, len(ob.data.bones), "bones; actions", [a.name for a in bpy.data.actions][:20])
