Forked from https://github.com/frute94/io_scene_bz2msh/tree/main

# Battlezone II/Combat Commander MSH Importer for Blender 4.5 LTS

A modern, high-performance Blender Extension for importing `.msh` 3d model assets from **Battlezone Combat Commander** and **Battlezone II**. This tool is designed specifically for the Blender 4.5+ ecosystem, supporting the new layered animation system and Vulkan-based viewport.

## Features

* **Global & Local Support:** Correctly handles both global geometry (origin-offset) and local hierarchy meshes.
* **Intelligent Mesh Indexing:** Respects vertex group relative indexing to prevent "origin-clumping."
* **Layered Animations:** Full support for Blender 4.5 **Action Slots**, importing translation and rotation keyframes directly into the Action Editor.
* **Material Mapping:** Automatically searches for and applies textures/materials based on BZ2 path logic. Multiple materials are supported now!

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
    * **Find Textures:** Searches adjacent folders (like `/bitmaps/`) for matching `.tga` or `.pic` files.
    * **Respect Relative Indexing:** (Enabled by default) Ensures geometry segments are placed correctly.

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
