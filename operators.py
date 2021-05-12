import os
import subprocess
import bpy

from . import functions


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
            filepath=filename,
            use_selection=True,
            object_types={"MESH"},
            bake_anim=False,
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


class SmoothNormalsOperator(bpy.types.Operator):
    bl_idname = "object.smooth_normals"
    bl_label = "Smooth normals"

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is not None:
            if obj.mode == "OBJECT":
                return True
        return False

    def execute(self, context):
        # TODO
        return {"FINISHED"}
