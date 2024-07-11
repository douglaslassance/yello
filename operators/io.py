import os
import subprocess
import bpy

from .. import functions


class ExportMeshOperator(bpy.types.Operator):
    bl_idname = "object.export_mesh"
    bl_label = "Export mesh"
    bl_description = "Export selected meshes and armatures to a single FBX"

    joined: bpy.props.BoolProperty(
        name="Joined",
        description="Join selected meshes in a single mesh.",
    )

    @classmethod
    def poll(cls, context):
        if bpy.data.filepath:
            if context.mode and context.selected_objects:
                return True
        return False

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if self.joined:
            meshes = []
            exports = []
            for obj in bpy.context.selected_objects:
                if obj.type == "MESH":
                    meshes.append(obj)
                else:
                    exports.append(obj)
            joined_mesh = functions.join_objects(meshes)
            if joined_mesh:
                exports.append(joined_mesh)
        else:
            exports = bpy.context.selected_objects
        dirname, basename = os.path.split(bpy.data.filepath)
        filename = os.path.join(dirname, f"{os.path.splitext(basename)[0]}.fbx")
        functions.export_fbx(exports, filename)
        if self.joined and joined_mesh:
            functions.delete_objects([joined_mesh])
        return {"FINISHED"}


class ExportMeshesOperator(bpy.types.Operator):
    bl_idname = "object.export_meshes"
    bl_label = "Export meshes"
    bl_description = "Export selected meshes to individual FBX files"

    prefix: bpy.props.StringProperty(
        name="Prefix",
        description="The prefix for this file's name",
    )
    separator: bpy.props.StringProperty(
        name="Separator",
        default="_",
        description="The object name separator to use",
    )
    remove_pre_existing: bpy.props.BoolProperty(
        name="Remove pre-existing files",
        default=False,
        description="Remove pre-existing FBX files that match this export prefix",
    )

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
        subprocess.Popen(["explorer", "/select,", bpy.data.filepath])
        return {"FINISHED"}
