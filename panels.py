# pylint: disable=invalid-name
from bpy.types import Panel


class PlaystheticIoView3dPanel(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "I/O"
    bl_category = "Playsthetic"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.operator("object.lock_file", icon="LOCKED")
        col.operator("object.open_containing_folder", icon="FILE_FOLDER")
        col.operator("object.export_mesh", icon="MESH_MONKEY")
        col.operator("object.export_animation", icon="ONIONSKIN_ON")
        col.operator("object.export_animated_mesh", icon="MOD_SOFT")


class PlaystheticRiggingView3dPanel(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Rigging"
    bl_category = "Playsthetic"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.operator("pose.create_bone_aligned_object", icon="EMPTY_DATA")
        col.operator("armature.distribute_bones_evenly", icon="CURVE_PATH")
        col.operator("armature.align_bones", icon="CON_TRACKTO")
        col.operator("armature.align_bone_rolls", icon="ORIENTATION_GIMBAL")
        col.operator("armature.generate_twist_bones", icon="FORCE_MAGNETIC")
        col.operator("armature.generate_blend_bone", icon="ORIENTATION_GLOBAL")


class PlaystheticShadingView3dPanel(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Shading"
    bl_category = "Playsthetic"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.operator("object.smooth_normals", icon="MOD_SMOOTH")
        col.operator("object.reset_normals", icon="X")
