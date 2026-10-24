import datetime
import json
import os
import struct

import bpy
import numpy as np

from . import contexts, vertex_animation
from .misc import make_writable, select_objects

GLB_HEADER = struct.Struct("<4sII")
GLB_CHUNK_HEADER = struct.Struct("<I4s")
VERTEX_ANIMATION_UV_NAME = "VertexAnimation"


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


def read_world_vertices(
    obj: bpy.types.Object, depsgraph: bpy.types.Depsgraph
) -> tuple[np.ndarray, np.ndarray]:
    """Return the evaluated vertex positions and normals of an object in world space."""
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    positions = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    normals = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", positions)
    mesh.vertex_normals.foreach_get("vector", normals)
    evaluated.to_mesh_clear()
    matrix = evaluated.matrix_world
    linear = np.array(matrix.to_3x3(), dtype=np.float32)
    normal_matrix = np.array(
        matrix.to_3x3().inverted_safe().transposed(), dtype=np.float32
    )
    positions = positions.reshape(-1, 3) @ linear.T + np.array(matrix.translation)
    normals = normals.reshape(-1, 3) @ normal_matrix.T
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    return positions, normals / np.maximum(lengths, 1e-12)


def add_vertex_animation_uvs(mesh: bpy.types.Mesh, texels: np.ndarray) -> None:
    """Keep the render UV map first and add a second holding each vertex's texel."""
    uv_layers = mesh.uv_layers
    kept = next((layer.name for layer in uv_layers if layer.active_render), None)
    for name in [layer.name for layer in uv_layers if layer.name != kept]:
        uv_layers.remove(uv_layers[name])
    if kept is None:
        uv_layers.new(name="UVMap")
    else:
        uv_layers[kept].name = "UVMap"
    layer = uv_layers.new(name=VERTEX_ANIMATION_UV_NAME)
    loop_vertices = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_vertices)
    coordinates = texels[loop_vertices].astype(np.float32)
    # The glTF exporter writes V as 1 - V, so the texel's row comes out whole.
    coordinates[:, 1] = 1.0 - coordinates[:, 1]
    layer.uv.foreach_set("vector", coordinates.ravel())


def create_vertex_animation_object(
    objects: list[bpy.types.Object],
    depsgraph: bpy.types.Depsgraph,
    texels: np.ndarray,
    name: str,
) -> bpy.types.Object:
    """Join world space copies of the evaluated objects, each vertex knowing its texel."""
    pieces = []
    offset = 0
    for obj in objects:
        mesh = bpy.data.meshes.new_from_object(
            obj.evaluated_get(depsgraph),
            preserve_all_data_layers=True,
            depsgraph=depsgraph,
        )
        mesh.transform(obj.matrix_world)
        if obj.matrix_world.is_negative:
            mesh.flip_normals()
        vertex_count = len(mesh.vertices)
        add_vertex_animation_uvs(mesh, texels[offset : offset + vertex_count])
        offset += vertex_count
        piece = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(piece)
        pieces.append(piece)
    meshes = [piece.data for piece in pieces]
    joined = pieces[0]
    if len(pieces) > 1:
        with contexts.SelectionContext():
            select_objects(pieces)
            bpy.ops.object.join()
    for mesh in meshes:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    joined.name = name
    joined.data.name = name
    return joined


def write_exr(filename: str, pixels: np.ndarray) -> None:
    """Write top down RGBA rows to a lossless 32 bit float EXR."""
    height, width, _ = pixels.shape
    name = os.path.basename(filename)
    image = bpy.data.images.new(name, width, height, alpha=True, float_buffer=True)
    image.colorspace_settings.name = "Non-Color"
    # Blender stores image rows bottom up.
    image.pixels.foreach_set(np.flipud(pixels).ravel())
    scene = bpy.data.scenes.new(name)
    settings = scene.render.image_settings
    settings.file_format = "OPEN_EXR"
    settings.color_depth = "32"
    settings.color_mode = "RGBA"
    settings.exr_codec = "ZIP"
    try:
        make_writable(filename)
        image.save_render(filename, scene=scene)
    finally:
        bpy.data.images.remove(image)
        bpy.data.scenes.remove(scene)


def write_png(filename: str, pixels: np.ndarray) -> None:
    """Write top down rows of values from 0 to 1 to an 8 bit RGBA PNG."""
    make_writable(filename)
    with open(filename, "wb") as handle:
        handle.write(vertex_animation.encode_png(pixels))


def export_vertex_animation_texture(
    objects: list[bpy.types.Object],
    filename: str,
    normals: str = vertex_animation.NORMALS_PACKED_IN_ALPHA,
) -> None:
    """Export meshes to a GLB and an EXR beside it of their vertices on every frame."""
    scene = bpy.context.scene
    frames = range(scene.frame_start, scene.frame_end + 1)
    current_frame = scene.frame_current
    positions = []
    frame_normals = []
    try:
        for frame in frames:
            scene.frame_set(frame)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            vertices = [read_world_vertices(obj, depsgraph) for obj in objects]
            positions.append(np.concatenate([position for position, _ in vertices]))
            frame_normals.append(np.concatenate([normal for _, normal in vertices]))
            if len(positions[-1]) != len(positions[0]):
                raise ValueError(f"The vertex count changes on frame {frame}.")
        scene.frame_set(frames[0])
        stem = os.path.splitext(filename)[0]
        texels = vertex_animation.get_vertex_texels(len(positions[0]))
        base = create_vertex_animation_object(
            objects,
            bpy.context.evaluated_depsgraph_get(),
            texels,
            os.path.basename(stem),
        )
    finally:
        scene.frame_set(current_frame)

    positions = vertex_animation.to_y_up(np.stack(positions))
    texture, normal_map = vertex_animation.pack_textures(
        positions, vertex_animation.to_y_up(np.stack(frame_normals)), normals
    )
    base.data["vertex_animation"] = {
        "frame_count": len(frames),
        "frames_per_second": scene.render.fps / scene.render.fps_base,
        "bounds_min": positions.min(axis=(0, 1)).tolist(),
        "bounds_max": positions.max(axis=(0, 1)).tolist(),
        "normals": normals.lower(),
    }
    mesh = base.data
    try:
        write_exr(stem + ".exr", texture)
        if normal_map is not None:
            write_png(stem + "_normals.png", normal_map)
        make_writable(filename)
        with contexts.SelectionContext():
            select_objects([base])
            bpy.ops.export_scene.gltf(
                filepath=filename,
                check_existing=False,
                use_selection=True,
                use_visible=False,
                export_format="GLB",
                export_yup=True,
                export_animations=False,
                export_extras=True,
                export_copyright=f"© {datetime.datetime.now().year} Douglas Lassance",
            )
    finally:
        bpy.data.objects.remove(base)
        bpy.data.meshes.remove(mesh)
