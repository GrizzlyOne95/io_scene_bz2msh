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

## Installation (Blender 4.5+)

The easiest way to install this is using the new **Extensions** system:

1.  **Download:** Click the green `<> Code` button and select **Download ZIP**.
2.  **Open Blender:** Go to `Edit > Preferences > Extensions`.
3.  **Install:** * Click the **down-arrow icon** in the top-right corner.
    * Select **Install from Disk...**.
    * Navigate to the downloaded `.zip` file and select it.
4.  **Enable:** Ensure the "Battlezone II MSH Importer" is toggled on.

## Usage

1.  Go to `File > Import > Battlezone II MSH (.msh)`.
2.  Select your file. 
3.  **Import Options:**
    * **Import Animations:** Creates Actions and Slots for any embedded keyframes.
    * **Global Mesh:** Imports the block as a single mesh object. Useful for quick static inspection, but it does not preserve animated sub-objects as separate Blender objects.
    * **Local Meshes:** Imports the full node hierarchy as separate objects. Use this mode for hardpoints, moving parts, and object-transform animations such as deploy/retract clips.
    * **Rotate Root Frames:** Converts BZ2 transforms into Blender-space. Leave this enabled unless you explicitly want raw source axes.
    * **Find Textures:** Searches adjacent folders (like `/bitmaps/`) for matching textures.
    * **Auto-convert .dxtbz2:** Converts supported `.dxtbz2` textures to `.dds` on demand before loading them into Blender.

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
