Forked from https://github.com/frute94/io_scene_bz2msh/tree/main

# Battlezone II / Combat Commander MSH Importer for Blender 4.5 LTS

A Blender 4.5+ Extension for importing Battlezone II and Battlezone: Combat Commander `.msh` assets, including rigid hierarchy animation, skinned meshes, BZ2/BZCC materials and textures, and assets stored inside `.pak` archives.

The importer is aimed at bringing game assets into Blender in a form that is useful for inspection, animation work, conversion, and further modding rather than only producing a static mesh.

## Highlights

- **Loose MSH and PAK import:** Import individual `.msh` files or browse MSH assets directly inside Battlezone II `.pak` archives.
- **Correct BZ2 hierarchy parsing:** The node stream is parsed as the bracketed hierarchy used by the game/exporter, preserving parent/child/sibling relationships.
- **Rigid and skinned models:** Rigid assets import as Blender object hierarchies; skinned assets can import as an Armature plus a weighted mesh.
- **Animation clips:** Embedded clips import as Blender Actions using Blender 4.5 Action Slots.
- **Channel-aware animation keys:** Position-only, rotation-only, and combined MSH keys are handled independently, with linear interpolation and rest-channel resets to avoid pose bleed between clips.
- **Blender-space conversion:** With **Rotate Root Frames** enabled, mesh positions, normals, object transforms, bind data, and animation channels are converted from BZ2 space into Blender space. Face winding is corrected for BZ2's left-handed coordinate system.
- **Global and local import modes:** Use a single global mesh for fast static inspection, or preserve the full local hierarchy for moving parts, hardpoints, animations, and rigs.
- **Multiple materials:** Face material assignments are preserved instead of collapsing the asset to one material.
- **BZ2R / BZCC `.material` support:** Diffuse, specular, normal, and emissive maps are wired into Principled BSDF materials. Team-colour masks are imported as image nodes for inspection/use.
- **BC4 / BC5 DDS decoding:** BC4/BC5 textures that Blender cannot load natively are decoded by the extension. BZCC BC5_SNORM normal maps have their Z component reconstructed automatically.
- **DXTBZ2 textures:** Supported `.dxtbz2` textures can be converted to DDS on demand.
- **Softimage PIC textures:** Older `.pic` textures are decoded directly and can optionally be cached as PNG.
- **Multi-file import:** Selecting multiple loose MSH files imports each asset as its own collection.
- **PAK extraction:** A separate PAK extractor is available from Blender's Import menu.

## Current Development State

The current development target is **v1.3.0**. The add-on now uses the Blender Extensions manifest as its authoritative package metadata: legacy `bl_info` metadata has been removed, and CI validates/builds the package with Blender's native `extension validate` and `extension build` commands.

The formal **v1.2.0** release predates the newer hierarchy, skinned-armature, animation-correction, BZ2R `.material`, BC4/BC5, and native Extensions-packaging work. Those changes are being prepared for the next packaged release.

## Installation

### Packaged release

For normal installation, use the ZIP attached to a GitHub Release rather than GitHub's generic **Code > Download ZIP** archive.

1. Open the repository's **Releases** page.
2. Download the packaged extension ZIP, for example `io_scene_bz2msh-v1.2.0.zip`.
3. In Blender 4.5+, open **Edit > Preferences > Extensions**.
4. Open the Extensions menu and choose **Install from Disk...**.
5. Select the downloaded ZIP and enable **Battlezone II MSH Importer**.

The release archive is built with Blender's native Extensions tooling and contains `blender_manifest.toml` and `__init__.py` at the archive root. The release workflow validates both the source manifest and the final ZIP with the pinned Blender 4.5 LTS CLI before publishing.

### Development checkout

If you are developing from this repository while Blender is loading a separately installed copy from `%APPDATA%`, keep the installed extension synchronized with:

```powershell
.\sync_installed_extension.ps1
```

This avoids testing an older installed copy when the repository parser/importer has already changed.

## Usage

### Import an MSH or an asset from a PAK

1. In Blender, go to **File > Import > BZ2 MSH / PAK (.msh, .pak)**.
2. Select a loose `.msh` file, multiple loose `.msh` files, or a `.pak` archive.
3. For a PAK, choose the in-archive MSH from **Archive Asset**.
4. Configure the import options and import.

When a PAK asset is imported, the archive contents are extracted to a cache location so referenced textures/materials can be resolved with the mesh.

### Extract a PAK

Use **File > Import > Battlezone II PAK Extractor (.pak)** to extract an archive without importing a model.

## Important Import Options

- **Import Animations:** Imports embedded MSH clips as Actions. Rigid assets receive object Actions; skinned assets receive bone Actions.
- **Skinned as Armature:** Enabled by default. Imports skinned blocks as an Armature plus the block-level weighted mesh instead of a set of rigid node meshes.
- **Global Mesh:** Builds one mesh from the block. Useful for static review and quick geometry inspection.
- **Local Meshes:** Preserves the complete object hierarchy. This is the preferred mode for hardpoints, moving parts, deploy/retract animation, and skinned assets.
- **Rotate Root Frames:** Converts BZ2 coordinate data into Blender-space orientation. Leave this enabled unless you explicitly need raw source-space data.
- **Normals / Vertex Colors / Materials / UV Maps:** Toggle individual mesh-data channels.
- **Recursive Image Search:** Searches for associated images beyond the immediate asset folder. This can be slow on large trees.
- **Auto-convert .dxtbz2:** Converts supported DXT-BZ2 textures to DDS when needed.
- **Convert PIC to PNG:** Decodes Softimage PIC textures and optionally saves PNG copies for faster reuse.

## Materials and Texture Lookup

The importer supports both older single-texture material references and newer BZ2R/BZCC `.material` files.

For `.material` assets, the importer recognizes:

- `diffuse`
- `specular`
- `normal`
- `emissive`
- `teamcolor`

Texture lookup includes the asset directory, common `bitmaps` paths, BZ2R-style `Textures` paths, and any configured search root such as an extracted PAK cache.

Unnamed MSH materials are kept distinct by colour using names such as `Solid_<rrggbb>` rather than being collapsed into a single default material.

## Animation and Skinning Notes

Rigid MSH animation is object-transform based. Animated nodes import as separate Blender objects with Actions.

Skinned blocks carry:

- one weight list per block vertex in `vert_to_state`;
- per-node inverse bind matrices in `state_matrices`;
- animation tracks addressed by node/state index.

With **Skinned as Armature**, the importer creates the armature rest pose from the bind data, builds vertex groups from the MSH weights, and imports each clip as a bone Action.

MSH animation keys use:

- `1` = position;
- `2` = rotation;
- `3` = position + rotation.

The stored quaternion is interpreted as the conjugate of the local rotation used by the row-vector MSH transform data. Keys are relative to the parent node and use linear interpolation.

A small number of assets contain duplicate key tracks for the same node index. For each channel, the last applicable track in file order wins, matching the validated skinning reference path.

### Known research point

For skinned clips, channels not keyed by a clip currently hold the bind-local value derived from `state_matrices`. Some assets contain a different posed transform in the node matrices, so the exact engine behavior for those unkeyed channels is still an open reverse-engineering question.

## Validation

The current parser/importer work includes headless Blender and independent reference checks.

Notable coverage includes:

- hierarchy round-trip checks across the BZ2R/Workshop MSH corpus;
- local and global Blender corpus imports;
- render overview generation;
- independent numpy skinning comparison against evaluated Blender poses;
- BZ2R/BZCC material-map loading checks;
- BC4/BC5 texture decode validation.

The hierarchy work was checked against **815 MSH files** from the BZ2R/Workshop corpus, and the corrected reader preserves the node trees written by the format.

## Repository Structure

- `__init__.py` — Blender Extension registration, UI, import operators, multi-file handling, and PAK extraction entry points.
- `blender_manifest.toml` — Blender 4.5 Extension metadata and permissions.
- `bz2msh.py` — Low-level Battlezone II MSH parser and format structures.
- `msh_blender_importer.py` — Blender mesh, hierarchy, material, rig, and animation creation.
- `bz2pak.py` — Battlezone II PAK reading, browsing, extraction, and cache support.
- `softimage_pic.py` — Softimage PIC texture decoding.
- `bcn.py` — BC4/BC5 DDS decoding, including BC5 normal reconstruction.
- `sync_installed_extension.ps1` — Development helper for syncing a checkout into an installed Blender extension.
- `tests/` — Headless Blender corpus, render, material, hierarchy/pose, and skinning validation tools.
- `.github/workflows/extension-ci.yml` — Pull-request/main validation using Blender's native Extension validator and builder.
- `.github/workflows/release.yml` — Tag-driven packaged Blender Extension release workflow using the same native tooling.

## Blender Extension Packaging

This repository targets Blender's current **Extensions** system rather than the legacy add-on packaging model.

- Package metadata and versioning live in `blender_manifest.toml`.
- `__init__.py` contains registration/runtime code only; it no longer carries legacy `bl_info` metadata.
- Internal runtime modules use package-relative imports so they work under Blender's extension namespace.
- The manifest has an explicit build file list so tests, documentation, GitHub metadata, and development helpers are not accidentally shipped in the extension ZIP.
- CI uses Blender **4.5.14 LTS** to validate the source manifest, build the ZIP, validate the built ZIP, and verify the exact runtime file set.
- NumPy is used by the BC4/BC5 decoder from Blender's bundled Python environment; the extension does not run `pip` or install packages at runtime.

Official publication on `extensions.blender.org` is a separate licensing/provenance decision and is not part of this migration.

## Compatibility

- **Blender:** 4.5 LTS or newer
- **Source assets:** Battlezone II and Battlezone: Combat Commander / BZ2 Redux MSH content
- **Import sources:** loose `.msh` files and Battlezone II `.pak` archives

## License

The current Blender manifest declares `SPDX:MIT`, matching the repository's existing licensing statement. However, neither this fork nor the original upstream repository currently contains a standalone license file. Licensing/provenance should be resolved before considering submission to Blender's official Extensions Platform.

## Links

- **Repository:** https://github.com/GrizzlyOne95/io_scene_bz2msh
- **Issues:** https://github.com/GrizzlyOne95/io_scene_bz2msh/issues
- **Original project:** https://github.com/frute94/io_scene_bz2msh

## Credits

Original plugin by frute94.

Earlier local mesh/material import fixes were credited to ZerothDivision and tested by GrizzlyOne95. This fork modernizes the importer for Blender 4.5+ and continues format/parser, animation, skinning, archive, and material support work.
