import json
import struct

import bpy

from . import contexts
from .misc import select_objects, make_writable

GLB_HEADER = struct.Struct("<4sII")
GLB_CHUNK_HEADER = struct.Struct("<I4s")


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


def import_fbx(filepath: str) -> list[bpy.types.Object]:
    """Import an FBX file and return the objects it added to the scene."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=filepath)
    return [obj for obj in bpy.data.objects if obj not in before]


def import_gltf(filepath: str) -> list[bpy.types.Object]:
    """Import a glTF or GLB file and return the objects it added to the scene."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=filepath)
    return [obj for obj in bpy.data.objects if obj not in before]


def append_blend(filepath: str) -> list[bpy.types.Object]:
    """Append all objects from a blend file and return the ones added."""
    before = set(bpy.data.objects)
    with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
        data_to.objects = list(data_from.objects)
    for obj in data_to.objects:
        if obj is not None:
            bpy.context.scene.collection.objects.link(obj)
    return [obj for obj in bpy.data.objects if obj not in before]


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


def read_glb(filepath: str) -> tuple[dict, bytes]:
    """Return the JSON document of a GLB file and the raw chunks that follow it."""
    with open(filepath, "rb") as handle:
        data = handle.read()
    magic, _, _ = GLB_HEADER.unpack_from(data)
    if magic != b"glTF":
        raise ValueError(f"Not a GLB file: {filepath}")
    json_length, _ = GLB_CHUNK_HEADER.unpack_from(data, GLB_HEADER.size)
    json_start = GLB_HEADER.size + GLB_CHUNK_HEADER.size
    json_end = json_start + json_length
    return json.loads(data[json_start:json_end]), data[json_end:]


def write_glb(filepath: str, document: dict, trailing_chunks: bytes) -> None:
    """Write a GLB file from a JSON document and the raw chunks that follow it."""
    json_bytes = json.dumps(document, separators=(",", ":"), ensure_ascii=False)
    json_bytes = json_bytes.encode("utf-8")
    json_bytes += b" " * (-len(json_bytes) % 4)
    length = (
        GLB_HEADER.size + GLB_CHUNK_HEADER.size + len(json_bytes) + len(trailing_chunks)
    )
    with open(filepath, "wb") as handle:
        handle.write(GLB_HEADER.pack(b"glTF", 2, length))
        handle.write(GLB_CHUNK_HEADER.pack(len(json_bytes), b"JSON"))
        handle.write(json_bytes)
        handle.write(trailing_chunks)


def add_glb_action_markers(filepath: str) -> int:
    """Add each action's pose markers to its GLB animation extras and count them."""
    document, trailing_chunks = read_glb(filepath)
    render = bpy.context.scene.render
    # Matches the glTF exporter's own frame to seconds conversion.
    frames_per_second = render.fps * render.fps_base
    tagged = 0
    for animation in document.get("animations", []):
        action = bpy.data.actions.get(animation.get("name", ""))
        if action is None or not action.pose_markers:
            continue
        markers = sorted(action.pose_markers, key=lambda marker: marker.frame)
        animation.setdefault("extras", {})["markers"] = [
            {
                "name": marker.name,
                "frame": marker.frame,
                "time": marker.frame / frames_per_second,
            }
            for marker in markers
        ]
        tagged += 1
    if tagged:
        write_glb(filepath, document, trailing_chunks)
    return tagged
