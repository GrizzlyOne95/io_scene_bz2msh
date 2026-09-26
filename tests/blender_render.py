"""Headless: import a .msh with this checkout and render an overview (front/side/top/3-4).
usage: blender -b --factory-startup -P tests/blender_render.py -- <file.msh> <out.png> [LOCAL|GLOBAL] [action frame]"""
import bpy, sys, os, math
from mathutils import Vector
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(REPO))
from importlib import import_module
imp = import_module(os.path.basename(REPO) + ".msh_blender_importer")
a = sys.argv[sys.argv.index("--") + 1:]
path, out = a[0], a[1]; mode = a[2] if len(a) > 2 else "LOCAL"
action = a[3] if len(a) > 3 else None; frame = float(a[4]) if len(a) > 4 else 0
bpy.ops.wm.read_factory_settings(use_empty=True)
imp.load(None, bpy.context, filepath=path, import_collection=False, import_mode=mode, data_from_faces=False,
         import_mesh_normals=True, import_mesh_vertcolor=True, import_mesh_materials=True, import_mesh_uvmap=True,
         find_textures=True, find_textures_ext=".dds .tga .png .pic .dxtbz2", auto_convert_dxtbz2=True, convert_pic_textures=True,
         place_at_cursor=False, rotate_for_yz=True, import_animations=action is not None)
sc = bpy.context.scene
if action:
    for ob in sc.objects:
        if ob.animation_data:
            act = next((x for x in bpy.data.actions if x.name.endswith("|" + action)), None)
            if act:
                ob.animation_data.action = act
                sl = next((s for s in act.slots if s.name_display == ob.name), None)
                if sl: ob.animation_data.action_slot = sl
    sc.frame_set(int(frame), subframe=frame - int(frame))
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
pts = []
for ob in sc.objects:
    if ob.type == "MESH":
        ev = ob.evaluated_get(dg); me = ev.to_mesh(); pts += [ev.matrix_world @ v.co for v in me.vertices]; ev.to_mesh_clear()
lo = Vector([min(p[k] for p in pts) for k in range(3)]); hi = Vector([max(p[k] for p in pts) for k in range(3)])
c = (lo + hi) / 2; size = max(hi - lo) * 1.15
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.6, 0.63, 0.68, 1)
for rot, e in (((50, 0, 30), 3.0), ((120, 0, 210), 1.0)):
    ld = bpy.data.lights.new("s", "SUN"); ld.energy = e
    lo_ = bpy.data.objects.new("s", ld); lo_.rotation_euler = [math.radians(x) for x in rot]; sc.collection.objects.link(lo_)
cd = bpy.data.cameras.new("c"); cd.type = "ORTHO"; cd.ortho_scale = size
cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam); sc.camera = cam
sc.render.engine = "BLENDER_EEVEE"; sc.render.resolution_x = sc.render.resolution_y = 500
sc.view_settings.view_transform = "Standard"
views = {"front": (90, 0, 180), "side": (90, 0, 90), "top": (0, 0, 0), "q34": (65, 0, 135)}
tiles = []
for name, (rx, ry, rz) in views.items():
    cam.rotation_euler = [math.radians(x) for x in (rx, ry, rz)]
    cam.location = c + cam.rotation_euler.to_matrix() @ Vector((0, 0, 50))
    f = out.replace(".png", f"_{name}.png"); sc.render.filepath = f; bpy.ops.render.render(write_still=True); tiles.append(f)
import numpy as np
imgs = [bpy.data.images.load(t) for t in tiles]
W = 500; arr = np.zeros((W, W * 4, 4), np.float32)
for k, im in enumerate(imgs):
    px = np.array(im.pixels[:], np.float32).reshape(W, W, 4); arr[:, k * W:(k + 1) * W] = px
sheet = bpy.data.images.new("sheet", W * 4, W, alpha=True); sheet.pixels = arr.ravel(); sheet.filepath_raw = out; sheet.file_format = "PNG"; sheet.save()
for t in tiles: os.remove(t)
print("RENDERED", out)
