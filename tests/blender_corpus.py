"""Headless smoke test: import every .msh under a folder, LOCAL (with animations) and GLOBAL.
usage: blender -b --factory-startup -P tests/blender_corpus.py -- <folder> [limit]
Prints one line per failure and a summary; exit code 1 if anything raised."""
import bpy, sys, os, glob, traceback
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(REPO))
from importlib import import_module
imp = import_module(os.path.basename(REPO) + ".msh_blender_importer")
a = sys.argv[sys.argv.index("--") + 1:]
files = sorted(glob.glob(os.path.join(a[0], "**", "*.msh"), recursive=True))
if len(a) > 1: files = files[:int(a[1])]
BASE = dict(import_collection=False, data_from_faces=False, import_mesh_normals=True, import_mesh_vertcolor=True,
            import_mesh_materials=True, import_mesh_uvmap=True, find_textures=False, find_textures_ext=".dds",
            auto_convert_dxtbz2=False, convert_pic_textures=False, place_at_cursor=False, rotate_for_yz=True)
fails = 0; rigs = 0; objs = 0
for i, path in enumerate(files):
    for mode, anim in (("LOCAL", True), ("GLOBAL", False)):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        try:
            imp.load(None, bpy.context, filepath=path, import_mode=mode, import_animations=anim, **BASE)
            objs += len(bpy.context.scene.objects)
            rigs += sum(1 for o in bpy.context.scene.objects if o.type == "ARMATURE")
        except Exception as e:
            fails += 1
            print("FAIL", mode, path, type(e).__name__, str(e)[:120])
            traceback.print_exc(limit=2)
    if i % 50 == 0: print("progress", i, "/", len(files), flush=True)
print(f"CORPUS files {len(files)} imports {2 * len(files)} failures {fails} armatures {rigs} objects {objs}")
sys.exit(1 if fails else 0)
