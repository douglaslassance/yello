import bpy

from . import contexts
from .misc import select_objects, make_writable


def export_fbx(
    objects: list[bpy.types.Object],
    filename: str,
    animations: bool = False,
    object_types: set[str] | None = None,
) -> None:
    """Export objects to FBX with rigging-friendly defaults."""
    if object_types is None:
        object_types = {"MESH", "ARMATURE"}
    with contexts.SelectionContext():
        select_objects(objects)
        make_writable(filename)
        bpy.ops.export_scene.fbx(
            add_leaf_bones=False,
            apply_scale_options="FBX_SCALE_NONE",
            apply_unit_scale=True,
            armature_nodetype="NULL",
            axis_forward="-Z",
            axis_up="Y",
            bake_anim=animations,
            bake_space_transform=False,
            filepath=filename,
            global_scale=1.0,
            mesh_smooth_type="FACE",
            object_types=object_types,
            primary_bone_axis="Y",
            secondary_bone_axis="X",
            use_selection=True,
            use_space_transform=True,
        )


def export_gltf(
    objects: list[bpy.types.Object],
    filename: str,
    animations: bool = True,
    save_settings: bool = False,
) -> None:
    """https://docs.blender.org/api/current/bpy.ops.export_scene.html#module-bpy.ops.export_scene"""
    with contexts.SelectionContext():
        select_objects(objects)
        make_writable(filename)
        bpy.ops.export_scene.gltf(
            export_animations=animations,
            export_apply=True,
            export_def_bones=True,
            export_format="GLB",
            filepath=filename,
            use_selection=True,
            use_visible=True,
            will_save_settings=save_settings,
        )
