import bmesh
import bpy
import json
import math
import mathutils
import urllib.error
from pathlib import Path
from typing import Any, Callable

from . import dracula
from . import ollama

_PROMPTS_DIR: Path = Path(__file__).parent / "prompts"
_ASSETS_DIR: Path = Path(__file__).parent / "assets"
CONTROL_PREFIX: str = "CR_"

SystemDict = dict[str, Any]
BoneDataDict = dict[str, dict[str, Any]]


def _load_prompt(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


def classify_bones(bone_names: list[str]) -> tuple[list[SystemDict] | None, str, str]:
    """Ask Ollama to classify bone names into rig systems.

    Returns (systems, message, raw) where systems is a list of system dicts,
    or (None, error_message, raw).
    """
    bone_list = "\n".join(f"  - {n}" for n in sorted(bone_names))
    user_msg = _load_prompt("classify_bones_user.md").replace("{bone_list}", bone_list)
    system_msg = _load_prompt("classify_bones_system.md")
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]
    try:
        raw = ollama.chat(messages)
        data = json.loads(raw or "{}")
        systems = _parse_systems(data, bone_names)
        if systems:
            summary = []
            for system in systems:
                label = (
                    f"{system['type']}.{system.get('side', system.get('name', '-'))}"
                )
                if system["type"] == "leg":
                    label += f"(toe={'yes' if system.get('toe') else 'NO'})"
                summary.append(label)
            return systems, f"Identified: {summary}", raw
        return None, f"Could not parse systems from Ollama response: {raw[:300]}", raw
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        return None, f"Ollama HTTP {exc.code}: {body[:200]}", ""
    except Exception as exc:
        return None, f"Ollama error: {exc}", ""


def _parse_systems(data: dict[str, Any], bone_names: list[str]) -> list[SystemDict] | None:
    """Parse the systems array from Ollama JSON into validated dicts with resolved bone names."""
    lookup = {n.strip().lower(): n for n in bone_names}

    def resolve(v):
        return lookup.get(v.strip().lower()) if isinstance(v, str) else None

    def resolve_chain(lst):
        if not isinstance(lst, list):
            return []
        return [r for r in (resolve(n) for n in lst if isinstance(n, str)) if r]

    systems = []
    for entry in data.get("systems") or []:
        if not isinstance(entry, dict):
            continue
        system_type = entry.get("type")

        if system_type == "spine":
            vertebrae = resolve_chain(entry.get("vertebrae"))
            pelvis = resolve(entry.get("pelvis"))
            if vertebrae or pelvis:
                systems.append(
                    {
                        "type": "spine",
                        "pelvis": pelvis,
                        "vertebrae": vertebrae,
                    }
                )

        elif system_type == "arm":
            upper_arm = resolve(entry.get("upper_arm"))
            forearm = resolve(entry.get("forearm"))
            hand = resolve(entry.get("hand"))
            if not all([upper_arm, forearm, hand]):
                continue
            systems.append(
                {
                    "type": "arm",
                    "side": str(entry.get("side") or "L"),
                    "parent": entry.get("parent"),
                    "shoulder": resolve(entry.get("shoulder")),
                    "upper_arm": upper_arm,
                    "forearm": forearm,
                    "hand": hand,
                }
            )

        elif system_type == "leg":
            upper_leg = resolve(entry.get("upper_leg"))
            lower_leg = resolve(entry.get("lower_leg"))
            foot = resolve(entry.get("foot"))
            if not all([upper_leg, lower_leg, foot]):
                continue
            systems.append(
                {
                    "type": "leg",
                    "side": str(entry.get("side") or "L"),
                    "parent": entry.get("parent"),
                    "upper_leg": upper_leg,
                    "lower_leg": lower_leg,
                    "foot": foot,
                    "toe": resolve(entry.get("toe")),
                }
            )

        elif system_type == "head":
            head = resolve(entry.get("head"))
            if not head:
                continue
            systems.append(
                {
                    "type": "head",
                    "parent": entry.get("parent"),
                    "neck": resolve(entry.get("neck")),
                    "head": head,
                }
            )

        elif system_type == "finger":
            chain = resolve_chain(entry.get("chain"))
            name = entry.get("name")
            if not chain or not name:
                continue
            systems.append(
                {
                    "type": "finger",
                    "name": str(name).lower(),
                    "side": str(entry.get("side") or "L"),
                    "parent": entry.get("parent"),
                    "chain": chain,
                }
            )

    return systems or None


def extract_bone_names(systems: list[SystemDict]) -> set[str]:
    """Return the flat set of all deform bone names referenced by systems."""
    names = set()
    for system in systems:
        system_type = system["type"]
        if system_type == "spine":
            if system.get("pelvis"):
                names.add(system["pelvis"])
            names.update(system.get("vertebrae") or [])
        elif system_type == "arm":
            for key in ("shoulder", "upper_arm", "forearm", "hand"):
                if system.get(key):
                    names.add(system[key])
        elif system_type == "leg":
            for key in ("upper_leg", "lower_leg", "foot", "toe"):
                if system.get(key):
                    names.add(system[key])
        elif system_type == "head":
            for key in ("neck", "head"):
                if system.get(key):
                    names.add(system[key])
        elif system_type == "finger":
            names.update(system.get("chain") or [])
    return names


def get_or_create_shape(name: str, create_fn: Callable[[str], bpy.types.Object]) -> bpy.types.Object:
    """Return or create a mesh object to use as a custom bone shape.

    Any existing object of a different type (e.g. a stale Grease Pencil object
    from a previous build) is removed and recreated as a mesh.
    The caller is responsible for parenting the shape to the control rig armature.
    """
    obj = bpy.data.objects.get(name)
    if obj is not None:
        if obj.type == "MESH":
            return obj
        bpy.data.objects.remove(obj, do_unlink=True)
    return create_fn(name)


def get_or_load_shape(blend_name: str, display_name: str | None = None) -> bpy.types.Object | None:
    """Return or import a named mesh object from the bundled shapes.blend file.

    blend_name is the name of the object inside shapes.blend. If display_name is
    given the loaded object is renamed to it on first import, and subsequent calls
    look up by display_name. Returns None if the object cannot be found.
    """
    name = display_name or blend_name
    obj = bpy.data.objects.get(name)
    if obj is not None:
        if obj.type == "MESH":
            return obj
        bpy.data.objects.remove(obj, do_unlink=True)
    blend_path = _ASSETS_DIR / "shapes.blend"
    with bpy.data.libraries.load(str(blend_path), link=False) as (data_from, data_to):
        if blend_name in data_from.objects:
            data_to.objects = [blend_name]
    loaded = bpy.data.objects.get(blend_name)
    if loaded and display_name:
        loaded.name = display_name
    return bpy.data.objects.get(name)


def get_or_create_control_rig_container(skeleton: bpy.types.Object, name: str) -> bpy.types.Object:
    """Return or create a named Empty parented to the skeleton for grouping CR_ objects."""
    existing = bpy.data.objects.get(name)
    if existing:
        return existing
    container = bpy.data.objects.new(name, None)
    container.empty_display_type = "PLAIN_AXES"
    container.empty_display_size = 0.0
    for col in skeleton.users_collection:
        col.objects.link(container)
    container.parent = skeleton
    return container


def parent_to_control_rig(obj: bpy.types.Object, container: bpy.types.Object) -> None:
    """Link obj to the container's collections, parent it, and hide it from the viewport."""
    for col in container.users_collection:
        if obj.name not in col.objects:
            col.objects.link(obj)
    obj.parent = container
    obj.hide_viewport = True


def _wire_shape(name: str, strokes: list[tuple[list[tuple[float, float, float]], bool]]) -> bpy.types.Object:
    """Create a mesh bone-shape object built from wire edges.

    strokes: list of (points_list, cyclic) tuples where points_list is a
             sequence of (x, y, z) tuples and cyclic closes the loop.
    """
    mesh_builder = bmesh.new()
    for points, cyclic in strokes:
        verts = [mesh_builder.verts.new(coord) for coord in points]
        for i in range(len(verts) - 1):
            mesh_builder.edges.new((verts[i], verts[i + 1]))
        if cyclic and len(verts) > 1:
            mesh_builder.edges.new((verts[-1], verts[0]))
    mesh = bpy.data.meshes.new(name)
    mesh_builder.to_mesh(mesh)
    mesh_builder.free()
    return bpy.data.objects.new(name, mesh)


def create_circle_shape(name: str) -> bpy.types.Object:
    segment_count = 16
    points = [
        (
            math.cos(2 * math.pi * i / segment_count),
            0.0,
            math.sin(2 * math.pi * i / segment_count),
        )
        for i in range(segment_count)
    ]
    return _wire_shape(name, [(points, True)])


def create_box_shape(name: str) -> bpy.types.Object:
    half_size = 0.5
    coordinates = [
        (-half_size, -half_size, -half_size),
        (half_size, -half_size, -half_size),
        (half_size, half_size, -half_size),
        (-half_size, half_size, -half_size),
        (-half_size, -half_size, half_size),
        (half_size, -half_size, half_size),
        (half_size, half_size, half_size),
        (-half_size, half_size, half_size),
    ]
    edges = [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 4),
        (0, 4),
        (1, 5),
        (2, 6),
        (3, 7),
    ]
    return _wire_shape(
        name, [([coordinates[a], coordinates[b]], False) for a, b in edges]
    )


def create_diamond_shape(name: str) -> bpy.types.Object:
    half_size = 0.5
    coordinates = [
        (0, half_size, 0),
        (half_size, 0, 0),
        (0, -half_size, 0),
        (-half_size, 0, 0),
        (0, 0, half_size),
        (0, 0, -half_size),
    ]
    edges = [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),
        (0, 4),
        (4, 2),
        (2, 5),
        (5, 0),
        (1, 4),
        (1, 5),
        (3, 4),
        (3, 5),
    ]
    return _wire_shape(
        name, [([coordinates[a], coordinates[b]], False) for a, b in edges]
    )


def create_sphere_shape(name: str) -> bpy.types.Object:
    """Unit sphere approximated by three orthogonal circles."""
    segment_count = 16
    xy = [
        (
            math.cos(2 * math.pi * i / segment_count),
            math.sin(2 * math.pi * i / segment_count),
            0.0,
        )
        for i in range(segment_count)
    ]
    xz = [
        (
            math.cos(2 * math.pi * i / segment_count),
            0.0,
            math.sin(2 * math.pi * i / segment_count),
        )
        for i in range(segment_count)
    ]
    yz = [
        (
            0.0,
            math.cos(2 * math.pi * i / segment_count),
            math.sin(2 * math.pi * i / segment_count),
        )
        for i in range(segment_count)
    ]
    return _wire_shape(name, [(xy, True), (xz, True), (yz, True)])


def create_square_shape(name: str) -> bpy.types.Object:
    """Unit square with crosshairs in the XZ plane."""
    points = [(-1, 0, 1), (1, 0, 1), (1, 0, -1), (-1, 0, -1)]
    return _wire_shape(
        name,
        [
            (points, True),
            ([(-1, 0, 0), (1, 0, 0)], False),
            ([(0, 0, -1), (0, 0, 1)], False),
        ],
    )


def _calc_pole_pos(upper_head: mathutils.Vector, upper_tail: mathutils.Vector, lower_tail: mathutils.Vector) -> mathutils.Vector:
    """Calculate the knee/elbow pole target position.

    Places the pole at the knee joint, offset along the flipped bisector of the
    thigh/calf angle. The bisector of (v_to_hip + v_to_ankle) points into the
    concave side of the bend; flipping it gives the convex side the knee sticks
    out toward. Falls back to a world-forward projection for a straight leg.
    """
    knee = upper_tail
    v_to_hip = (upper_head - knee).normalized()
    v_to_ankle = (lower_tail - knee).normalized()
    bisector = v_to_hip + v_to_ankle
    dist = (upper_tail - upper_head).length

    if bisector.length > 1e-4:
        pole_dir = -bisector.normalized()
    else:
        leg_axis = (lower_tail - upper_head).normalized()
        world_fwd = mathutils.Vector((0.0, 1.0, 0.0))
        pole_dir = world_fwd - world_fwd.dot(leg_axis) * leg_axis
        if pole_dir.length < 1e-4:
            pole_dir = mathutils.Vector((1.0, 0.0, 0.0))
        else:
            pole_dir = pole_dir.normalized()

    return knee + pole_dir * dist


def _new_edit_bone(
    edit_bones: bpy.types.ArmatureEditBones,
    name: str,
    head: mathutils.Vector,
    tail: mathutils.Vector,
    roll: float,
    parent: bpy.types.EditBone | None = None,
    connect: bool = False,
) -> bpy.types.EditBone:
    edit_bone = edit_bones.new(name)
    edit_bone.head, edit_bone.tail, edit_bone.roll, edit_bone.use_deform = (
        head,
        tail,
        roll,
        False,
    )
    if parent:
        edit_bone.parent = parent
        edit_bone.use_connect = connect
    return edit_bone


def _connected(head: mathutils.Vector, parent_tail: mathutils.Vector) -> bool:
    return (head - parent_tail).length < 1e-4


def _side_color(side: str) -> tuple[float, float, float]:
    """Return the bone color for a given side: left=yellow, right=green, center=purple."""
    if side == "L":
        return dracula.YELLOW
    if side == "R":
        return dracula.GREEN
    return dracula.PURPLE


def _bone_color(pose_bone: bpy.types.PoseBone, color: tuple[float, float, float]) -> None:
    pose_bone.color.palette = "CUSTOM"
    pose_bone.color.custom.normal = color
    pose_bone.color.custom.select = tuple(min(1.0, c + 0.2) for c in color)
    pose_bone.color.custom.active = (1.0, 1.0, 1.0)


def _assign_shape(
    pose_bone: bpy.types.PoseBone,
    shape: bpy.types.Object,
    use_bone_size: bool = True,
    scale: float | tuple[float, float, float] = 1.0,
) -> None:
    """Assign a custom shape to a pose bone.

    scale can be a float for uniform scaling or a (x, y, z) tuple for per-axis scaling.
    """
    pose_bone.custom_shape = shape
    pose_bone.use_custom_shape_bone_size = use_bone_size
    if isinstance(scale, (int, float)):
        pose_bone.custom_shape_scale_xyz = (scale, scale, scale)
    else:
        pose_bone.custom_shape_scale_xyz = scale
    pose_bone.custom_shape_wire_width = 3.0


def _finger_ctrl_name(system: SystemDict, index: int) -> str:
    """Return the base control bone name for a finger bone at a given index (without CR_ prefix)."""
    return f"{system['name'].capitalize()}.{index + 1:03d}.{system['side']}"


def _build_spine_system(
    edit_bones: bpy.types.ArmatureEditBones,
    system: SystemDict,
    bone_data: BoneDataDict,
    root_edit_bone: bpy.types.EditBone,
) -> tuple[bpy.types.EditBone | None, bpy.types.EditBone, dict[str, bpy.types.EditBone]]:
    """Build spine FK control bones.

    Creates Pelvis and Hips at the base and a free Chest at the top.
    The deform vertebrae are driven by a Spline IK constraint added directly on the
    skeleton side in wire_deform_constraints — no mechanism bones are needed here.
    Returns (hips_edit_bone, chest_edit_bone, deform_to_ctrl).
    """
    deform_to_ctrl = {}
    pelvis_edit_bone = None
    hips_edit_bone = None

    if system.get("pelvis") and system["pelvis"] in bone_data:
        bone = bone_data[system["pelvis"]]
        bone_len = (bone["tail"] - bone["head"]).length
        pelvis_edit_bone = _new_edit_bone(
            edit_bones,
            f"{CONTROL_PREFIX}Pelvis",
            bone["head"],
            bone["tail"],
            bone["roll"],
            root_edit_bone,
            False,
        )
        direction = (bone["tail"] - bone["head"]).normalized()
        hips_tail = bone["head"] + direction * max(bone_len * 0.5, 0.05)
        hips_edit_bone = _new_edit_bone(
            edit_bones,
            f"{CONTROL_PREFIX}Hips",
            bone["head"],
            hips_tail,
            bone["roll"],
            pelvis_edit_bone,
            False,
        )
        deform_to_ctrl[system["pelvis"]] = pelvis_edit_bone

    chain = [n for n in (system.get("vertebrae") or []) if n in bone_data]
    chest_edit_bone = hips_edit_bone or pelvis_edit_bone or root_edit_bone

    if chain:
        last_bone = bone_data[chain[-1]]
        chest_edit_bone = _new_edit_bone(
            edit_bones,
            f"{CONTROL_PREFIX}Chest",
            last_bone["head"],
            last_bone["tail"],
            last_bone["roll"],
            pelvis_edit_bone or root_edit_bone,
            False,
        )

    return hips_edit_bone, chest_edit_bone, deform_to_ctrl


def _build_arm_system(
    edit_bones: bpy.types.ArmatureEditBones,
    system: SystemDict,
    bone_data: BoneDataDict,
    parent_edit_bone: bpy.types.EditBone,
    deform_to_ctrl: dict[str, bpy.types.EditBone],
) -> None:
    """Build arm FK control bones and register them in deform_to_ctrl for finger parenting."""
    side = system["side"]
    arm_root = parent_edit_bone

    if system.get("shoulder") and system["shoulder"] in bone_data:
        bone = bone_data[system["shoulder"]]
        shoulder_edit_bone = _new_edit_bone(
            edit_bones,
            f"{CONTROL_PREFIX}Shoulder.{side}",
            bone["head"],
            bone["tail"],
            bone["roll"],
            parent_edit_bone,
            False,
        )
        deform_to_ctrl[system["shoulder"]] = shoulder_edit_bone
        arm_root = shoulder_edit_bone

    upper_arm_bone = bone_data[system["upper_arm"]]
    upper_arm_edit_bone = _new_edit_bone(
        edit_bones,
        f"{CONTROL_PREFIX}UpperArm.{side}",
        upper_arm_bone["head"],
        upper_arm_bone["tail"],
        upper_arm_bone["roll"],
        arm_root,
        False,
    )
    deform_to_ctrl[system["upper_arm"]] = upper_arm_edit_bone

    forearm_bone = bone_data[system["forearm"]]
    forearm_edit_bone = _new_edit_bone(
        edit_bones,
        f"{CONTROL_PREFIX}Forearm.{side}",
        forearm_bone["head"],
        forearm_bone["tail"],
        forearm_bone["roll"],
        upper_arm_edit_bone,
        _connected(forearm_bone["head"], upper_arm_bone["tail"]),
    )
    deform_to_ctrl[system["forearm"]] = forearm_edit_bone

    hand_bone = bone_data[system["hand"]]
    hand_edit_bone = _new_edit_bone(
        edit_bones,
        f"{CONTROL_PREFIX}Hand.{side}",
        hand_bone["head"],
        hand_bone["tail"],
        hand_bone["roll"],
        forearm_edit_bone,
        _connected(hand_bone["head"], forearm_bone["tail"]),
    )
    deform_to_ctrl[system["hand"]] = hand_edit_bone


def _build_leg_system(
    edit_bones: bpy.types.ArmatureEditBones,
    system: SystemDict,
    bone_data: BoneDataDict,
    parent_edit_bone: bpy.types.EditBone,
) -> None:
    """Build leg IK control bones with a reverse-foot roll pivot chain.

    Leg_Target (master), Leg_Pole, and all foot pivots are parented to World.
    The reverse foot pivot chain ends at IK_Target which is the actual leg IK target.
    """
    side = system["side"]
    root_edit_bone = edit_bones.get(f"{CONTROL_PREFIX}World")
    upper_leg_bone = bone_data[system["upper_leg"]]
    lower_leg_bone = bone_data[system["lower_leg"]]
    foot_bone = bone_data[system["foot"]]
    has_toe = system.get("toe") and system["toe"] in bone_data
    toe_bone = bone_data[system["toe"]] if has_toe else None

    foot_len = (foot_bone["tail"] - foot_bone["head"]).length
    ball_pos = toe_bone["head"] if has_toe else foot_bone["tail"]
    pivot_up = mathutils.Vector((0.0, 0.0, max(foot_len * 0.15, 0.05)))

    foot_dir = (foot_bone["tail"] - foot_bone["head"]).normalized()
    foot_dir_horiz = mathutils.Vector((foot_dir.x, foot_dir.y, 0.0))
    if foot_dir_horiz.length > 1e-4:
        foot_dir_horiz = foot_dir_horiz.normalized()
    else:
        foot_dir_horiz = mathutils.Vector((0.0, 1.0, 0.0))
    foot_horiz_tail = foot_bone["head"] - foot_dir_horiz * foot_len
    leg_target_edit_bone = _new_edit_bone(
        edit_bones,
        f"{CONTROL_PREFIX}Leg_Target.{side}",
        foot_bone["head"],
        foot_horiz_tail,
        0.0,
        root_edit_bone,
    )
    ball_edit_bone = _new_edit_bone(
        edit_bones,
        f"{CONTROL_PREFIX}Ball.{side}",
        ball_pos,
        ball_pos + pivot_up,
        0.0,
        leg_target_edit_bone,
    )
    _new_edit_bone(
        edit_bones,
        f"{CONTROL_PREFIX}IK_Target.{side}",
        foot_bone["head"],
        foot_bone["tail"],
        foot_bone["roll"],
        ball_edit_bone,
    )

    if has_toe:
        _new_edit_bone(
            edit_bones,
            f"{CONTROL_PREFIX}Toe.{side}",
            toe_bone["head"],
            toe_bone["tail"],
            toe_bone["roll"],
            leg_target_edit_bone,
            False,
        )

    pole = _calc_pole_pos(
        upper_leg_bone["head"], upper_leg_bone["tail"], lower_leg_bone["tail"]
    )
    _new_edit_bone(
        edit_bones,
        f"{CONTROL_PREFIX}Leg_Pole.{side}",
        pole,
        pole + mathutils.Vector((0.0, 0.05, 0.0)),
        0.0,
        root_edit_bone,
    )


def _build_head_system(
    edit_bones: bpy.types.ArmatureEditBones,
    system: SystemDict,
    bone_data: BoneDataDict,
    parent_edit_bone: bpy.types.EditBone,
) -> None:
    """Build neck and head FK control bones."""
    neck_edit_bone = None
    if system.get("neck") and system["neck"] in bone_data:
        bone = bone_data[system["neck"]]
        neck_edit_bone = _new_edit_bone(
            edit_bones,
            f"{CONTROL_PREFIX}Neck",
            bone["head"],
            bone["tail"],
            bone["roll"],
            parent_edit_bone,
            False,
        )
    if system["head"] in bone_data:
        bone = bone_data[system["head"]]
        _new_edit_bone(
            edit_bones,
            f"{CONTROL_PREFIX}Head",
            bone["head"],
            bone["tail"],
            bone["roll"],
            neck_edit_bone or parent_edit_bone,
            False,
        )


def _build_finger_system(
    edit_bones: bpy.types.ArmatureEditBones,
    system: SystemDict,
    bone_data: BoneDataDict,
    parent_edit_bone: bpy.types.EditBone,
) -> None:
    """Build finger FK control bones with consistent role-based names."""
    prev_edit_bone, prev_bone = parent_edit_bone, None
    for i, bone_name in enumerate(system.get("chain") or []):
        if bone_name not in bone_data:
            continue
        bone = bone_data[bone_name]
        control_edit_bone = _new_edit_bone(
            edit_bones,
            CONTROL_PREFIX + _finger_ctrl_name(system, i),
            bone["head"],
            bone["tail"],
            bone["roll"],
            prev_edit_bone,
            prev_bone is not None and _connected(bone["head"], prev_bone["tail"]),
        )
        prev_edit_bone, prev_bone = control_edit_bone, bone


def build_control_bones(armature_data: bpy.types.Armature, systems: list[SystemDict], bone_data: BoneDataDict) -> None:
    """Build all control bones on the armature from the classified systems."""
    edit_bones = armature_data.edit_bones
    root_edit_bone = _new_edit_bone(
        edit_bones,
        f"{CONTROL_PREFIX}World",
        mathutils.Vector((0.0, 0.0, 0.0)),
        mathutils.Vector((0.0, 0.1, 0.0)),
        0.0,
    )

    hips_edit_bone = None
    chest_edit_bone = root_edit_bone
    deform_to_ctrl = {}

    for system in systems:
        if system["type"] == "spine":
            hips_edit_bone, chest_edit_bone, deform_to_ctrl = _build_spine_system(
                edit_bones, system, bone_data, root_edit_bone
            )
            break

    for system in systems:
        system_type = system["type"]
        if system_type == "arm":
            _build_arm_system(
                edit_bones, system, bone_data, chest_edit_bone, deform_to_ctrl
            )
        elif system_type == "leg":
            parent_edit_bone = (
                hips_edit_bone
                or deform_to_ctrl.get(system.get("parent"))
                or chest_edit_bone
            )
            _build_leg_system(edit_bones, system, bone_data, parent_edit_bone)
        elif system_type == "head":
            _build_head_system(edit_bones, system, bone_data, chest_edit_bone)

    for system in systems:
        if system["type"] == "finger":
            parent_edit_bone = (
                deform_to_ctrl.get(system.get("parent")) or chest_edit_bone
            )
            _build_finger_system(edit_bones, system, bone_data, parent_edit_bone)


def _setup_spine_pose(skeleton: bpy.types.Object, system: SystemDict, shapes: dict[str, bpy.types.Object | None]) -> None:
    """Pelvis, hips, and chest as purple circles."""
    pose_bones = skeleton.pose.bones
    pelvis_hips_shape = shapes.get("pelvis_hips") or shapes["circle"]
    pelvis_name = f"{CONTROL_PREFIX}Pelvis"
    if pelvis_name in pose_bones:
        _assign_shape(pose_bones[pelvis_name], pelvis_hips_shape, True, (2.0, 2.0, 2.0))
        _bone_color(pose_bones[pelvis_name], dracula.PURPLE)
    hips_name = f"{CONTROL_PREFIX}Hips"
    if hips_name in pose_bones:
        _assign_shape(pose_bones[hips_name], pelvis_hips_shape, True, 3.5)
        _bone_color(pose_bones[hips_name], dracula.PURPLE)
    chest_name = f"{CONTROL_PREFIX}Chest"
    if chest_name in pose_bones:
        _assign_shape(pose_bones[chest_name], shapes["circle"], True, 1.6)
        _bone_color(pose_bones[chest_name], dracula.PURPLE)


def _setup_arm_pose(skeleton: bpy.types.Object, system: SystemDict, shapes: dict[str, bpy.types.Object | None]) -> None:
    """Arm FK bones colored by side: left=yellow, right=green."""
    pose_bones = skeleton.pose.bones
    side = system["side"]
    color = _side_color(side)
    shoulder_name = f"{CONTROL_PREFIX}Shoulder.{side}"
    if shoulder_name in pose_bones:
        _assign_shape(pose_bones[shoulder_name], shapes["circle"], True, 1.2)
        _bone_color(pose_bones[shoulder_name], color)
    for name in (f"{CONTROL_PREFIX}UpperArm.{side}", f"{CONTROL_PREFIX}Hand.{side}"):
        if name in pose_bones:
            _assign_shape(pose_bones[name], shapes["circle"], True, 0.4)
            _bone_color(pose_bones[name], color)
    forearm_name = f"{CONTROL_PREFIX}Forearm.{side}"
    if forearm_name in pose_bones:
        _assign_shape(pose_bones[forearm_name], shapes["circle"], True, 0.3)
        _bone_color(pose_bones[forearm_name], color)


def _setup_leg_pose(skeleton: bpy.types.Object, system: SystemDict, shapes: dict[str, bpy.types.Object | None]) -> None:
    """Reverse foot pivot chain, IK leg constraint, knee swivel. Mechanism bones hidden."""
    pose_bones = skeleton.pose.bones
    side = system["side"]
    color = _side_color(side)

    leg_target_name = f"{CONTROL_PREFIX}Leg_Target.{side}"
    if leg_target_name in pose_bones:
        _assign_shape(pose_bones[leg_target_name], shapes["sphere"], False, 0.1)
        _bone_color(pose_bones[leg_target_name], color)
    ball_name = f"{CONTROL_PREFIX}Ball.{side}"
    if ball_name in pose_bones:
        _assign_shape(pose_bones[ball_name], shapes["diamond"], False, 0.03)
        pose_bones[ball_name].custom_shape_translation = (0.0, 0.0, -7.5)
        _bone_color(pose_bones[ball_name], color)
    toe_name = f"{CONTROL_PREFIX}Toe.{side}"
    if toe_name in pose_bones:
        _assign_shape(pose_bones[toe_name], shapes["sphere"], False, 0.06)
        _bone_color(pose_bones[toe_name], color)
    leg_pole_name = f"{CONTROL_PREFIX}Leg_Pole.{side}"
    if leg_pole_name in pose_bones:
        _assign_shape(pose_bones[leg_pole_name], shapes["sphere"], False, 0.04)
        _bone_color(pose_bones[leg_pole_name], color)

    ik_target_name = f"{CONTROL_PREFIX}IK_Target.{side}"
    if ik_target_name in pose_bones:
        pose_bones[ik_target_name].bone.hide = True


def _setup_head_pose(skeleton: bpy.types.Object, shapes: dict[str, bpy.types.Object | None]) -> None:
    """Neck and head as purple circles (central controls), head slightly larger."""
    pose_bones = skeleton.pose.bones
    neck_name = f"{CONTROL_PREFIX}Neck"
    if neck_name in pose_bones:
        _assign_shape(pose_bones[neck_name], shapes["circle"], True, 1.15)
        _bone_color(pose_bones[neck_name], dracula.PURPLE)
    head_name = f"{CONTROL_PREFIX}Head"
    if head_name in pose_bones:
        _assign_shape(pose_bones[head_name], shapes["circle"], True, (0.6, 0.8, 0.8))
        _bone_color(pose_bones[head_name], dracula.PURPLE)


def _setup_finger_pose(skeleton: bpy.types.Object, system: SystemDict, shapes: dict[str, bpy.types.Object | None]) -> None:
    """Finger FK bones colored by side: left=yellow, right=green."""
    pose_bones = skeleton.pose.bones
    color = _side_color(system["side"])
    for i in range(len(system.get("chain") or [])):
        control_name = CONTROL_PREFIX + _finger_ctrl_name(system, i)
        if control_name in pose_bones:
            _assign_shape(
                pose_bones[control_name], shapes["circle"], True, 0.5 if i == 0 else 0.3
            )
            _bone_color(pose_bones[control_name], color)


def setup_control_rig_pose(skeleton: bpy.types.Object, systems: list[SystemDict], shapes: dict[str, bpy.types.Object | None]) -> None:
    """Apply custom shapes, colors, and constraints to all control bones."""
    skeleton.data.pose_position = "POSE"
    pose_bones = skeleton.pose.bones
    world_name = f"{CONTROL_PREFIX}World"
    if world_name in pose_bones:
        _assign_shape(
            pose_bones[world_name],
            shapes.get("master") or shapes["square"],
            False,
            0.5,
        )
        pose_bones[world_name].custom_shape_rotation_euler = (math.pi / 2, 0.0, 0.0)
        _bone_color(pose_bones[world_name], dracula.PURPLE)
    for system in systems:
        system_type = system["type"]
        if system_type == "spine":
            _setup_spine_pose(skeleton, system, shapes)
        elif system_type == "arm":
            _setup_arm_pose(skeleton, system, shapes)
        elif system_type == "leg":
            _setup_leg_pose(skeleton, system, shapes)
        elif system_type == "head":
            _setup_head_pose(skeleton, shapes)
        elif system_type == "finger":
            _setup_finger_pose(skeleton, system, shapes)


def setup_spine_splineik(
    skeleton: bpy.types.Object,
    systems: list[SystemDict],
    context: bpy.types.Context,
    bone_data: BoneDataDict,
    container: bpy.types.Object | None = None,
) -> None:
    """Create the Spline IK curve for the spine, hooked to CR_Hips and CR_Chest.

    The curve is parented to container (or skeleton if None). The Spline IK
    constraint itself is added on the deform skeleton side in wire_deform_constraints.
    Should be called after setup_control_rig_pose while skeleton is in POSE mode.
    Returns with skeleton in POSE mode.
    """
    spine_sys = next((s for s in systems if s["type"] == "spine"), None)
    if spine_sys is None:
        return

    chain = spine_sys.get("vertebrae") or []
    if not chain or chain[0] not in bone_data or chain[-1] not in bone_data:
        return

    matrix_world = skeleton.matrix_world
    start_pos = matrix_world @ bone_data[chain[0]]["head"]
    end_pos = matrix_world @ bone_data[chain[-1]]["tail"]

    curve_name = f"{CONTROL_PREFIX}Spine_Curve"
    old = bpy.data.objects.get(curve_name)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)

    curve_data = bpy.data.curves.new(curve_name, "CURVE")
    curve_data.dimensions = "3D"
    curve_data.resolution_u = 12
    spline = curve_data.splines.new("BEZIER")
    spline.bezier_points.add(1)

    spine_dir = (end_pos - start_pos).normalized()
    spine_len = (end_pos - start_pos).length

    start_point = spline.bezier_points[0]
    start_point.co = start_pos
    start_point.handle_left_type = "FREE"
    start_point.handle_right_type = "FREE"
    start_point.handle_left = start_pos - spine_dir * spine_len / 3
    start_point.handle_right = start_pos + spine_dir * spine_len / 3

    end_point = spline.bezier_points[1]
    end_point.co = end_pos
    end_point.handle_left_type = "FREE"
    end_point.handle_right_type = "FREE"
    end_point.handle_left = end_pos - spine_dir * spine_len / 3
    end_point.handle_right = end_pos + spine_dir * spine_len / 3

    parent = container or skeleton
    curve_obj = bpy.data.objects.new(curve_name, curve_data)
    for col in parent.users_collection:
        col.objects.link(curve_obj)
    curve_obj.parent = parent
    curve_obj.hide_render = True

    hook_hips = curve_obj.modifiers.new("Hook_Hips", "HOOK")
    hook_hips.object = skeleton
    hook_hips.subtarget = f"{CONTROL_PREFIX}Hips"

    hook_chest = curve_obj.modifiers.new("Hook_Chest", "HOOK")
    hook_chest.object = skeleton
    hook_chest.subtarget = f"{CONTROL_PREFIX}Chest"

    bpy.ops.object.mode_set(mode="OBJECT")
    context.view_layer.objects.active = curve_obj
    bpy.ops.object.mode_set(mode="EDIT")

    bezier_points = curve_obj.data.splines[0].bezier_points
    last_index = len(bezier_points) - 1
    for i, bezier_point in enumerate(bezier_points):
        bezier_point.select_control_point = i == 0
        bezier_point.select_left_handle = i == 0
        bezier_point.select_right_handle = i == 0
    bpy.ops.object.hook_assign(modifier="Hook_Hips")

    for i, bezier_point in enumerate(bezier_points):
        bezier_point.select_control_point = i == last_index
        bezier_point.select_left_handle = i == last_index
        bezier_point.select_right_handle = i == last_index
    bpy.ops.object.hook_assign(modifier="Hook_Chest")

    bpy.ops.object.mode_set(mode="OBJECT")
    curve_obj.hide_viewport = True
    context.view_layer.objects.active = skeleton
    bpy.ops.object.mode_set(mode="POSE")


def _add_copy_transforms(skeleton: bpy.types.Object, deform_bone: str, control_bone: str) -> str:
    pose_bone = skeleton.pose.bones.get(deform_bone)
    if pose_bone is None:
        return f"SKIP {deform_bone}: not found on skeleton"
    control_bone_name = CONTROL_PREFIX + control_bone
    if control_bone_name not in skeleton.pose.bones:
        return f"SKIP {deform_bone}: control bone '{control_bone_name}' not found"
    constraint = pose_bone.constraints.new("COPY_TRANSFORMS")
    constraint.name = "CR"
    constraint.target = skeleton
    constraint.subtarget = control_bone_name
    constraint.target_space, constraint.owner_space = "WORLD", "WORLD"
    return f"OK {deform_bone} → {control_bone_name}"


def wire_deform_constraints(skeleton: bpy.types.Object, systems: list[SystemDict]) -> list[str]:
    """Add Copy Transforms constraints on the skeleton wired to each control bone."""
    skeleton.data.pose_position = "POSE"
    log = []
    for system in systems:
        system_type = system["type"]
        if system_type == "spine":
            if system.get("pelvis"):
                log.append(_add_copy_transforms(skeleton, system["pelvis"], "Hips"))
            vertebrae = system.get("vertebrae") or []
            if vertebrae:
                curve_name = f"{CONTROL_PREFIX}Spine_Curve"
                curve_obj = bpy.data.objects.get(curve_name)
                last_pose_bone = skeleton.pose.bones.get(vertebrae[-1])
                if curve_obj and last_pose_bone:
                    constraint = last_pose_bone.constraints.new("SPLINE_IK")
                    constraint.name = "CR"
                    constraint.target = curve_obj
                    constraint.chain_count = len(vertebrae)
                    constraint.use_chain_offset = False
                    constraint.use_even_divisions = False
                    constraint.use_curve_radius = False
                    constraint.y_scale_mode = "FIT_CURVE"
                    constraint.xz_scale_mode = "NONE"
                    log.append(
                        f"OK SplineIK on {vertebrae[-1]} (chain={len(vertebrae)})"
                    )
                else:
                    log.append("SKIP SplineIK: curve or bone not found")
        elif system_type == "arm":
            side = system["side"]
            if system.get("shoulder"):
                log.append(
                    _add_copy_transforms(
                        skeleton, system["shoulder"], f"Shoulder.{side}"
                    )
                )
            for deform_key, control_bone in (
                ("upper_arm", f"UpperArm.{side}"),
                ("forearm", f"Forearm.{side}"),
                ("hand", f"Hand.{side}"),
            ):
                if system.get(deform_key):
                    log.append(
                        _add_copy_transforms(skeleton, system[deform_key], control_bone)
                    )
        elif system_type == "leg":
            side = system["side"]
            lower_leg_pose_bone = skeleton.pose.bones.get(system.get("lower_leg", ""))
            if lower_leg_pose_bone:
                ik_chain = [k for k in ("upper_leg", "lower_leg") if system.get(k)]
                constraint = lower_leg_pose_bone.constraints.new("IK")
                constraint.name = "CR"
                constraint.target = skeleton
                constraint.subtarget = f"{CONTROL_PREFIX}IK_Target.{side}"
                constraint.pole_target = skeleton
                constraint.pole_subtarget = f"{CONTROL_PREFIX}Leg_Pole.{side}"
                constraint.chain_count = len(ik_chain)
                constraint.use_stretch = False
                constraint.pole_angle = -math.pi / 2
                log.append(
                    f"OK IK on {system['lower_leg']} (chain={len(ik_chain)}) → {CONTROL_PREFIX}IK_Target.{side}"
                )
            for deform_key, control_bone in (
                ("foot", f"IK_Target.{side}"),
                ("toe", f"Toe.{side}"),
            ):
                if system.get(deform_key):
                    log.append(
                        _add_copy_transforms(skeleton, system[deform_key], control_bone)
                    )
        elif system_type == "head":
            if system.get("neck"):
                log.append(_add_copy_transforms(skeleton, system["neck"], "Neck"))
            log.append(_add_copy_transforms(skeleton, system["head"], "Head"))
        elif system_type == "finger":
            for i, bone_name in enumerate(system.get("chain") or []):
                log.append(
                    _add_copy_transforms(
                        skeleton, bone_name, _finger_ctrl_name(system, i)
                    )
                )
    return log


def remove_control_rig_bones(skeleton: bpy.types.Object) -> None:
    """Remove all CR_ control bones and any constraints targeting them from the skeleton.

    Should be called in POSE mode. Internally switches to EDIT mode to delete bones,
    then returns to OBJECT mode.
    """
    control_bone_names = {
        b.name for b in skeleton.data.bones if b.name.startswith(CONTROL_PREFIX)
    }
    if not control_bone_names:
        return
    for pose_bone in skeleton.pose.bones:
        for constraint in list(pose_bone.constraints):
            if getattr(constraint, "subtarget", None) in control_bone_names:
                pose_bone.constraints.remove(constraint)
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = skeleton.data.edit_bones
    for name in list(control_bone_names):
        if name in edit_bones:
            edit_bones.remove(edit_bones[name])
    bpy.ops.object.mode_set(mode="OBJECT")
