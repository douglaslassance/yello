import os
import subprocess
import bpy

from .. import functions


class ExportMeshOperator(bpy.types.Operator):
    bl_idname = "object.export_mesh"
    bl_label = "Export mesh"

    @classmethod
    def poll(cls, context):
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
            bake_anim=False,
            filepath=filename,
            mesh_smooth_type="FACE",
            object_types={"MESH", "ARMATURE"},
            use_selection=True,
        )
        return {"FINISHED"}


class ExportAnimationOperator(bpy.types.Operator):
    bl_idname = "object.export_animation"
    bl_label = "Export animation"

    @classmethod
    def poll(cls, context):
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
            bake_anim_use_all_actions=False,
            bake_anim_use_nla_strips=False,
            bake_anim=True,
            filepath=filename,
            object_types={"ARMATURE"},
            use_selection=True,
        )
        return {"FINISHED"}


class ExportAnimatedMeshOperator(bpy.types.Operator):
    bl_idname = "object.export_animated_mesh"
    bl_label = "Export animated mesh"

    @classmethod
    def poll(cls, context):
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

    def execute(self, context):
        filename = bpy.data.filepath
        subprocess.run(["git", "lfs", "lock", filename], cwd=os.path.dirname(filename))
        return {"FINISHED"}