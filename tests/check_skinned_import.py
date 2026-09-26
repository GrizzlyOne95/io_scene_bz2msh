"""Verify a skinned import against the raw .msh keys, independently of Blender.

1. Run blender_dump_pose.py to save the evaluated skin vertices of some clip:frame pairs.
2. python tests/check_skinned_import.py <file.msh> <poses.npz>

The reference here re-implements MSH skinning with numpy only:
  - bind(node) = inverse(state_matrix) (row-vector form -> transposed);
  - a key is the node transform relative to its parent node: position keys (type 1/3)
    give the translation, rotation keys (type 2/3) store the conjugate quaternion;
    channels without keys keep the bind-local value;
  - skin = sum(w * world(node) @ bind(node)^-1 @ v) over vert_to_state;
and converts to Blender space with the importer's Y/Z swap.
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bz2msh


def M(m): return np.array([list(r) for r in m])


def quat_matrix(x, y, z, w):
    n = np.sqrt(x * x + y * y + z * z + w * w); x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def slerp(a, b, t):
    a = np.asarray(a, float); b = np.asarray(b, float)
    d = float(np.dot(a, b))
    if d < 0: b, d = -b, -d
    if d > 0.9995: q = a + t * (b - a); return q / np.linalg.norm(q)
    th = np.arccos(d); return (np.sin((1 - t) * th) * a + np.sin(t * th) * b) / np.sin(th)


def sample(keys, f, interp):
    if f <= keys[0][0]: return keys[0][1]
    for (f0, a), (f1, b) in zip(keys, keys[1:]):
        if f0 <= f <= f1: return interp(a, b, 0.0 if f1 == f0 else (f - f0) / (f1 - f0))
    return keys[-1][1]


def skin(block, clip, frame):
    nodes = [me for me, _ in block.walk()]
    parent = {c.state_index.value: me.state_index.value for me in nodes for c in me.meshes}
    bind = {me.state_index.value: np.linalg.inv(M(block.state_matrices[me.state_index.value]).T) for me in nodes}
    local = {i: (B if i not in parent else np.linalg.inv(bind[parent[i]]) @ B) for i, B in bind.items()}
    anim = next(a for a in block.animation_list if a.name == clip)
    for s in anim.animations:
        i = s.index.value; L = local[i].copy()
        pk = [(k.frame, np.array([k.vect.x, k.vect.y, k.vect.z])) for k in s.states if k.type in (1, 3)]
        rk = [(k.frame, np.array([-k.quat.x, -k.quat.y, -k.quat.z, k.quat.s])) for k in s.states if k.type in (2, 3)]
        if pk: L[:3, 3] = sample(pk, frame, lambda a, b, t: a + (b - a) * t)
        if rk: L[:3, :3] = quat_matrix(*sample(rk, frame, slerp))
        local[i] = L
    W = {}
    for me in nodes:
        i = me.state_index.value
        W[i] = local[i] if i not in parent else W[parent[i]] @ local[i]
    V = np.c_[np.array([list(v) for v in block.vertices]), np.ones(len(block.vertices))]
    S = np.zeros((len(V), 3))
    for vi, entry in enumerate(block.vert_to_state):
        for a in entry.array:
            S[vi] += a.weight * (W[a.index] @ np.linalg.inv(bind[a.index]) @ V[vi])[:3]
    return np.c_[S[:, 0], S[:, 2], S[:, 1]]   # BZ2 -> Blender (importer's Rotate Root Frames)


if __name__ == "__main__":
    block = next(b for b in bz2msh.MSH(sys.argv[1]).blocks if b.msh_header.skinned)
    poses = np.load(sys.argv[2]); worst = 0.0
    for key in poses.files:
        clip, frame = key.rsplit(":", 1)
        e = float(np.abs(skin(block, clip, float(frame)) - poses[key]).max())
        worst = max(worst, e)
        print(f"{key:14s} max vertex error {e * 1000:.3f} mm")
    print(f"WORST {worst * 1000:.3f} mm")
    sys.exit(0 if worst < 1e-3 else 1)
