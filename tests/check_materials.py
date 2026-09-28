"""Headless check of .material file support: every map a BZ2R/BZCC .material file names that exists
on disk must end up as a non-empty image node linked into the material (teamcolor: present only).
usage: blender -b --factory-startup -P tests/check_materials.py -- <msh folder> [texture folder] [limit]
Exit code 1 on any missing/empty map."""
import bpy, sys, os, glob
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(REPO))
from importlib import import_module
imp = import_module(os.path.basename(REPO) + ".msh_blender_importer")
a = sys.argv[sys.argv.index("--") + 1:]
folder = a[0]
tex_root = a[1] if len(a) > 1 and os.path.isdir(a[1]) else None
limit = int(a[-1]) if a[-1].isdigit() else None
files = sorted(glob.glob(os.path.join(folder, "**", "*.msh"), recursive=True))[:limit]
OPT = dict(import_collection=False, data_from_faces=False, import_mesh_normals=True, import_mesh_vertcolor=True,
           import_mesh_materials=True, import_mesh_uvmap=True, find_textures=False,
           find_textures_ext=".dds .tga .png .bmp .pic .dxtbz2", auto_convert_dxtbz2=False,
           convert_pic_textures=False, place_at_cursor=False, rotate_for_yz=True, import_mode="LOCAL",
           import_animations=False)
if tex_root:
	OPT["texture_search_root"] = tex_root
stats = dict(files=0, material_files=0, maps=0, linked=0, bcn=0, solid=0)
problems = []
for path in files:
	bpy.ops.wm.read_factory_settings(use_empty=True)
	imp.load(None, bpy.context, filepath=path, **OPT)
	stats["files"] += 1
	search = [os.path.dirname(path), os.path.join(os.path.dirname(path), "textures")] + ([tex_root] if tex_root else [])
	for mat in bpy.data.materials:
		if mat.name.startswith("Solid_"): stats["solid"] += 1
		if not mat.name.casefold().endswith(".material"): continue
		mfile = os.path.join(os.path.dirname(path), mat.name)
		if not os.path.exists(mfile): continue
		stats["material_files"] += 1
		maps = imp.read_material_file(mfile)
		nodes = [n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE"]
		for which, tex in maps.items():
			if not tex or not any(os.path.exists(os.path.join(d, tex)) for d in search): continue
			stats["maps"] += 1
			node = next((n for n in nodes if n.label.startswith(which + ":")), None)
			if node is None or node.image is None:
				problems.append(f"{os.path.basename(path)} {mat.name}: {which} {tex} has no image node"); continue
			if tuple(node.image.size) == (0, 0):
				problems.append(f"{os.path.basename(path)} {mat.name}: {which} {tex} loaded empty"); continue
			if "bcn_source" in node.image: stats["bcn"] += 1
			if which == "teamcolor" or any(l.from_node == node for l in mat.node_tree.links):
				stats["linked"] += 1
			else:
				problems.append(f"{os.path.basename(path)} {mat.name}: {which} not linked")
for p in problems[:40]: print("PROBLEM", p)
print("MATERIALS", " ".join(f"{k} {v}" for k, v in stats.items()), "problems", len(problems))
sys.exit(1 if problems else 0)
