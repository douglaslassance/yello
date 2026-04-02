import os
import subprocess
import platform
import bpy

from .. import functions


class ExportMeshOperator(bpy.types.Operator):
    bl_idname = "object.export_mesh"
    bl_label = "Export mesh"
    bl_description = "Export selected meshes and armatures to a single FBX"

    file_format: bpy.props.EnumProperty(
        name="File format",
        description="The file format to export.",
        items=[
            ("FBX", "FBX", "FBX"),
            ("GLTF", "GLTF", "GLTF"),
        ],
    )  # pyright: ignore [reportInvalidTypeForm]

    join_meshes: bpy.props.BoolProperty(
        name="Join meshes",
        description="Join selected meshes in a single mesh.",
    )  # pyright: ignore [reportInvalidTypeForm]

    include_children: bpy.props.BoolProperty(
        name="Include children",
        description="Will add all children from selected parents.",
    )  # pyright: ignore [reportInvalidTypeForm]

    @classmethod
    def poll(cls, context):
        if bpy.data.filepath:
            if context.mode and context.selected_objects:
                return True
        return False

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        exports = bpy.context.selected_objects
        if self.include_children:
            for obj in bpy.context.selected_objects:
                for child in obj.children:
                    if child not in exports:
                        exports.append(child)
        if self.join_meshes:
            meshes = []
            joined_exports = []
            for obj in exports:
                if obj.type == "MESH":
                    meshes.append(obj)
                else:
                    joined_exports.append(obj)
            joined_mesh = functions.join_objects(meshes)
            if joined_mesh:
                joined_exports.append(joined_mesh)
            exports = joined_exports
        dirname, basename = os.path.split(bpy.data.filepath)
        filename = os.path.join(dirname, f"{os.path.splitext(basename)[0]}")
        if self.file_format == "FBX":
            functions.export_fbx(exports, filename + ".fbx")
        elif self.file_format == "GLTF":
            functions.export_gltf(exports, filename + ".glb", animations=False)
        if self.join_meshes and joined_mesh:
            functions.delete_objects([joined_mesh])
        return {"FINISHED"}


class ExportMeshesOperator(bpy.types.Operator):
    bl_idname = "object.export_meshes"
    bl_label = "Export meshes"
    bl_description = "Export selected meshes to individual FBX files"

    prefix: bpy.props.StringProperty(
        name="Prefix",
        description="The prefix for this file's name",
    )  # pyright: ignore [reportInvalidTypeForm]

    separator: bpy.props.StringProperty(
        name="Separator",
        default="_",
        description="The object name separator to use",
    )  # pyright: ignore [reportInvalidTypeForm]

    remove_pre_existing: bpy.props.BoolProperty(
        name="Remove pre-existing files",
        default=False,
        description="Remove pre-existing FBX files that match this export prefix",
    )  # pyright: ignore [reportInvalidTypeForm]

    @classmethod
    def poll(cls, context):
        if bpy.data.filepath:
            if context.mode and context.selected_objects:
                return True
        return False

    def invoke(self, context, event):
        basename = os.path.basename(bpy.data.filepath)
        self.prefix = os.path.splitext(basename)[0]
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        selection = bpy.context.selected_objects
        dirname, basename = os.path.split(bpy.data.filepath)
        if self.remove_pre_existing:
            for fbx_file in self.find_pre_existing(dirname, self.prefix):
                os.remove(fbx_file)
        for object in selection:
            object_name = object.name.replace(".", self.separator)
            filename = os.path.join(
                dirname,
                f"{self.prefix}{self.separator}{object_name}.fbx",
            )
            functions.export_fbx([object], filename)
        return {"FINISHED"}

    def find_pre_existing(self, dirname, prefix):
        """Find FBX files corresponding to this scene file export."""
        fbx_files = []
        for basename in os.listdir(dirname):
            if basename.startswith(prefix) and basename.endswith(".fbx"):
                fbx_files.append(os.path.join(dirname, basename))
        return fbx_files


class ExportAnimationOperator(bpy.types.Operator):
    bl_idname = "object.export_animation"
    bl_label = "Export animation"
    bl_description = "Export mesh only as an alembic"

    @classmethod
    def poll(cls, context):
        if bpy.data.filepath:
            if context.mode and context.selected_objects:
                return True
        return False

    def execute(self, context):
        filename = os.path.splitext(bpy.data.filepath)[0] + ".fbx"
        functions.make_writable(filename)
        bpy.ops.export_scene.fbx(
            add_leaf_bones=False,
            apply_scale_options="FBX_SCALE_NONE",
            apply_unit_scale=True,
            armature_nodetype="NULL",
            axis_forward="-Z",
            axis_up="Y",
            bake_anim=True,
            bake_space_transform=False,
            filepath=filename,
            global_scale=1.0,
            mesh_smooth_type="FACE",
            object_types={"ARMATURE"},
            primary_bone_axis="Y",
            secondary_bone_axis="X",
            use_selection=True,
            use_space_transform=True,
        )
        return {"FINISHED"}


class ExportAnimatedMeshOperator(bpy.types.Operator):
    bl_idname = "object.export_animated_mesh"
    bl_label = "Export animated mesh"
    bl_description = "Export armature only as FBX"

    @classmethod
    def poll(cls, context):
        if bpy.data.filepath:
            if context.mode and context.selected_objects:
                return True
        return False

    def execute(self, context):
        filename = os.path.splitext(bpy.data.filepath)[0] + ".abc"
        functions.make_writable(filename)
        bpy.ops.wm.alembic_export(
            apply_subdiv=True,
            check_existing=False,
            filepath=filename,
            selected=True,
            triangulate=True,
            use_instancing=False,
            uvs=False,
        )
        return {"FINISHED"}


class MakeWritableOperator(bpy.types.Operator):
    bl_idname = "object.make_writable"
    bl_label = "Make writable"
    bl_description = "Perform a Gitarmony make writable on the current file"

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.filepath)

    def execute(self, context):
        functions.make_writable(bpy.data.filepath)
        return {"FINISHED"}


class OpenContainingFolderOperator(bpy.types.Operator):
    bl_idname = "object.open_containing_folder"
    bl_label = "Open containing folder"

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.filepath)

    def execute(self, context):
        filepath = bpy.data.filepath
        if platform.system() == "Windows":
            subprocess.Popen(["explorer", "/select,", filepath])
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-R", filepath])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(filepath)])
        return {"FINISHED"}
