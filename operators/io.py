import os
import subprocess
import bpy

from .. import functions


class ExportMeshOperator(bpy.types.Operator):
    bl_idname = "object.export_mesh"
    bl_label = "Export mesh"
    bl_description = "Export static mesh and armature as FBX."

    @classmethod
    def poll(cls, context):
        if bpy.data.filepath:
            obj = context.object
            if obj is not None:
                if obj.mode == "OBJECT":
                    return True
        return False

    def execute(self, context):
        filename = os.path.splitext(bpy.data.filepath)[0] + ".fbx"
        functions.lock_file(filename)
        bpy.ops.export_scene.fbx(
            add_leaf_bones=False,
            apply_scale_options="FBX_SCALE_NONE",
            apply_unit_scale=True,
            axis_forward="-Z",
            axis_up="Y",
            bake_anim=False,
            bake_space_transform=False,
            filepath=filename,
            global_scale=1.0,
            mesh_smooth_type="FACE",
            object_types={"MESH", "ARMATURE"},
            use_selection=True,
            use_space_transform=True,
        )
        return {"FINISHED"}


class ExportAnimationOperator(bpy.types.Operator):
    bl_idname = "object.export_animation"
    bl_label = "Export animation"
    bl_description = "Export mesh only as an alembic."

    @classmethod
    def poll(cls, context):
        if bpy.data.filepath:
            obj = context.object
            if obj is not None:
                if obj.mode == "OBJECT":
                    return True
        return False

    def execute(self, context):
        filename = os.path.splitext(bpy.data.filepath)[0] + ".fbx"
        functions.lock_file(filename)
        bpy.ops.export_scene.fbx(
            add_leaf_bones=False,
            apply_scale_options="FBX_SCALE_NONE",
            apply_unit_scale=True,
            axis_forward="-Z",
            axis_up="Y",
            bake_anim=True,
            bake_space_transform=False,
            filepath=filename,
            global_scale=1.0,
            mesh_smooth_type="FACE",
            object_types={"ARMATURE"},
            use_selection=True,
            use_space_transform=True,
        )
        return {"FINISHED"}


class ExportAnimatedMeshOperator(bpy.types.Operator):
    bl_idname = "object.export_animated_mesh"
    bl_label = "Export animated mesh"
    bl_description = "Export armature only as FBX."

    @classmethod
    def poll(cls, context):
        if bpy.data.filepath:
            obj = context.object
            if obj is not None:
                if obj.mode == "OBJECT":
                    return True
        return False

    def execute(self, context):
        filename = os.path.splitext(bpy.data.filepath)[0] + ".abc"
        functions.lock_file(filename)
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


class LockFileOperator(bpy.types.Operator):
    bl_idname = "object.lock_file"
    bl_label = "Lock file"
    bl_description = "Perform a Git lock on the current file."

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.filepath)

    def execute(self, context):
        functions.lock_file(bpy.data.filepath)
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
