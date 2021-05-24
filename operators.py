import os
import subprocess
import bpy

from . import functions
from .contexts import SelectionContext


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
    _ratio_key = "normal_smooth_iterations"

    bl_idname = "object.smooth_normals"
    bl_label = "Smooth normals"

    iterations = bpy.props.FloatProperty(name="Repeat", default=8)

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is not None:
            if obj.mode == "OBJECT":
                return True
        return False

    def invoke(self, context, event):
        if self._ratio_key in bpy.context.scene.world:
            self.iterations = bpy.context.scene.world[self._ratio_key]
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        with SelectionContext() as selection_context:
            for obj in selection_context.selected:
                obj.data.use_auto_smooth = True
                dup = obj.copy()
                dup.data = obj.data.copy()
                for mod in obj.modifiers:
                    if mod.name == "NormalTransfer":
                        data_transfer = mod
                        bpy.data.objects.remove(mod.object)
                        break
                else:
                    bpy.context.view_layer.objects.active = obj
                    bpy.ops.object.modifier_add(type="DATA_TRANSFER")
                    data_transfer = obj.modifiers[-1]
                    data_transfer.name = "NormalTransfer"
                functions.remove_object_from_all_collections(dup)
                collection = functions.create_collection("Normal Sources")
                functions.add_object_to_collection(dup, collection)
                # dup.animation_data_clear()
                bpy.context.view_layer.objects.active = dup
                bpy.ops.object.modifier_add(type="SMOOTH")
                smooth = dup.modifiers[-1]
                smooth.iterations = self.iterations
                bpy.context.scene.world[self._ratio_key] = self.iterations
                dup.show_bounds = True
                dup.display_type = "BOUNDS"
                data_transfer.object = dup
                data_transfer.use_loop_data = True
                data_transfer.data_types_loops = {"CUSTOM_NORMAL"}
                data_transfer.loop_mapping = "POLYINTERP_NEAREST"
        return {"FINISHED"}


class ResetNormalsOperator(bpy.types.Operator):
    bl_idname = "object.reset_normals"
    bl_label = "Reset normals"

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is not None:
            if obj.mode == "OBJECT":
                return True
        return False

    def execute(self, context):
        with SelectionContext() as selection_context:
            for obj in selection_context.selected:
                for mod in obj.modifiers:
                    if mod.type == "DATA_TRANSFER" and mod.name == "NormalTransfer":
                        source = mod.object
                        if source:
                            bpy.data.objects.remove(source)
                        bpy.context.view_layer.objects.active = obj
                        bpy.ops.object.modifier_remove(modifier=mod.name)
                        break
        return {"FINISHED"}


class AlignBoneRollsOperator(bpy.types.Operator):
    bl_idname = "editable_bones.align_bone_rolls"
    bl_label = "Align bone rolls"

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is not None:
            if obj.mode == "EDIT":
                return True
        return False

    def execute(self, context):
        # TODO
        return {"FINISHED"}


class DistributeBonesEvenlyOperator(bpy.types.Operator):
    bl_idname = "editable_bones.distribute_bones_evenly"
    bl_label = "Distribute bones evenly"

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is not None:
            if obj.mode == "EDIT":
                return True
        return False

    def execute(self, context):
        bones = context.editable_bones
        if not bones or len(bones) < 2:
            self.report({"ERROR"}, "A minimum of 2 bones should be selected")
            return {"FINISHED"}
        bones.reverse()
        for bone in bones[:-1]:
            print(bone)
            parent_index = bones.index(bone) + 1
            if not bone.parent == bones[parent_index]:
                self.report({"ERROR"}, "Selected bones need to be connected")
                return {"FINISHED"}
        head = bones[-1].head
        overarching_vector = bones[0].tail - head
        length = overarching_vector.length
        normalized = overarching_vector.normalized()
        bone_count = len(bones)
        bone_number = 0
        bones.reverse()
        for bone in bones[:-1]:
            bone_number += 1
            print(head, normalized, length, bone_count, bone_number)
            bone.tail = head + normalized * length / bone_count * bone_number
        self.report({"INFO"}, "Distributing bones evenly")
        for bone in bones:
            bone.roll = 0
        return {"FINISHED"}