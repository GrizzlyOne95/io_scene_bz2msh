import bpy
import re  # Reading .material files
from mathutils import Matrix, Vector, Euler, Quaternion
from bpy_extras import image_utils
from math import radians

from . import bz2msh
from . import undxtbz2
import os

# Normals changed in 4.1 from 4.0
OLD_NORMALS = not (bpy.app.version[0] >= 4 and bpy.app.version[1] >= 1)

PRINT_TEXTURE_FINDER_INFO = False
PRINT_LOCAL_MATERIAL_REUSE = False
PRINT_MSH_HEADER = True

NODE_NORMALMAP_STRENGTH = 1.0
NODE_EMISSIVE_STRENGTH = 1.0
NODE_DEFAULT_ROUGHNESS = 0.50

# Emulate mesh render flags
USE_RENDER_FLAGS = True
RENDER_FLAGS_RENAME = True  # add __h2cg etc to object name

# Visual placement for material nodes in the blender node editor
NODE_SPACING_X, NODE_SPACING_Y = 600, 300
NODE_HEIGHT = {
    "diffuse": NODE_SPACING_Y,
    "specular": 0,
    "emissive": -NODE_SPACING_Y,
    "normal": -(NODE_SPACING_Y * 2)
}


def find_texture(texture_filepath, search_directories, acceptable_extensions, recursive=False, auto_convert_dxtbz2=False):
    acceptable_extensions = list(acceptable_extensions)

    file_name, original_extension = os.path.splitext(os.path.basename(texture_filepath))
    original_extension_compare = original_extension.lower()
    is_material_file = bool(original_extension_compare == ".material")

    # If we passed a .material file extension, just look for .material files.
    # Does *NOT* look for textures based on any parsed material file.
    if is_material_file:
        # Only look for .material files
        acceptable_extensions = [original_extension_compare]

    else:
        # Prevent a double search
        while original_extension_compare in acceptable_extensions:
            del acceptable_extensions[acceptable_extensions.index(original_extension_compare)]

        # Originally specified extension is looked for first.
        if original_extension_compare not in acceptable_extensions:
            acceptable_extensions = [original_extension_compare] + acceptable_extensions

    # Format extension list
    for index, ext in enumerate(acceptable_extensions):
        acceptable_extensions[index] = ext.lower()

    # If specified, search directories for acceptable extensions first
    if search_directories:
        for ext in acceptable_extensions:
            if ext != original_extension_compare:
                filename = file_name + ext
                for directory in search_directories:
                    if recursive:
                        for root, dirs, files in os.walk(directory):
                            if filename in files:
                                path = os.path.join(root, filename)
                                if PRINT_TEXTURE_FINDER_INFO:
                                    print("TEXTURE FOUND FOR %r:" % file_name, "%r success." % path)
                                return path
                    else:
                        path = os.path.join(directory, filename)
                        if os.path.exists(path) and os.path.isfile(path):
                            if PRINT_TEXTURE_FINDER_INFO:
                                print("TEXTURE FOUND FOR %r:" % file_name, "%r success." % path)
                            return path

    # If that failed, try the original extension in search directories
    if search_directories:
        filename = file_name + original_extension
        if original_extension_compare == ".dxtbz2" and auto_convert_dxtbz2:
            filename = file_name + ".dds"

        for directory in search_directories:
            if recursive:
                for root, dirs, files in os.walk(directory):
                    if filename in files:
                        path = os.path.join(root, filename)
                        if PRINT_TEXTURE_FINDER_INFO:
                            print("TEXTURE FOUND FOR %r:" % file_name, "%r success." % path)
                        return path
            else:
                path = os.path.join(directory, filename)
                if os.path.exists(path) and os.path.isfile(path):
                    if PRINT_TEXTURE_FINDER_INFO:
                        print("TEXTURE FOUND FOR %r:" % file_name, "%r success." % path)
                    return path

                if not recursive:
                    break

    if PRINT_TEXTURE_FINDER_INFO:
        print("TEXTURE FINDER %r:" % file_name, "Texture not found.")

    return file_name + original_extension


def read_material_file(filepath, default_diffuse=None):
    re_section = re.compile(r"\[(.+?)\]")
    re_property = re.compile(r"([a-zA-Z_]+)\s*=\s*(.+)")

    textures = {
        "diffuse": default_diffuse,
        "normal": None,
        "specular": None
    }

    current_section = None
    if not os.path.exists(filepath):
        return textures

    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(";"):
                continue

            section_match = re_section.match(line)
            if section_match:
                current_section = section_match.group(1).lower()
                continue

            prop_match = re_property.match(line)
            if prop_match and current_section == "textures":
                key = prop_match.group(1).lower()
                value = prop_match.group(2).strip()
                if key in textures:
                    textures[key] = value

    return textures


def verts_of_all_vertex_groups(mesh):
    index_start = 0
    vert_start = 0
    for vgroup in mesh.vert_groups:
        index_end = index_start + vgroup.index_count.value
        for index in mesh.indices[index_start:index_end]:
            yield mesh.vertex[vert_start + index]
        vert_start += vgroup.vert_count.value
        index_start = index_end


class Load:
    def __init__(self, operator, context, filepath="", as_collection=False, **opt):
        self.opt = opt
        self.context = context

        self.name = os.path.basename(filepath)
        self.filefolder = os.path.dirname(filepath)
        self.ext_list = self.opt["find_textures_ext"].casefold().split()
        self.tex_dir = self.context.preferences.filepaths.texture_directory

        self.bpy_objects = []
        bpy_root_objects = []
        # Map state indices to Blender objects for animation
        self.state_to_object = {}
        # Entire .msh file is read into this object first
        self.msh = bz2msh.MSH(filepath)

        collection = self.context.view_layer.active_layer_collection.collection
        if as_collection:
            collection = bpy.data.collections.new(os.path.basename(filepath))
            bpy.context.scene.collection.children.link(collection)

        if PRINT_MSH_HEADER:
            print("\nMSH %r" % os.path.basename(filepath))
            for block in self.msh.blocks:
                print("\nBlock %r MSH Header:" % block.name)
                print("- dummy:", block.msh_header.dummy)
                print("- scale:", block.msh_header.scale)
                print("- indexed:", block.msh_header.indexed)
                print("- moveAnim:", block.msh_header.moveAnim)
                print("- oldPipe:", block.msh_header.oldPipe)
                print("- isSingleGeometry:", block.msh_header.isSingleGeometry)
                print("- skinned:", block.msh_header.skinned, "\n")

        # Deselect all objects in blender
        for bpy_obj in context.scene.objects:
            bpy_obj.select_set(False)

        if opt["import_mode"] == "GLOBAL":
            for block in self.msh.blocks:
                bpy_obj = self.create_object(
                    block.name,
                    self.create_global_mesh(block),
                    self.create_matrix(Matrix()),
                    None
                )

                scale = block.msh_header.scale
                bpy_obj.scale = Vector((scale, scale, scale))
                bpy_root_objects.append(bpy_obj)

        elif opt["import_mode"] == "LOCAL":
            # Reuse same-named materials for each local mesh
            self.existing_materials = {}  # {str(name of msh material): bpy.types.Material(blender material object)}
            for block in self.msh.blocks:
                bpy_root_objects.append(self.walk(block.root))

        for bpy_obj in bpy_root_objects:
            if self.opt["rotate_for_yz"]:
                bpy_obj.rotation_euler[0] = radians(90)
                bpy_obj.rotation_euler[2] = radians(180)
                bpy_obj.location[1], bpy_obj.location[2] = bpy_obj.location[2], bpy_obj.location[1]

            if self.opt["place_at_cursor"]:
                bpy_obj.location += context.scene.cursor.location

        for bpy_obj in self.bpy_objects[::-1]:
            collection.objects.link(bpy_obj)
            bpy_obj.select_set(True)
            self.context.view_layer.objects.active = bpy_obj

        # Build animations after all objects exist
        if self.opt.get("import_animations", False):
            self.import_animations()

    def walk(self, mesh, bpy_parent=None):
        bpy_obj = self.create_object(
            mesh.name,
            self.create_local_mesh(mesh),
            self.create_matrix(mesh.matrix),
            bpy_parent
        )

        # Map this mesh's state index to the Blender object for animation
        if hasattr(mesh, "state_index"):
            try:
                state_index = mesh.state_index.value
            except AttributeError:
                state_index = None
            if state_index is not None:
                key = (id(mesh.block), state_index)
                self.state_to_object[key] = bpy_obj

        if USE_RENDER_FLAGS and bpy_obj.data:
            ignore_hidden = bool(mesh.name.split("_")[0].casefold() in ("flame",))
            append_flags = ""

            if mesh.renderflags.value & bz2msh.RS_HIDDEN and not ignore_hidden:
                bpy_obj.hide_render = True
                bpy_obj.display_type = "WIRE"
                append_flags += "h"

            if mesh.renderflags.value & bz2msh.RS_COLLIDABLE and not ignore_hidden:
                bpy_obj.hide_render = True
                bpy_obj.display_type = "WIRE"
                append_flags += "c"

            # Example of other flags; adjust to your real flags if needed
            # if mesh.renderflags.value & bz2msh.DP_DONOTLIGHT:
            #     append_flags += "e"

            if mesh.renderflags.value & bz2msh.RS_2SIDED:
                append_flags += "2"

            if RENDER_FLAGS_RENAME and append_flags:
                bpy_obj.name = bpy_obj.name + "__" + append_flags

        if not bpy_parent:
            scale = mesh.block.msh_header.scale
            bpy_obj.scale = Vector((scale, scale, scale))

        if not bpy_obj.data:
            bpy_obj.empty_display_type = "SINGLE_ARROW"

        for msh_sub_mesh in mesh.meshes:
            self.walk(msh_sub_mesh, bpy_obj)

        return bpy_obj

    def create_normals(self, bpy_mesh, normals):
        try:
            bpy_mesh.normals_split_custom_set(normals)
            if OLD_NORMALS:
                bpy_mesh.use_auto_smooth = True

        except RuntimeError as msg:
            print("MSH importer failed to import normals for %r:" % bpy_mesh.name, msg)
            if OLD_NORMALS:
                bpy_mesh.use_auto_smooth = False

    def create_uvmap(self, bpy_mesh, uvs):
        bpy_uvmap = bpy_mesh.uv_layers.new().data
        for index, uv in enumerate(uvs):
            bpy_uvmap[index].uv = Vector((uv[0], -uv[1] + 1.0))

    def create_vertex_colors(self, bpy_mesh, colors):
        bpy_vcol = bpy_mesh.vertex_colors.new().data

        if colors:
            loop_colors = []
            for loop in bpy_mesh.loops:
                loop_colors.append(colors[loop.vertex_index])

            for index, color in enumerate(loop_colors):
                bpy_vcol[index].color = [value / 255 for value in (color.r, color.g, color.b, color.a)]

    def create_matrix(self, msh_matrix):
        return Matrix(list(msh_matrix)).transposed()

    def create_object(self, name, data, matrix, bpy_obj_parent=None):
        bpy_obj = bpy.data.objects.new(name=name, object_data=data)

        if bpy_obj_parent:
            bpy_obj.parent = bpy_obj_parent

        bpy_obj.matrix_local = matrix

        self.bpy_objects.append(bpy_obj)

        return bpy_obj

    # =========================
    #  Animation import helpers
    # =========================

    def import_animations(self):
        """Import animations for all blocks, if requested."""
        if not self.opt.get("import_animations", False):
            return
        for block in self.msh.blocks:
            self.import_block_animations(block)

    def import_block_animations(self, block):
        """Create Blender actions for all AnimLists in a Block."""
        anim_lists = getattr(block, "animation_list", None)
        if not anim_lists:
            return
        for anim_list in anim_lists:
            self._import_animlist_for_block(block, anim_list)

    def _import_animlist_for_block(self, block, anim_list):
        """Create actions for each Anim track in an AnimList."""
        for anim in anim_list.animations:
            try:
                state_index = anim.index.value
            except AttributeError:
                continue

            key = (id(block), state_index)
            obj = self.state_to_object.get(key)
            if obj is None:
                continue

            clip_name = anim_list.name or "Anim"
            action_name = f"{obj.name}_{clip_name}"
            action = bpy.data.actions.new(name=action_name)

            obj.animation_data_create()
            obj.animation_data.action = action
            obj.rotation_mode = "QUATERNION"

            fcurves_loc = [
                action.fcurves.new(data_path="location", index=i)
                for i in range(3)
            ]
            fcurves_rot = [
                action.fcurves.new(data_path="rotation_quaternion", index=i)
                for i in range(4)
            ]

            for keyframe in anim.states:
                frame = keyframe.frame
                loc = (keyframe.vect.x, keyframe.vect.y, keyframe.vect.z)
                rot = (keyframe.quat.s, keyframe.quat.x, keyframe.quat.y, keyframe.quat.z)

                for i, val in enumerate(loc):
                    fcurves_loc[i].keyframe_points.insert(frame, val)

                for i, val in enumerate(rot):
                    fcurves_rot[i].keyframe_points.insert(frame, val)

    # =======================
    #  Mesh building routines
    # =======================

    def create_global_mesh(self, block):
        if len(block.vertices) <= 0:
            return None

        vertices = [tuple(v) for v in block.vertices]
        faces = [tuple(faceobj.verts) for faceobj in block.faces]
        bucky_indices = [int(faceobj.buckyIndex) for faceobj in block.faces]

        bpy_mesh = bpy.data.meshes.new(block.name)
        bpy_mesh.from_pydata(vertices, [], faces)

        if self.opt["import_mesh_materials"]:
            bpy_materials = []
            for bucky in block.buckydescriptions:
                bpy_materials += [self.create_material(bucky.material, bucky.texture)]
                bpy_mesh.materials.append(bpy_materials[-1])

            for index, material_index in enumerate(bucky_indices):
                if material_index >= 0 and material_index < len(bpy_materials):
                    bpy_mesh.polygons[index].material_index = material_index

        if self.opt["import_mesh_normals"]:
            normals = [tuple(v) for v in block.vertex_normals]
            self.create_normals(bpy_mesh, normals)

        if self.opt["import_mesh_uvmap"]:
            self.create_uvmap(bpy_mesh, [tuple(v) for v in block.uvs])

        if self.opt["import_mesh_vertcolor"]:
            self.create_vertex_colors(bpy_mesh, list(block.vert_colors))

        return bpy_mesh

    def create_local_mesh(self, mesh):
        if len(mesh.vertex) <= 0:
            return None

        vertices = [(vert.pos.x, vert.pos.y, vert.pos.z) for vert in mesh.vertex]

        faces = []
        index_start = 0
        vert_start = 0
        for vgindex, vgroup in enumerate(mesh.vert_groups):
            triangle = []
            index_end = index_start + vgroup.index_count.value
            for index in mesh.indices[index_start:index_end]:
                triangle += [vert_start + index]
                if len(triangle) >= 3:
                    faces += [triangle]
                    triangle = []

            vert_start += vgroup.vert_count.value
            index_start = index_end

        bpy_mesh = bpy.data.meshes.new(mesh.name)
        bpy_mesh.from_pydata(vertices, [], faces)

        if self.opt["import_mesh_materials"]:
            face_start = 0
            bpy_materials = []
            for vgroup in mesh.vert_groups:
                mat = vgroup.material
                tex = vgroup.texture

                if mat.name in self.existing_materials:
                    bpy_materials += [self.existing_materials[mat.name]]
                    if PRINT_LOCAL_MATERIAL_REUSE:
                        print("Reusing material:", mat.name)

                else:
                    bpy_materials += [self.create_material(mat, tex)]
                    self.existing_materials[mat.name] = bpy_materials[-1]
                    if PRINT_LOCAL_MATERIAL_REUSE:
                        print("New Material %r" % mat.name)

                mat_index = len(bpy_mesh.materials)
                bpy_mesh.materials.append(bpy_materials[-1])

                face_end = face_start + vgroup.index_count.value // 3
                for index in range(face_start, face_end):
                    bpy_mesh.polygons[index].material_index = mat_index

                face_start = face_end

        if self.opt["import_mesh_uvmap"]:
            self.create_uvmap(bpy_mesh, [tuple(vertex.uv) for vertex in verts_of_all_vertex_groups(mesh)])

        if self.opt["import_mesh_normals"]:
            self.create_normals(bpy_mesh, [tuple(vertex.norm) for vertex in verts_of_all_vertex_groups(mesh)])

        if self.opt["import_mesh_vertcolor"]:
            colors = []
            if mesh.vert_colors:
                for face in faces:
                    for index in face:
                        colors += [mesh.vert_colors[index]]

            self.create_vertex_colors(bpy_mesh, colors)

        return bpy_mesh

    # =================================
    #  Material & node-setup utilities
    # =================================

    def create_material_vcolnodes(self, bpy_material, bpy_node_bsdf, bpy_node_texture):
        bpy_node_attribute = bpy_material.node_tree.nodes.new("ShaderNodeAttribute")
        bpy_node_attribute.attribute_name = "Col"
        bpy_node_attribute.location = (-NODE_SPACING_X, NODE_HEIGHT["diffuse"] + NODE_SPACING_Y)

        bpy_node_mixrgb = bpy_material.node_tree.nodes.new("ShaderNodeMixRGB")
        bpy_node_mixrgb.blend_type = "MULTIPLY"
        bpy_node_mixrgb.inputs["Fac"].default_value = 1.0
        bpy_node_mixrgb.location = (-NODE_SPACING_X / 2, NODE_HEIGHT["diffuse"] + NODE_SPACING_Y / 2)

        bpy_material.node_tree.links.new(
            bpy_node_attribute.outputs["Color"],
            bpy_node_mixrgb.inputs["Color1"]
        )

        bpy_material.node_tree.links.new(
            bpy_node_texture.outputs["Color"],
            bpy_node_mixrgb.inputs["Color2"]
        )

        bpy_material.node_tree.links.new(
            bpy_node_mixrgb.outputs["Color"],
            bpy_node_bsdf.inputs["Base Color"]
        )

    def create_material(self, material, texture):
        mat_name = material.name if hasattr(material, "name") else "Material"

        if mat_name in getattr(self, "existing_materials", {}):
            return self.existing_materials[mat_name]

        mat = bpy.data.materials.new(mat_name)
        mat.use_nodes = True
        nt = mat.node_tree
        nodes = nt.nodes
        links = nt.links

        for node in nodes:
            nodes.remove(node)

        node_output = nodes.new("ShaderNodeOutputMaterial")
        node_output.location = (NODE_SPACING_X * 2, 0)

        node_bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        node_bsdf.location = (NODE_SPACING_X, 0)
        node_bsdf.inputs["Roughness"].default_value = NODE_DEFAULT_ROUGHNESS

        links.new(node_bsdf.outputs["BSDF"], node_output.inputs["Surface"])

        diffuse_path = texture.textureName if hasattr(texture, "textureName") else None
        image_node = None
        if diffuse_path:
            tex_full = find_texture(
                diffuse_path,
                [self.filefolder, self.tex_dir] if self.tex_dir else [self.filefolder],
                self.ext_list,
                recursive=self.opt["find_textures"],
                auto_convert_dxtbz2=self.opt.get("auto_convert_dxtbz2", False)
            )

            try:
                img = image_utils.load_image(tex_full, self.filefolder)
                image_node = nodes.new("ShaderNodeTexImage")
                image_node.image = img
                image_node.location = (0, NODE_HEIGHT["diffuse"])
                links.new(image_node.outputs["Color"], node_bsdf.inputs["Base Color"])
            except Exception as e:
                print("Failed to load texture %r: %s" % (tex_full, e))

        self.existing_materials[mat_name] = mat
        return mat


def load(operator, context, filepath="", **opt):
    multiple_files = opt["multi_select"]
    as_collection = opt["import_collection"] or multiple_files

    if not multiple_files:
        Load(operator, context, filepath, as_collection, **opt)
    else:
        for index, filepath in enumerate(multiple_files):
            try:
                print("Importing file %d of %d (%r)" % (index + 1, len(multiple_files), filepath))
                Load(operator, context, filepath, as_collection, **opt)
            except Exception as msg:
                print("Exception occurred importing MSH file %r." % filepath)
                print(msg)

    return {"FINISHED"}
