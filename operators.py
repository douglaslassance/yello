import os
import subprocess
import bpy


class CheckOutFileOperator(bpy.types.Operator):
    bl_idname = "object.check_out_file"
    bl_label = "Check out file"
    bl_description = "Check out the current Blender file on Perforce."

    def execute(self, context):
        filename = bpy.data.filepath
        subprocess.run(['p4', 'edit', filename], cwd=os.path.dirname(filename))
        return {'FINISHED'}


class ExportStaticMeshOperator(bpy.types.Operator):
    bl_idname = "object.export_static_mesh"
    bl_label = "Export static mesh"

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is not None:
            if obj.mode == "OBJECT":
                return True
        return False
        
    def execute(self, context):
        filename = os.path.splitext(bpy.data.filepath)[0] + '.fbx'
        bpy.ops.export_scene.fbx(
            filepath=filename, use_selection=True,
            object_types={'MESH'}, bake_anim=False
        )
        return {'FINISHED'}


class LockFileOperator(bpy.types.Operator):
    bl_idname = "object.lock_file"
    bl_label = "Lock file"
    bl_description = "Perform a Git lock on the current file."

    def execute(self, context):
        filename = bpy.data.filepath
        subprocess.run(['git', 'lfs', 'lock', filename], cwd=os.path.dirname(filename))
        return {'FINISHED'}


class SimplifyNormalsOperator(bpy.types.Operator):
    bl_idname = "object.simplify_normals"
    bl_label = "Simplify normals"

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is not None:
            if obj.mode == "OBJECT":
                return True
        return False

    def execute(self, context):
        pairs = []
        for obj in [obj for obj in context.view_layer.objects.selected]:
            dup = obj.copy()
            dup.data = obj.data.copy()
            # dup.animation_data_clear()
            context.collection.objects.link(dup)
            pairs.append((obj, dup))
        for pair in pairs:
            # Setting decimated copy.
            bpy.context.view_layer.objects.active = pair[1]
            bpy.ops.object.modifier_add(type='DECIMATE')
            decimate = pair[1].modifiers[-1]
            decimate.ratio = 0.05
            pair[1].show_bounds = True
            pair[1].display_type = "BOUNDS"
            # Projecting normals.
            pair[0].data.use_auto_smooth = True
            bpy.context.view_layer.objects.active = pair[0]
            bpy.ops.object.modifier_add(type='DATA_TRANSFER')
            data_transfer = pair[0].modifiers[-1]
            data_transfer.object = pair[1]
            data_transfer.use_loop_data = True
            data_transfer.data_types_loops = {"CUSTOM_NORMAL"}
            data_transfer.loop_mapping = "POLYINTERP_NEAREST"
        return {'FINISHED'}


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
        return {'FINISHED'}