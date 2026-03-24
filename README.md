Forked from https://github.com/frute94/io_scene_bz2msh/tree/main

# Battlezone II/Combat Commander MSH Importer for Blender 4.5 LTS

A modern, high-performance Blender Extension for importing `.msh` 3d model assets from **Battlezone Combat Commander** and **Battlezone II**. This tool is designed specifically for the Blender 4.5+ ecosystem, supporting the new layered animation system and Vulkan-based viewport.

## Features

* **Global & Local Support:** Correctly handles both global geometry (origin-offset) and local hierarchy meshes.
* **Intelligent Mesh Indexing:** Respects vertex group relative indexing to prevent "origin-clumping."
* **Layered Animations:** Imports block-level object animations into Blender 4.5 **Action Slots**, mapping clips by MSH `state_index` so moving parts land on the correct objects.
* **Blender-Space Transform Baking:** Local transforms and animation keyframes are converted into Blender-space channels when `Rotate Root Frames` is enabled, so Action Editor values match the viewport orientation.
* **Material Mapping:** Automatically searches for and applies textures/materials based on BZ2 path logic. Multiple materials are supported now!
* **DXTBZ2 Conversion:** Auto-converts detected `.dxtbz2` textures to `.dds` and loads them into Blender materials.
* **PAK Import:** Browse `.msh` assets directly inside Battlezone II `.pak` archives and cache extracted contents automatically.
* **Softimage PIC Support:** Loads `.pic` textures used by older assets and can cache decoded `.png` copies next to the originals.

## Installation (Blender 4.5+)

The easiest way to install this is using the new **Extensions** system:

1.  **Download:** Click the green `<> Code` button and select **Download ZIP**.
2.  **Open Blender:** Go to `Edit > Preferences > Extensions`.
3.  **Install:** * Click the **down-arrow icon** in the top-right corner.
    * Select **Install from Disk...**.
    * Navigate to the downloaded `.zip` file and select it.
4.  **Enable:** Ensure the "Battlezone II MSH Importer" is toggled on.

## Development Sync

If you are developing from this checkout and Blender is loading a separately installed copy from `%APPDATA%`, keep that installed extension in sync with:

```powershell
.\sync_installed_extension.ps1
```

This avoids stale-extension issues where valid BZ2 demo meshes may fail in Blender with errors such as `Unhandled Mesh Block 0x0` or unexpected `MemoryError` exceptions even though the repo parser already handles them.

## Usage

1.  Go to `File > Import > Battlezone II MSH / PAK (.msh, .pak)`.
2.  Select either a loose `.msh` or a `.pak` archive.
3.  If you selected a `.pak`, choose the in-archive `.msh` asset from the import panel.
4.  **Import Options:**
    * **Import Animations:** Creates Actions and Slots for any embedded keyframes.
    * **Global Mesh:** Imports the block as a single mesh object. Useful for quick static inspection, but it does not preserve animated sub-objects as separate Blender objects.
    * **Local Meshes:** Imports the full node hierarchy as separate objects. Use this mode for hardpoints, moving parts, and object-transform animations such as deploy/retract clips.
    * **Rotate Root Frames:** Converts BZ2 transforms into Blender-space. Leave this enabled unless you explicitly want raw source axes.
    * **Find Textures:** Searches adjacent folders (like `/bitmaps/`) for matching textures.
    * **Auto-convert .dxtbz2:** Converts supported `.dxtbz2` textures to `.dds` on demand before loading them into Blender.
    * **Convert PIC to PNG:** Decodes Softimage `.pic` textures and optionally caches `.png` copies so re-imports are faster.

## Notes

* BZ2 animation in `.msh` files is object-transform based, not armature/skinning based. Animated parts import as separate Blender objects with Actions.
* Animation clips are read from each parsed block's `animation_list`, not from a top-level file animation table.
* The importer resolves animation targets by `state_index`, which is required for multi-part assets such as deployable structures and vehicles.
* `Global Mesh` is best for static review. `Local Meshes` is the correct mode for animated assets.

## Repository Structure

For developers looking to contribute, the structure is optimized for the Blender Extension manifest:

* `blender_manifest.toml`: Metadata and permissions for Blender 4.5.
* `__init__.py`: Handles the UI and registration.
* `msh_blender_importer.py`: The core logic for mesh and animation creation.
* `bz2msh.py`: The low-level binary parser for the .msh format.

## License

Distributed under the MIT License. See `LICENSE` for more information.

## Links

* **GitHub:** [GrizzlyOne95/io_scene_bz2msh](https://github.com/GrizzlyOne95/io_scene_bz2msh)
* **Issues:** [Report a Bug](https://github.com/GrizzlyOne95/io_scene_bz2msh/issues)


Original plugin developed by frute94, original credits there:
"Import logic for local mesh & material imports fixed by ZerothDivision and tested by GrizzlyOne95"
