# Battlezone II MSH Importer v1.2.0

## Summary

First formal GitHub Release of the current Blender 4.5 extension for importing Battlezone II / Battlezone Combat Commander MSH assets.

## Highlights

- Imports loose `.msh` files and assets directly from Battlezone II `.pak` archives.
- Supports global geometry and local hierarchy imports.
- Imports object-transform animations into Blender 4.5 Action Slots and maps clips by MSH `state_index`.
- Converts source transforms and animation keyframes into Blender-space channels when root-frame conversion is enabled.
- Supports multiple materials and Battlezone II texture lookup behavior.
- Converts supported `.dxtbz2` textures to DDS for Blender loading.
- Decodes Softimage PIC textures and can cache PNG copies.
- Designed for Blender 4.5 LTS and its Extensions system.

## Installation

1. Download `io_scene_bz2msh-v1.2.0.zip` from this release.
2. In Blender 4.5+, open **Edit > Preferences > Extensions**.
3. Open the Extensions menu and choose **Install from Disk...**.
4. Select the downloaded ZIP and enable **Battlezone II MSH Importer**.

The release archive is packaged as a Blender Extension with `blender_manifest.toml` and `__init__.py` at the archive root.

## Credits

Based on the original `io_scene_bz2msh` work by frute94, with earlier local mesh/material import fixes credited in the repository to ZerothDivision and testing by GrizzlyOne95.
