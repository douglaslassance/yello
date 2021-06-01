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
        row.operator("object.lock_file", icon="LOCKED")
        row = layout.row()
        row.operator("object.open_containing_folder", icon="FILE_FOLDER")
        row = layout.row()
        row.operator("object.export_mesh", icon="MESH_MONKEY")
        row = layout.row()
        row.operator("object.export_animation", icon="ONIONSKIN_ON")
        row = layout.row()
        row.operator("object.export_animated_mesh", icon="MOD_SOFT")


class PlaystheticShadingView3dPanel(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Shading"
    bl_category = "Playsthetic"

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.operator("object.smooth_normals", icon="MOD_SMOOTH")
        row = layout.row()
        row.operator("object.reset_normals", icon="X")


class PlaystheticRiggingView3dPanel(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Rigging"
    bl_category = "Playsthetic"

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.operator("editable_bones.distribute_bones_evenly", icon="CURVE_PATH")
        row = layout.row()
        row.operator("editable_bones.align_bones", icon="CON_TRACKTO")
        row = layout.row()
        row.operator("editable_bones.align_bone_rolls", icon="ORIENTATION_GIMBAL")
        row = layout.row()
        row.operator("editable_bones.generate_twist_bones", icon="FORCE_MAGNETIC")
        row = layout.row()
        row.operator("editable_bones.generate_ease_bone", icon="ORIENTATION_GLOBAL")