# pylint: disable=invalid-name

from bpy.types import Panel


class PlaystheticView3dPanel(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Playsthetic"
    bl_category = "Playsthetic"

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        col = row.column()
        col.operator("object.lock_file")
        row = layout.row()
        col = row.column()
        col.operator("object.export_static_mesh")
        row = layout.row()
        col = row.column()
        col.operator("object.smooth_normals")
