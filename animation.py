import logging

import bpy
import mathutils

from .contexts import AnimationContext

logger = logging.getLogger(__name__)

TRANSFER_METHOD_COPY: str = "COPY"
TRANSFER_METHOD_BAKE: str = "BAKE"

SOURCE_ARMATURE_MINIMUM_COVERAGE: float = 0.5
STATIC_CURVE_TOLERANCE: float = 1e-6

OBJECT_TRANSFORM_DATA_PATHS = {
    "location",
    "rotation_euler",
    "rotation_quaternion",
    "rotation_axis_angle",
    "scale",
    "delta_location",
    "delta_rotation_euler",
    "delta_rotation_quaternion",
    "delta_scale",
}


IMPORT_METHOD_BAKE: str = "BAKE"
IMPORT_METHOD_COPY: str = "COPY"


def match_rotation_modes(
    source: bpy.types.Object, target: bpy.types.Object, bone_mapping: dict[str, str]
) -> None:
    """Give each mapped target bone its source bone's rotation mode."""
    for source_bone, target_bone in bone_mapping.items():
        source_mode = source.pose.bones[source_bone].rotation_mode
        target.pose.bones[target_bone].rotation_mode = source_mode


def assign_action(obj: bpy.types.Object, action: bpy.types.Action) -> None:
    """Assign an action to an object, creating animation data and binding its slot.

    On Blender 4.4+ slotted actions, the first slot is bound so the action
    evaluates on the object.
    """
    if obj.animation_data is None:
        obj.animation_data_create()
    obj.animation_data.action = action
    if hasattr(obj.animation_data, "action_slot") and action.slots:
        obj.animation_data.action_slot = action.slots[0]


def get_action_bone_names(action: bpy.types.Action) -> list[str]:
    """Return the unique bone names referenced by pose bone fcurves in the action."""
    fcurves = get_action_fcurves(action)
    if fcurves is None:
        return []
    bone_names = []
    for fcurve in fcurves:
        if fcurve.data_path.startswith('pose.bones["'):
            name = fcurve.data_path.split('"')[1]
            if name not in bone_names:
                bone_names.append(name)
    return bone_names


def get_action_fcurves(action: bpy.types.Action):
    """Return the fcurves collection of an existing action.

    Supports both the legacy flat API (Blender < 4.4) where fcurves live
    directly on the action, and the layered API (Blender 4.4+) where they
    live on the first channelbag of the first strip of the first layer.
    Returns None if no fcurves collection is found.
    """
    if hasattr(action, "fcurves"):
        return action.fcurves
    for layer in action.layers:
        for strip in layer.strips:
            if hasattr(strip, "channelbags") and strip.channelbags:
                return strip.channelbags[0].fcurves
    return None


def get_object_transform_fcurves(action: bpy.types.Action) -> list[bpy.types.FCurve]:
    """Return the fcurves animating the object's own transform rather than its bones."""
    fcurves = get_action_fcurves(action)
    if fcurves is None:
        return []
    return [
        fcurve for fcurve in fcurves if fcurve.data_path in OBJECT_TRANSFORM_DATA_PATHS
    ]


def ensure_action_fcurves(action: bpy.types.Action):
    """Return the fcurves collection of an action, creating the structure if needed.

    For existing actions behaves identically to get_action_fcurves. For new
    empty actions using the Blender 4.4+ layered API, creates the required
    layer, strip, slot, and channelbag before returning the fcurves collection.
    """
    existing = get_action_fcurves(action)
    if existing is not None:
        return existing
    if hasattr(action, "fcurves"):
        return action.fcurves
    layer = action.layers.new("Layer") if not action.layers else action.layers[0]
    strip = layer.strips.new(type="KEYFRAME") if not layer.strips else layer.strips[0]
    if strip.channelbags:
        return strip.channelbags[0].fcurves
    slot = (
        action.slots.new(id_type="OBJECT", name="Object")
        if not action.slots
        else action.slots[0]
    )
    return strip.channelbags.new(slot).fcurves


def copy_and_remap_animation(
    source_action: bpy.types.Action,
    target_action_name: str,
    bone_mapping: dict[str, str],
) -> bpy.types.Action | None:
    """Copy fcurves from source_action into a new action with bone names remapped.

    For each fcurve whose data_path contains a bone name present in bone_mapping,
    a copy is written into the target action with the bone name substituted.
    Fcurves that do not match any mapped bone are skipped.

    An existing action named target_action_name is cleared and reused. If that
    name matches the source action itself, a new uniquely-named action is created
    to avoid overwriting the source.

    Returns the target action, or None if source fcurves could not be read.
    """
    source_fcurves = get_action_fcurves(source_action)
    if source_fcurves is None:
        logger.warning("Could not read fcurves from action '%s'", source_action.name)
        return None

    target_action = _prepare_target_action(source_action, target_action_name)
    target_fcurves = ensure_action_fcurves(target_action)
    if target_fcurves is None:
        return None

    for fcurve in source_fcurves:
        data_path = fcurve.data_path
        new_data_path = None
        target_bone = None
        for source_bone, mapped_bone in bone_mapping.items():
            if f'"{source_bone}"' in data_path:
                new_data_path = data_path.replace(
                    f'"{source_bone}"', f'"{mapped_bone}"'
                )
                target_bone = mapped_bone
                break
        if new_data_path is None:
            continue
        new_fcurve = target_fcurves.new(
            data_path=new_data_path,
            index=fcurve.array_index,
            group_name=target_bone,
        )
        for keyframe in fcurve.keyframe_points:
            new_fcurve.keyframe_points.insert(
                frame=keyframe.co[0],
                value=keyframe.co[1],
                options={"FAST"},
            )
        for i, keyframe in enumerate(fcurve.keyframe_points):
            new_fcurve.keyframe_points[i].interpolation = keyframe.interpolation
        new_fcurve.update()

    return target_action


def _prepare_target_action(
    source_action: bpy.types.Action, target_action_name: str
) -> bpy.types.Action:
    """Return an empty action named target_action_name, never the source action itself."""
    target_action = bpy.data.actions.get(target_action_name)
    if target_action is None or target_action is source_action:
        return bpy.data.actions.new(target_action_name)
    existing_fcurves = get_action_fcurves(target_action)
    if existing_fcurves is not None:
        for fcurve in list(existing_fcurves):
            existing_fcurves.remove(fcurve)
    return target_action


def get_animated_location_bone_names(action: bpy.types.Action) -> set[str]:
    """Return the bones whose location fcurves change value over the action."""
    fcurves = get_action_fcurves(action)
    if fcurves is None:
        return set()
    bone_names = set()
    for fcurve in fcurves:
        data_path = fcurve.data_path
        if not data_path.startswith('pose.bones["') or not data_path.endswith(
            ".location"
        ):
            continue
        values = [point.co[1] for point in fcurve.keyframe_points]
        if values and max(values) - min(values) > STATIC_CURVE_TOLERANCE:
            bone_names.add(data_path.split('"')[1])
    return bone_names


def find_source_armature(
    action: bpy.types.Action, candidates: list[bpy.types.Object]
) -> bpy.types.Object | None:
    """Return the candidate armature holding most of the action's bones, preferring one playing it."""
    bone_names = get_action_bone_names(action)
    minimum_coverage = len(bone_names) * SOURCE_ARMATURE_MINIMUM_COVERAGE
    best_armature = None
    best_rank = (0, False)
    for candidate in candidates:
        coverage = sum(1 for name in bone_names if name in candidate.data.bones)
        if coverage == 0 or coverage < minimum_coverage:
            continue
        animation_data = candidate.animation_data
        playing = animation_data is not None and animation_data.action == action
        if (coverage, playing) > best_rank:
            best_armature = candidate
            best_rank = (coverage, playing)
    return best_armature


def _mapped_ancestor(bone: bpy.types.Bone, mapped_names) -> str | None:
    """Return the name of the closest ancestor of bone found in mapped_names."""
    parent = bone.parent
    while parent is not None:
        if parent.name in mapped_names:
            return parent.name
        parent = parent.parent
    return None


def _rest_world_transforms(
    armature: bpy.types.Object, bone_names
) -> dict[str, tuple[mathutils.Vector, mathutils.Quaternion]]:
    """Return the rest head and orientation of each bone in world space."""
    transforms = {}
    for name in bone_names:
        matrix = armature.matrix_world @ armature.data.bones[name].matrix_local
        transforms[name] = (matrix.translation.copy(), matrix.to_quaternion())
    return transforms


def _sample_world_transforms(
    armature: bpy.types.Object, bone_names, frames: range
) -> dict[str, list[tuple[mathutils.Vector, mathutils.Quaternion]]]:
    """Return the evaluated head and orientation of each bone in world space at every frame."""
    scene = bpy.context.scene
    samples = {name: [] for name in bone_names}
    for frame in frames:
        scene.frame_set(frame)
        evaluated = armature.evaluated_get(bpy.context.evaluated_depsgraph_get())
        for name in bone_names:
            matrix = evaluated.matrix_world @ evaluated.pose.bones[name].matrix
            samples[name].append((matrix.translation.copy(), matrix.to_quaternion()))
    return samples


def _proportion_scale(
    target: bpy.types.Object,
    target_to_source: dict[str, str],
    source_rest: dict[str, tuple[mathutils.Vector, mathutils.Quaternion]],
    target_rest: dict[str, tuple[mathutils.Vector, mathutils.Quaternion]],
) -> float:
    """Return the ratio of target to source joint spacing along the mapped hierarchy."""
    source_length = 0.0
    target_length = 0.0
    for target_bone, source_bone in target_to_source.items():
        ancestor = _mapped_ancestor(target.data.bones[target_bone], target_to_source)
        if ancestor is None:
            continue
        target_length += (target_rest[target_bone][0] - target_rest[ancestor][0]).length
        source_ancestor = target_to_source[ancestor]
        source_length += (
            source_rest[source_bone][0] - source_rest[source_ancestor][0]
        ).length
    if source_length == 0.0 or target_length == 0.0:
        return 1.0
    return target_length / source_length


def _rotation_channel(
    rotation_mode: str, rotations: list[mathutils.Quaternion]
) -> tuple[str, list[tuple[float, ...]]]:
    """Return the rotation data path and continuous per frame values for a rotation mode."""
    values = []
    if rotation_mode == "QUATERNION":
        previous = None
        for rotation in rotations:
            if previous is not None and previous.dot(rotation) < 0.0:
                rotation = -rotation
            values.append(tuple(rotation))
            previous = rotation
        return "rotation_quaternion", values
    if rotation_mode == "AXIS_ANGLE":
        for rotation in rotations:
            axis, angle = rotation.to_axis_angle()
            values.append((angle, *axis))
        return "rotation_axis_angle", values
    previous = None
    for rotation in rotations:
        if previous is None:
            euler = rotation.to_euler(rotation_mode)
        else:
            euler = rotation.to_euler(rotation_mode, previous)
        values.append(tuple(euler))
        previous = euler
    return "rotation_euler", values


def _write_baked_fcurves(
    fcurves,
    data_path: str,
    group_name: str,
    frames: range,
    values: list[tuple[float, ...]],
) -> None:
    """Write one fcurve per channel of values, keyed on every frame."""
    for index in range(len(values[0])):
        fcurve = fcurves.new(data_path=data_path, index=index, group_name=group_name)
        fcurve.keyframe_points.add(len(frames))
        coordinates = []
        for frame, value in zip(frames, values):
            coordinates.extend((frame, value[index]))
        fcurve.keyframe_points.foreach_set("co", coordinates)
        fcurve.update()


def bake_remapped_animation(
    source: bpy.types.Object,
    source_action: bpy.types.Action,
    target: bpy.types.Object,
    target_action_name: str,
    bone_mapping: dict[str, str],
) -> bpy.types.Action | None:
    """Play source_action on source and key every frame of its rest-relative motion onto target's mapped bones."""
    target_to_source = {}
    for source_bone, target_bone in bone_mapping.items():
        if source_bone in source.pose.bones and target_bone in target.pose.bones:
            target_to_source.setdefault(target_bone, source_bone)
    if not target_to_source:
        return None

    source_rest = _rest_world_transforms(source, target_to_source.values())
    target_rest = _rest_world_transforms(target, target_to_source)
    scale = _proportion_scale(target, target_to_source, source_rest, target_rest)
    animated_locations = get_animated_location_bone_names(source_action)
    location_bones = {
        target_bone
        for target_bone, source_bone in target_to_source.items()
        if source_bone in animated_locations
        or _mapped_ancestor(target.data.bones[target_bone], target_to_source) is None
    }

    frame_start, frame_end = (int(frame) for frame in source_action.frame_range)
    frames = range(frame_start, frame_end + 1)
    scene = bpy.context.scene
    current_frame = scene.frame_current
    with AnimationContext(source):
        assign_action(source, source_action)
        samples = _sample_world_transforms(source, target_to_source.values(), frames)
    scene.frame_set(current_frame)

    target_world_inverted = target.matrix_world.inverted()
    target_world_rotation_inverted = target.matrix_world.to_quaternion().inverted()
    ordered_bones = sorted(
        target.data.bones, key=lambda bone: len(bone.parent_recursive)
    )
    identity = mathutils.Matrix.Identity(4)
    bases = {name: [] for name in target_to_source}
    for frame_index in range(len(frames)):
        pose_matrices = {}
        for bone in ordered_bones:
            parent_matrices = {}
            if bone.parent is not None:
                parent_matrices = {
                    "parent_matrix": pose_matrices[bone.parent.name],
                    "parent_matrix_local": bone.parent.matrix_local,
                }
            unposed = bone.convert_local_to_pose(
                identity, bone.matrix_local, **parent_matrices
            )
            source_bone = target_to_source.get(bone.name)
            if source_bone is None:
                pose_matrices[bone.name] = unposed
                continue
            source_head, source_rotation = samples[source_bone][frame_index]
            source_rest_head, source_rest_rotation = source_rest[source_bone]
            target_rest_head, target_rest_rotation = target_rest[bone.name]
            rotation = (
                target_world_rotation_inverted
                @ source_rotation
                @ source_rest_rotation.inverted()
                @ target_rest_rotation
            )
            head = unposed.translation
            if bone.name in location_bones:
                offset = (source_head - source_rest_head) * scale
                head = target_world_inverted @ (target_rest_head + offset)
            pose = mathutils.Matrix.LocRotScale(head, rotation, unposed.to_scale())
            pose_matrices[bone.name] = pose
            bases[bone.name].append(
                bone.convert_local_to_pose(
                    pose, bone.matrix_local, invert=True, **parent_matrices
                )
            )

    target_action = _prepare_target_action(source_action, target_action_name)
    target_fcurves = ensure_action_fcurves(target_action)
    if target_fcurves is None:
        return None
    for bone_name, bone_bases in bases.items():
        data_path_prefix = f'pose.bones["{bone_name}"]'
        rotation_mode = target.pose.bones[bone_name].rotation_mode
        rotation_path, rotation_values = _rotation_channel(
            rotation_mode, [basis.to_quaternion() for basis in bone_bases]
        )
        _write_baked_fcurves(
            target_fcurves,
            f"{data_path_prefix}.{rotation_path}",
            bone_name,
            frames,
            rotation_values,
        )
        if bone_name in location_bones:
            _write_baked_fcurves(
                target_fcurves,
                f"{data_path_prefix}.location",
                bone_name,
                frames,
                [tuple(basis.translation) for basis in bone_bases],
            )
    return target_action
