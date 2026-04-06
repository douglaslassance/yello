# pylint: disable=invalid-name
import bpy
from bpy.types import Panel


class YelloFileView3dPanel(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "File"
    bl_category = "Yello"
    bl_order = 0

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        col = layout.column(align=True)
        col.operator("object.make_writable", icon="OUTLINER_DATA_GP_LAYER")
        col.operator("object.open_containing_folder", icon="FILE_FOLDER")


class YelloRiggingView3dPanel(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Rigging"
    bl_category = "Yello"
    bl_order = 2

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        col = layout.column(align=True)
        col.operator("pose.create_bone_aligned_object", icon="EMPTY_DATA")
        col.operator("armature.distribute_bones_evenly", icon="CURVE_PATH")
        col.operator("armature.align_bones", icon="CON_TRACKTO")
        col.operator("armature.align_bone_rolls", icon="ORIENTATION_GIMBAL")
        col.operator("armature.normalize_bone_roll", icon="TRACKING_CLEAR_BACKWARDS")
        col.operator("armature.generate_twist_bones", icon="FORCE_MAGNETIC")
        col.operator("armature.generate_blend_bone", icon="ORIENTATION_GLOBAL")
        col.separator()
        col.operator("armature.build_control_rig", icon="ARMATURE_DATA")
        col.operator("armature.remove_control_rig", icon="X")


class YelloAnimationView3dPanel(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Animation"
    bl_category = "Yello"
    bl_order = 3

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        col = layout.column(align=True)
        col.operator("object.export_animation", icon="ONIONSKIN_ON")
        col.operator("object.export_animated_mesh", icon="MOD_SOFT")
        col.operator("armature.export_actions", icon="RENDER_ANIMATION")
        col.separator()
        col.operator("armature.transfer_animation", icon="ANIM_DATA")


class YelloShadingView3dPanel(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Shading"
    bl_category = "Yello"
    bl_order = 4

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        col = layout.column(align=True)
        col.operator("object.smooth_normals", icon="MOD_SMOOTH")
        col.operator("object.reset_normals", icon="X")
        col.operator("object.set_vertex_color", icon="VPAINT_HLT")


class YelloModelingView3dPanel(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Modeling"
    bl_category = "Yello"
    bl_order = 1

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        col = layout.column(align=True)
        col.operator("object.slice_meshes_with_collection", icon="MOD_BUILD")
        col.separator()
        col.operator("object.export_mesh", icon="MESH_MONKEY")
        col.operator("object.export_meshes", icon="COMMUNITY")
