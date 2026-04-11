import os
import logging
import subprocess
from typing import Any

import bpy
import mathutils

from bpy.types import Mesh, Attribute
from bmesh.types import BMesh, BMLayerItem

from . import contexts

logger = logging.getLogger(__name__)


def create_collection(name: str = "Collection") -> bpy.types.Collection:
    if name not in bpy.data.collections:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
    else:
        collection = bpy.data.collections[name]
    return collection


def add_object_to_collection(
    obj: bpy.types.Object, collection: bpy.types.Collection
) -> None:
    if obj.name not in bpy.data.collections[collection.name]:
        bpy.data.collections[collection.name].objects.link(obj)


def apply_all_modifiers(obj: bpy.types.Object) -> None:
    """Apply all modifiers on an object."""
    with contexts.SelectionContext():
        select_objects([obj])
        for modifier in obj.modifiers:
            bpy.ops.object.modifier_apply(modifier=modifier.name)


def remove_object_from_all_collections(obj: bpy.types.Object) -> None:
    for col in obj.users_collection:
        col.objects.unlink(obj)
    bpy.data.scenes["Scene"].collection.objects.link(obj)


def run_command(command: list[str]) -> int:
    process = subprocess.Popen(
        command,
        cwd=os.path.dirname(bpy.data.filepath),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    output, err = process.communicate()
    if output:
        logger.warning(output)
    if err:
        logger.error(err)
    return process.returncode


def run_gitalong_command(command: list[str]) -> int | None:
    try:
        return run_command(["gitalong"] + command)
    except FileNotFoundError:
        logger.warning("Gitalong not found.")
    return None


def lock_file(filename: str) -> bool | int:
    """Lock a file using Git LFS."""
    if not os.path.exists(filename):
        return False
    command = ["git", "lfs", "lock", os.path.join(".", os.path.basename(filename))]
    return run_command(command)


def has_conflict(filename: str) -> bool | int | None:
    """Check if Gitalong says we'd have a conflicting touching this file."""
    if not os.path.exists(filename):
        return False
    command = ["has-conflict", os.path.join(".", os.path.basename(filename))]
    return run_gitalong_command(command)


def make_writable(filename: str) -> bool | int | None:
    """Make file writable safely using Gitalong."""
    if not os.path.exists(filename):
        return False
    command = ["make-writable", os.path.join(".", os.path.basename(filename))]
    return run_gitalong_command(command)


def get_projected_vector(
    vector: mathutils.Vector, normal: mathutils.Vector
) -> mathutils.Vector:
    """Project a vector onto a plane defined by a normalized normal vector."""
    return vector - normal * vector.dot(normal)


def validate_bone_chain(
    editable_bones: Any, minimum: int = 2
) -> tuple[list[Any] | None, str | None]:
    """Validate that editable bones form a connected chain of at least minimum length.

    Returns the chain sorted root-to-tip, or None if validation fails.
    The second return value is an error message (or None on success).
    """
    if not editable_bones or len(editable_bones) < minimum:
        return None, f"A minimum of {minimum} bones should be selected"
    bone_set = set(editable_bones)
    roots = [bone for bone in bone_set if bone.parent not in bone_set]
    if len(roots) != 1:
        return None, "Selected bones need to be connected"
    chain = []
    bone = roots[0]
    while bone in bone_set:
        chain.append(bone)
        children_in_set = [child for child in bone.children if child in bone_set]
        if not children_in_set:
            break
        if len(children_in_set) > 1:
            return None, "Selected bones need to be connected"
        bone = children_in_set[0]
    if len(chain) != len(bone_set):
        return None, "Selected bones need to be connected"
    return chain, None


def select_objects(objects: list[bpy.types.Object]) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]


def get_children(
    obj: bpy.types.Object, recursive: bool = False
) -> list[bpy.types.Object]:
    """Return the children of an object.

    When recursive is True, includes all descendants in depth-first order.
    """
    children = list(obj.children)
    if recursive:
        for child in obj.children:
            children.extend(get_children(child, recursive=True))
    return children


def duplicate_object(obj: bpy.types.Object) -> bpy.types.Object:
    with contexts.SelectionContext():
        select_objects([obj])
        bpy.ops.object.duplicate()
        return bpy.context.selected_objects[0]


def apply_transforms(
    obj: bpy.types.Object,
    location: bool = True,
    rotation: bool = True,
    scale: bool = True,
) -> None:
    with contexts.SelectionContext():
        select_objects([obj])
        bpy.ops.object.transform_apply(
            location=location, rotation=rotation, scale=scale
        )


def join_objects(objects: list[bpy.types.Object]) -> bpy.types.Object | None:
    joinables = []
    for obj in objects:
        if obj.type == "MESH":
            joinables.append(obj)
    if not joinables:
        return None
    duplicates = []
    for joinable in joinables:
        duplicates.append(duplicate_object(joinable))
    for duplicate in duplicates:
        apply_all_modifiers(duplicate)
    with contexts.SelectionContext():
        select_objects(duplicates)
        bpy.ops.object.join()
        joined_mesh = bpy.context.selected_objects[0]
    apply_transforms(joined_mesh)
    return joined_mesh


def delete_objects(objects: list[bpy.types.Object]) -> None:
    with contexts.SelectionContext():
        select_objects(objects)
        bpy.ops.object.delete()


def get_active_color_attribute(mesh: Mesh, create: bool = False) -> Attribute | None:
    """Get the active color attribute."""
    if mesh.color_attributes:
        return mesh.color_attributes.active_color
    elif create:
        color_attribute = mesh.color_attributes.new(
            name="Color", type="FLOAT_COLOR", domain="CORNER"
        )
        for datum in color_attribute.data:
            datum.color = (0.0, 0.0, 0.0, 0.0)
        return color_attribute
    return None


def get_color_attribute_layer(
    bm: BMesh, color_attribute: Attribute
) -> BMLayerItem | None:
    if color_attribute.domain == "CORNER":
        if color_attribute.data_type == "FLOAT_COLOR":
            return bm.loops.layers.float_color.get(color_attribute.name)
        return bm.loops.layers.color.get(color_attribute.name)
    elif color_attribute.domain == "POINT":
        if color_attribute.data_type == "FLOAT_COLOR":
            return bm.verts.layers.float_color.get(color_attribute.name)
        return bm.verts.layers.color.get(color_attribute.name)
    return None
