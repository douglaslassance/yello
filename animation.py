import bpy
import logging

logger = logging.getLogger(__name__)


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

    target_action = bpy.data.actions.get(target_action_name)
    if target_action is source_action:
        target_action = bpy.data.actions.new(target_action_name)
    elif target_action is not None:
        existing_fcurves = get_action_fcurves(target_action)
        if existing_fcurves is not None:
            for fcurve in list(existing_fcurves):
                existing_fcurves.remove(fcurve)
    else:
        target_action = bpy.data.actions.new(target_action_name)

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
