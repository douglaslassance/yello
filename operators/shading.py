import bpy

from .. import functions
from ..contexts import SelectionContext


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
