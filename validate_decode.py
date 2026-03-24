import argparse
import math
import pathlib

import bz2msh


def is_finite_matrix(matrix):
	for row_name in ("right", "up", "front", "posit"):
		row = getattr(matrix, row_name)
		for value in row:
			if not math.isfinite(value):
				return False
	return True


def summarize_file(path):
	msh = bz2msh.MSH(str(path))
	block = msh.blocks[0]
	meshes = list(block.walk())
	nodes_by_state = {}
	duplicate_states = {}
	invalid_matrices = []
	geometry_nodes = 0
	animated_nodes = set()
	missing_targets = {}

	for mesh, _level in meshes:
		state_index = mesh.state_index.value
		if state_index in nodes_by_state:
			duplicate_states.setdefault(state_index, [nodes_by_state[state_index].name])
			duplicate_states[state_index] += [mesh.name]
		else:
			nodes_by_state[state_index] = mesh

		if len(mesh.vertex):
			geometry_nodes += 1
		if not is_finite_matrix(mesh.matrix):
			invalid_matrices += [mesh.name]

	for anim in block.animation_list:
		for sub_anim in anim.animations:
			target = sub_anim.index.value
			if target in nodes_by_state:
				animated_nodes.add(target)
			else:
				missing_targets.setdefault(anim.name, [])
				missing_targets[anim.name] += [target]

	return {
		"path": str(path),
		"root": block.root.name if block.root else None,
		"synthetic_root": block.synthetic_root,
		"skinned_section": bool(block.skinned_section),
		"node_count": len(meshes),
		"geometry_nodes": geometry_nodes,
		"clip_count": len(block.animation_list),
		"animated_node_count": len(animated_nodes),
		"duplicate_states": duplicate_states,
		"invalid_matrices": invalid_matrices,
		"missing_targets": missing_targets,
	}


def main():
	parser = argparse.ArgumentParser(description="Validate decoded BZ2 MSH transforms and animation targets.")
	parser.add_argument("paths", nargs="+", help="MSH files to validate")
	args = parser.parse_args()

	for raw_path in args.paths:
		path = pathlib.Path(raw_path)
		summary = summarize_file(path)
		print(f"\nFILE {summary['path']}")
		print(
			f"  root={summary['root']} synthetic_root={summary['synthetic_root']} "
			f"skinned_section={summary['skinned_section']}"
		)
		print(
			f"  nodes={summary['node_count']} geometry_nodes={summary['geometry_nodes']} "
			f"clips={summary['clip_count']} animated_nodes={summary['animated_node_count']}"
		)
		print(f"  invalid_matrices={len(summary['invalid_matrices'])}")
		if summary["invalid_matrices"]:
			print(f"    {summary['invalid_matrices']}")
		print(f"  duplicate_state_indices={len(summary['duplicate_states'])}")
		if summary["duplicate_states"]:
			for state_index, names in sorted(summary["duplicate_states"].items()):
				print(f"    state {state_index}: {names}")
		print(f"  clips_with_missing_targets={len(summary['missing_targets'])}")
		if summary["missing_targets"]:
			for clip_name, targets in sorted(summary["missing_targets"].items()):
				unique_targets = sorted(set(targets))
				print(f"    {clip_name}: {unique_targets}")


if __name__ == "__main__":
	main()
