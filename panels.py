# pylint: disable=invalid-name

from bpy.types import Panel


class PlaystheticIOView3dPanel(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "I/O"
    bl_category = "Playsthetic"

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.operator("object.lock_file")
        row = layout.row()
        row.operator("object.export_mesh")
        row = layout.row()
        row.operator("object.export_animation")
        row = layout.row()
        row.operator("object.export_animated_mesh")


class PlaystheticShadingView3dPanel(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Shading"
    bl_category = "Playsthetic"

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.operator("object.smooth_normals")
        row = layout.row()
        row.operator("object.reset_normals")


class PlaystheticRiggingView3dPanel(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Rigging"
    bl_category = "Playsthetic"

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.operator("editable_bones.distribute_bones_evenly")
        row = layout.row()
        row.operator("editable_bones.align_bones")
        row = layout.row()
        row.operator("editable_bones.align_bone_rolls")