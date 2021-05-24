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
        row.operator("object.export_mesh")


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
