import bpy
import logging

from . import rigging

logger = logging.getLogger(__name__)

RETARGET_CONSTRAINT_NAME: str = "Retarget"


def has_control_rig(skeleton: bpy.types.Object) -> bool:
    """Return True if the skeleton contains at least one control bone."""
    return any(rigging.CONTROL_SUFFIX in bone.name for bone in skeleton.data.bones)


def add_retarget_constraints(
    target_skeleton: bpy.types.Object,
    source_skeleton: bpy.types.Object,
    bone_mapping: dict[str, str],
) -> int:
    """Add COPY_TRANSFORMS constraints on target control bones driven by source bones.

    bone_mapping maps source bone name to target control bone name.
    Returns the number of constraints successfully added.
    """
    count = 0
    for source_bone_name, target_bone_name in bone_mapping.items():
        target_pose_bone = target_skeleton.pose.bones.get(target_bone_name)
        if target_pose_bone is None:
            logger.warning("Target bone '%s' not found, skipping.", target_bone_name)
            continue
        if source_bone_name not in source_skeleton.pose.bones:
            logger.warning("Source bone '%s' not found, skipping.", source_bone_name)
            continue
        constraint = target_pose_bone.constraints.new("COPY_TRANSFORMS")
        constraint.name = RETARGET_CONSTRAINT_NAME
        constraint.target = source_skeleton
        constraint.subtarget = source_bone_name
        constraint.target_space = "WORLD"
        constraint.owner_space = "WORLD"
        count += 1
    return count


def remove_retarget_constraints(target_skeleton: bpy.types.Object) -> None:
    """Remove all retargeting constraints from the target skeleton's pose bones."""
    for pose_bone in target_skeleton.pose.bones:
        for constraint in list(pose_bone.constraints):
            if constraint.name == RETARGET_CONSTRAINT_NAME:
                pose_bone.constraints.remove(constraint)


def bake_retarget_action(
    target_skeleton: bpy.types.Object,
    frame_start: int,
    frame_end: int,
    action_name: str,
) -> bpy.types.Action | None:
    """Bake the constrained control bone animation to keyframes and return the action.

    Must be called in POSE mode with the target skeleton active. Selects only
    control bones before baking so deform bones are left untouched.
    """
    for pose_bone in target_skeleton.pose.bones:
        pose_bone.bone.select = rigging.CONTROL_SUFFIX in pose_bone.name

    bpy.ops.nla.bake(
        frame_start=frame_start,
        frame_end=frame_end,
        only_selected=True,
        visual_keying=True,
        clear_constraints=False,
        bake_types={"POSE"},
    )

    action = None
    if target_skeleton.animation_data and target_skeleton.animation_data.action:
        action = target_skeleton.animation_data.action
        action.name = action_name
        action.use_fake_user = True
    return action
