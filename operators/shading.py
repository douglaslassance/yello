import bpy
import bmesh

from .. import functions
from ..contexts import SelectionContext, ModeContext
from ..functions import get_active_color_attribute, get_color_attribute_layer


class SmoothNormalsOperator(bpy.types.Operator):
    _ratio_key = "yello_smooth_normal_iterations"

    bl_idname = "object.smooth_normals"
    bl_label = "Smooth Normals"
    bl_description = (
        "Generate normals by projecting them from a smoothed version of the model"
    )

    iterations: bpy.props.FloatProperty(
        name="Repeat", default=8
    )  # pyright: ignore [reportInvalidTypeForm]

    @classmethod
    def poll(cls, context):
        if context.mode == "OBJECT" and context.selected_objects:
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
                dup.name = "{}.Normals".format(obj.name)
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
    bl_label = "Reset Normals"
    bl_description = "Remove projected normal from model"

    @classmethod
    def poll(cls, context):
        if context.mode == "OBJECT" and context.selected_objects:
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


class SetMeshColorChannelOperator(bpy.types.Operator):
    bl_idname = "object.set_vertex_color"
    bl_label = "Set Mesh Color Channel"
    bl_description = (
        "Set a channel of the active mesh color attribute to the desired value for the "
        "selected components."
    )

    channel: bpy.props.EnumProperty(
        name="Channel",  # noqa: F821
        description="The channel we want to set.",  # noqa: F722
        items=[
            ("Red", "Red", "Red"),  # noqa: F821
            ("Green", "Green", "Green"),  # noqa: F821
            ("Blue", "Blue", "Blue"),  # noqa: F821
            ("Alpha", "Alpha", "Alpha"),  # noqa: F821
        ],
    )  # pyright: ignore [reportInvalidTypeForm]

    value: bpy.props.FloatProperty(
        name="Value",  # noqa: F821
        description="The value to set.",  # noqa: F722
        min=0.0,
        max=1.0,
        default=1.0,
    )  # pyright: ignore [reportInvalidTypeForm]

    @classmethod
    def poll(cls, context):
        return (
            context.object
            and context.object.type == "MESH"
            and context.mode == "EDIT_MESH"
        )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        with ModeContext("OBJECT"):
            object_ = context.object
            color_attribute = get_active_color_attribute(object_.data, create=True)
            domain = color_attribute.domain

            bm = bmesh.new()
            bm.from_mesh(object_.data)
            layer = get_color_attribute_layer(bm, color_attribute)

            if domain == "CORNER":
                loops = []
                # If we are in face mode we set value for the selected faces only.
                if bpy.context.tool_settings.mesh_select_mode[2]:
                    for face in bm.faces:
                        if face.select:
                            loops += face.loops
                else:
                    for vertice in bm.verts:
                        if vertice.select:
                            loops += list(vertice.link_loops)
                for loop in loops:
                    if self.channel == "Red":
                        loop[layer].x = self.value
                    elif self.channel == "Green":
                        loop[layer].y = self.value
                    elif self.channel == "Blue":
                        loop[layer].z = self.value
                    elif self.channel == "Alpha":
                        loop[layer].w = self.value

            elif domain == "POINT":
                for vert in bm.verts:
                    if vert.select:
                        if self.channel == "Red":
                            vert[layer].x = self.value
                        elif self.channel == "Green":
                            vert[layer].y = self.value
                        elif self.channel == "Blue":
                            vert[layer].z = self.value
                        elif self.channel == "Alpha":
                            vert[layer].w = self.value

            bm.to_mesh(object_.data)
        return {"FINISHED"}
