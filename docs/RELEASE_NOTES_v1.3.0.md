# Battlezone II MSH Importer v1.3.0

## Summary

v1.3.0 moves the project fully onto Blender's current Extensions packaging model while collecting the major importer correctness work added after v1.2.0.

The extension continues to target Blender 4.5 LTS and later.

## Blender Extension Packaging

- `blender_manifest.toml` is now the authoritative package metadata.
- Removed legacy `bl_info` metadata from `__init__.py`.
- Updated the manifest to v1.3.0 and current Extension schema fields.
- Added an explicit runtime build file list so development files are excluded from release ZIPs.
- Replaced the hand-written ZIP release step with Blender's native `extension validate` and `extension build` commands.
- Added pull-request and `main` CI that validates the source manifest, builds the extension, validates the built ZIP, and checks the exact package contents.
- Release CI is pinned to Blender 4.5.14 LTS and verifies the Git tag matches the manifest version.

## Importer Improvements Since v1.2.0

- Corrected MSH hierarchy parsing using the file's actual bracketed node structure.
- Corrected BZ2-to-Blender coordinate conversion for geometry, normals, hierarchy transforms, and winding.
- Added skinned-model import as Blender Armatures with weighted meshes.
- Corrected position-only, rotation-only, and combined animation key handling.
- Prevented unkeyed channels from leaking transforms between rigid animation clips.
- Corrected duplicate animation tracks targeting the same state index.
- Restored BZ2R/BZCC `.material` support.
- Added BC4/BC5 DDS decoding, including BC5 normal-Z reconstruction.
- Preserved unnamed flat-colour materials independently.
- Fixed multi-file MSH importing.
- Hardened imports against degenerate triangles.
- Added corpus, render, material, and independent skinning validation tools.

## Installation

1. Download `io_scene_bz2msh-v1.3.0.zip` from the GitHub Release.
2. In Blender 4.5+, open **Edit > Preferences > Extensions**.
3. Open the Extensions menu and choose **Install from Disk...**.
4. Select the downloaded ZIP.
5. Enable **Battlezone II MSH Importer**.

Do not use GitHub's generic source-code ZIP as the install package.

## Licensing Note

This release preserves the repository's existing `SPDX:MIT` manifest declaration. Official submission to `extensions.blender.org` is intentionally out of scope until the inherited-code licensing/provenance is resolved.
