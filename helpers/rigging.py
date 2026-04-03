import bmesh
import bpy
import json
import math
import mathutils
import urllib.error
from pathlib import Path

from . import dracula
from . import ollama

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(filename):
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


def classify_bones(bone_names):
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
            for s in systems:
                label = f"{s['type']}.{s.get('side', s.get('name', '-'))}"
                if s["type"] == "leg":
                    label += f"(toe={'yes' if s.get('toe') else 'NO'})"
                summary.append(label)
            return systems, f"Identified: {summary}", raw
        return None, f"Could not parse systems from Ollama response: {raw[:300]}", raw
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        return None, f"Ollama HTTP {exc.code}: {body[:200]}", ""
    except Exception as exc:
        return None, f"Ollama error: {exc}", ""


def _parse_systems(data, bone_names):
    """Parse the systems array from Ollama JSON into validated dicts with resolved bone names."""
    lookup = {n.strip().lower(): n for n in bone_names}

    def resolve(v):
        return lookup.get(v.strip().lower()) if isinstance(v, str) else None

    def resolve_chain(lst):
        if not isinstance(lst, list):
            return []
        return [r for r in (resolve(n) for n in lst if isinstance(n, str)) if r]

    systems = []
    for entry in (data.get("systems") or []):
        if not isinstance(entry, dict):
            continue
        t = entry.get("type")

        if t == "spine":
            vertebrae = resolve_chain(entry.get("vertebrae"))
            pelvis = resolve(entry.get("pelvis"))
            if vertebrae or pelvis:
                systems.append({
                    "type": "spine",
                    "pelvis": pelvis,
                    "vertebrae": vertebrae,
                })

        elif t == "arm":
            upper_arm = resolve(entry.get("upper_arm"))
            forearm = resolve(entry.get("forearm"))
            hand = resolve(entry.get("hand"))
            if not all([upper_arm, forearm, hand]):
                continue
            systems.append({
                "type": "arm",
                "side": str(entry.get("side") or "L"),
                "parent": entry.get("parent"),
                "shoulder": resolve(entry.get("shoulder")),
                "upper_arm": upper_arm,
                "forearm": forearm,
                "hand": hand,
            })

        elif t == "leg":
            upper_leg = resolve(entry.get("upper_leg"))
            lower_leg = resolve(entry.get("lower_leg"))
            foot = resolve(entry.get("foot"))
            if not all([upper_leg, lower_leg, foot]):
                continue
            systems.append({
                "type": "leg",
                "side": str(entry.get("side") or "L"),
                "parent": entry.get("parent"),
                "upper_leg": upper_leg,
                "lower_leg": lower_leg,
                "foot": foot,
                "toe": resolve(entry.get("toe")),
            })

        elif t == "head":
            head = resolve(entry.get("head"))
            if not head:
                continue
            systems.append({
                "type": "head",
                "parent": entry.get("parent"),
                "neck": resolve(entry.get("neck")),
                "head": head,
            })

        elif t == "finger":
            chain = resolve_chain(entry.get("chain"))
            name = entry.get("name")
            if not chain or not name:
                continue
            systems.append({
                "type": "finger",
                "name": str(name).lower(),
                "side": str(entry.get("side") or "L"),
                "parent": entry.get("parent"),
                "chain": chain,
            })

    return systems or None


def extract_bone_names(systems):
    """Return the flat set of all deform bone names referenced by systems."""
    names = set()
    for s in systems:
        t = s["type"]
        if t == "spine":
            if s.get("pelvis"):
                names.add(s["pelvis"])
            names.update(s.get("vertebrae") or [])
        elif t == "arm":
            for key in ("shoulder", "upper_arm", "forearm", "hand"):
                if s.get(key):
                    names.add(s[key])
        elif t == "leg":
            for key in ("upper_leg", "lower_leg", "foot", "toe"):
                if s.get(key):
                    names.add(s[key])
        elif t == "head":
            for key in ("neck", "head"):
                if s.get(key):
                    names.add(s[key])
        elif t == "finger":
            names.update(s.get("chain") or [])
    return names


def _shapes_collection():
    col = bpy.data.collections.get("_Shapes")
    if col is None:
        col = bpy.data.collections.new("_Shapes")
        bpy.context.scene.collection.children.link(col)
    col.hide_viewport = True
    col.hide_render = True
    return col


def get_or_create_shape(name, create_fn):
    """Return or create a mesh object to use as a custom bone shape.

    Any existing object of a different type (e.g. a stale Grease Pencil object
    from a previous build) is removed and recreated as a mesh.
    """
    obj = bpy.data.objects.get(name)
    if obj is not None:
        if obj.type == "MESH":
            return obj
        bpy.data.objects.remove(obj, do_unlink=True)
    obj = create_fn(name)
    _shapes_collection().objects.link(obj)
    return obj


def _wire_shape(name, strokes):
    """Create a mesh bone-shape object built from wire edges.

    strokes: list of (points_list, cyclic) tuples where points_list is a
             sequence of (x, y, z) tuples and cyclic closes the loop.
    """
    bm = bmesh.new()
    for pts, cyclic in strokes:
        verts = [bm.verts.new(co) for co in pts]
        for i in range(len(verts) - 1):
            bm.edges.new((verts[i], verts[i + 1]))
        if cyclic and len(verts) > 1:
            bm.edges.new((verts[-1], verts[0]))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return bpy.data.objects.new(name, mesh)


def create_circle_shape(name):
    n = 16
    pts = [(math.cos(2 * math.pi * i / n), 0.0, math.sin(2 * math.pi * i / n)) for i in range(n)]
    return _wire_shape(name, [(pts, True)])


def create_box_shape(name):
    s = 0.5
    co = [
        (-s, -s, -s), (s, -s, -s), (s, s, -s), (-s, s, -s),
        (-s, -s, s), (s, -s, s), (s, s, s), (-s, s, s),
    ]
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    return _wire_shape(name, [([co[a], co[b]], False) for a, b in edges])


def create_diamond_shape(name):
    s = 0.5
    co = [(0, s, 0), (s, 0, 0), (0, -s, 0), (-s, 0, 0), (0, 0, s), (0, 0, -s)]
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (0, 4), (4, 2), (2, 5), (5, 0), (1, 4), (1, 5), (3, 4), (3, 5)]
    return _wire_shape(name, [([co[a], co[b]], False) for a, b in edges])


def create_sphere_shape(name):
    """Unit sphere approximated by three orthogonal circles."""
    n = 16
    xy = [(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n), 0.0) for i in range(n)]
    xz = [(math.cos(2 * math.pi * i / n), 0.0, math.sin(2 * math.pi * i / n)) for i in range(n)]
    yz = [(0.0, math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)) for i in range(n)]
    return _wire_shape(name, [(xy, True), (xz, True), (yz, True)])


def create_square_shape(name):
    """Unit square with crosshairs in the XZ plane."""
    pts = [(-1, 0, 1), (1, 0, 1), (1, 0, -1), (-1, 0, -1)]
    return _wire_shape(name, [
        (pts, True),
        ([(-1, 0, 0), (1, 0, 0)], False),
        ([(0, 0, -1), (0, 0, 1)], False),
    ])



def _calc_pole_angle(upper_pb, lower_pb, pole_pos):
    """Calculate the IK pole_angle that keeps the leg in its rest pose.

    Projects both the bone's Z axis (roll direction) and the direction to the pole
    onto the plane perpendicular to the full chain axis, then returns the signed
    angle between them. Setting this on the IK constraint compensates for Blender's
    default pole orientation so the leg does not move from rest when the rig is built.
    """
    chain = (lower_pb.bone.tail_local - upper_pb.bone.head_local).normalized()

    to_pole = pole_pos - upper_pb.bone.head_local
    to_pole -= to_pole.dot(chain) * chain
    if to_pole.length < 1e-4:
        return 0.0
    to_pole = to_pole.normalized()

    bone_z = upper_pb.bone.z_axis.copy()
    bone_z -= bone_z.dot(chain) * chain
    if bone_z.length < 1e-4:
        return 0.0
    bone_z = bone_z.normalized()

    angle = math.acos(max(-1.0, min(1.0, bone_z.dot(to_pole))))
    if bone_z.cross(to_pole).dot(chain) < 0:
        angle = -angle
    return angle


def _calc_pole_pos(upper_head, upper_tail, lower_tail):
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


def _eb(ebs, name, head, tail, roll, parent=None, connect=False):
    b = ebs.new(name)
    b.head, b.tail, b.roll, b.use_deform = head, tail, roll, False
    if parent:
        b.parent = parent
        b.use_connect = connect
    return b


def _connected(head, parent_tail):
    return (head - parent_tail).length < 1e-4


def _side_color(side):
    """Return the bone color for a given side: left=yellow, right=green, center=purple."""
    if side == "L":
        return dracula.YELLOW
    if side == "R":
        return dracula.GREEN
    return dracula.PURPLE


def _bone_color(pb, color):
    pb.color.palette = "CUSTOM"
    pb.color.custom.normal = color
    pb.color.custom.select = tuple(min(1.0, c + 0.2) for c in color)
    pb.color.custom.active = (1.0, 1.0, 1.0)


def _assign_shape(pb, shape, use_bone_size=True, scale=1.0):
    """Assign a custom shape to a pose bone.

    scale can be a float for uniform scaling or a (x, y, z) tuple for per-axis scaling.
    """
    pb.custom_shape = shape
    pb.use_custom_shape_bone_size = use_bone_size
    if isinstance(scale, (int, float)):
        pb.custom_shape_scale_xyz = (scale, scale, scale)
    else:
        pb.custom_shape_scale_xyz = scale
    pb.custom_shape_wire_width = 3.0


def _finger_ctrl_name(system, index):
    """Return the consistent control bone name for a finger bone at a given index."""
    return f"FK_{system['name'].capitalize()}.{index + 1:03d}.{system['side']}"


def _build_spine_system(ebs, system, bd, root_eb):
    """Build spine FK control bones.

    Creates FK_Pelvis and FK_Hips at the base and a free FK_Chest at the top.
    The deform vertebrae are driven by a Spline IK constraint added directly on the
    skeleton side in wire_deform_constraints — no mechanism bones are needed here.
    Returns (hips_eb, chest_eb, deform_to_ctrl).
    """
    deform_to_ctrl = {}
    pelvis_eb = None
    hips_eb = None

    if system.get("pelvis") and system["pelvis"] in bd:
        d = bd[system["pelvis"]]
        bone_len = (d["tail"] - d["head"]).length
        pelvis_eb = _eb(ebs, "FK_Pelvis", d["head"], d["tail"], d["roll"], root_eb, False)
        direction = (d["tail"] - d["head"]).normalized()
        hips_tail = d["head"] + direction * max(bone_len * 0.5, 0.05)
        hips_eb = _eb(ebs, "FK_Hips", d["head"], hips_tail, d["roll"], pelvis_eb, False)
        deform_to_ctrl[system["pelvis"]] = pelvis_eb

    chain = [n for n in (system.get("vertebrae") or []) if n in bd]
    chest_eb = hips_eb or pelvis_eb or root_eb

    if chain:
        last_d = bd[chain[-1]]
        chest_eb = _eb(ebs, "FK_Chest", last_d["head"], last_d["tail"], last_d["roll"], pelvis_eb or root_eb, False)

    return hips_eb, chest_eb, deform_to_ctrl


def _build_arm_system(ebs, system, bd, parent_eb, deform_to_ctrl):
    """Build arm FK control bones and register them in deform_to_ctrl for finger parenting."""
    s = system["side"]
    arm_root = parent_eb

    if system.get("shoulder") and system["shoulder"] in bd:
        d = bd[system["shoulder"]]
        sh_eb = _eb(ebs, f"FK_Shoulder.{s}", d["head"], d["tail"], d["roll"], parent_eb, False)
        deform_to_ctrl[system["shoulder"]] = sh_eb
        arm_root = sh_eb

    u_data = bd[system["upper_arm"]]
    upper_eb = _eb(ebs, f"FK_UpperArm.{s}", u_data["head"], u_data["tail"], u_data["roll"], arm_root, False)
    deform_to_ctrl[system["upper_arm"]] = upper_eb

    f_data = bd[system["forearm"]]
    forearm_eb = _eb(ebs, f"FK_Forearm.{s}", f_data["head"], f_data["tail"], f_data["roll"], upper_eb,
                     _connected(f_data["head"], u_data["tail"]))
    deform_to_ctrl[system["forearm"]] = forearm_eb

    h_data = bd[system["hand"]]
    hand_eb = _eb(ebs, f"FK_Hand.{s}", h_data["head"], h_data["tail"], h_data["roll"], forearm_eb,
                  _connected(h_data["head"], f_data["tail"]))
    deform_to_ctrl[system["hand"]] = hand_eb


def _build_leg_system(ebs, system, bd, parent_eb):
    """Build leg IK control bones with a reverse-foot roll pivot chain.

    IK_Foot (master), Pole_Knee, and all foot pivots are parented to FK_Root.
    The reverse foot pivot chain ends at IK_Ankle which is the actual leg IK target.
    """
    s = system["side"]
    root_eb = ebs.get("FK_Root")
    u_data = bd[system["upper_leg"]]
    l_data = bd[system["lower_leg"]]
    f_data = bd[system["foot"]]
    has_toe = system.get("toe") and system["toe"] in bd
    t_data = bd[system["toe"]] if has_toe else None

    ik_u = _eb(ebs, f"IK_UpperLeg.{s}", u_data["head"], u_data["tail"], u_data["roll"], parent_eb, False)
    _eb(ebs, f"IK_LowerLeg.{s}", l_data["head"], l_data["tail"], l_data["roll"], ik_u,
        _connected(l_data["head"], u_data["tail"]))

    foot_len = (f_data["tail"] - f_data["head"]).length
    ball_pos = t_data["head"] if has_toe else f_data["tail"]
    pivot_up = mathutils.Vector((0.0, 0.0, max(foot_len * 0.15, 0.05)))

    foot_dir = (f_data["tail"] - f_data["head"]).normalized()
    foot_dir_horiz = mathutils.Vector((foot_dir.x, foot_dir.y, 0.0))
    if foot_dir_horiz.length > 1e-4:
        foot_dir_horiz = foot_dir_horiz.normalized()
    else:
        foot_dir_horiz = mathutils.Vector((0.0, 1.0, 0.0))
    foot_horiz_tail = f_data["head"] + foot_dir_horiz * foot_len
    foot_eb = _eb(ebs, f"IK_Foot.{s}", f_data["head"], foot_horiz_tail, 0.0, root_eb)
    ball_eb = _eb(ebs, f"Pivot_Ball.{s}", ball_pos, ball_pos + pivot_up, 0.0, foot_eb)
    ankle_eb = _eb(ebs, f"IK_Ankle.{s}", f_data["head"], f_data["tail"], f_data["roll"], ball_eb)

    if has_toe:
        _eb(ebs, f"FK_Toe.{s}", t_data["head"], t_data["tail"], t_data["roll"], foot_eb,
            False)

    pole = _calc_pole_pos(u_data["head"], u_data["tail"], l_data["tail"])
    _eb(ebs, f"Pole_Knee.{s}", pole, pole + mathutils.Vector((0.0, 0.05, 0.0)), 0.0, root_eb)


def _build_head_system(ebs, system, bd, parent_eb):
    """Build neck and head FK control bones."""
    neck_eb = None
    if system.get("neck") and system["neck"] in bd:
        d = bd[system["neck"]]
        neck_eb = _eb(ebs, "FK_Neck", d["head"], d["tail"], d["roll"], parent_eb, False)
    if system["head"] in bd:
        d = bd[system["head"]]
        _eb(ebs, "FK_Head", d["head"], d["tail"], d["roll"], neck_eb or parent_eb, False)


def _build_finger_system(ebs, system, bd, parent_eb):
    """Build finger FK control bones with consistent role-based names."""
    prev, prev_data = parent_eb, None
    for i, bone_name in enumerate(system.get("chain") or []):
        if bone_name not in bd:
            continue
        d = bd[bone_name]
        ctrl_eb = _eb(ebs, _finger_ctrl_name(system, i), d["head"], d["tail"], d["roll"], prev,
                      prev_data is not None and _connected(d["head"], prev_data["tail"]))
        prev, prev_data = ctrl_eb, d


def build_control_bones(cr_arm_data, systems, bone_data):
    """Build all control bones on the CR armature from the classified systems."""
    ebs = cr_arm_data.edit_bones
    root_eb = _eb(ebs, "FK_Root", mathutils.Vector((0.0, 0.0, 0.0)),
                  mathutils.Vector((0.0, 0.1, 0.0)), 0.0)

    hips_eb = None
    chest_eb = root_eb
    deform_to_ctrl = {}

    for s in systems:
        if s["type"] == "spine":
            hips_eb, chest_eb, deform_to_ctrl = _build_spine_system(ebs, s, bone_data, root_eb)
            break

    for s in systems:
        t = s["type"]
        if t == "arm":
            _build_arm_system(ebs, s, bone_data, chest_eb, deform_to_ctrl)
        elif t == "leg":
            parent_eb = hips_eb or deform_to_ctrl.get(s.get("parent")) or chest_eb
            _build_leg_system(ebs, s, bone_data, parent_eb)
        elif t == "head":
            _build_head_system(ebs, s, bone_data, chest_eb)

    for s in systems:
        if s["type"] == "finger":
            parent_eb = deform_to_ctrl.get(s.get("parent")) or chest_eb
            _build_finger_system(ebs, s, bone_data, parent_eb)


def _setup_spine_pose(cr_obj, system, shapes):
    """Pelvis, hips, and chest as purple circles."""
    pbs = cr_obj.pose.bones
    if "FK_Pelvis" in pbs:
        _assign_shape(pbs["FK_Pelvis"], shapes["circle"], True, (2.0, 2.0, 2.0))
        _bone_color(pbs["FK_Pelvis"], dracula.PURPLE)
    if "FK_Hips" in pbs:
        _assign_shape(pbs["FK_Hips"], shapes["circle"], True, 3.5)
        _bone_color(pbs["FK_Hips"], dracula.PURPLE)
    if "FK_Chest" in pbs:
        _assign_shape(pbs["FK_Chest"], shapes["circle"], True, 1.6)
        _bone_color(pbs["FK_Chest"], dracula.PURPLE)


def _setup_arm_pose(cr_obj, system, shapes):
    """Arm FK bones colored by side: left=yellow, right=green."""
    pbs, s = cr_obj.pose.bones, system["side"]
    color = _side_color(s)
    if f"FK_Shoulder.{s}" in pbs:
        _assign_shape(pbs[f"FK_Shoulder.{s}"], shapes["circle"], True, 1.2)
        _bone_color(pbs[f"FK_Shoulder.{s}"], color)
    for name in (f"FK_UpperArm.{s}", f"FK_Hand.{s}"):
        if name in pbs:
            _assign_shape(pbs[name], shapes["circle"], True, 0.4)
            _bone_color(pbs[name], color)
    if f"FK_Forearm.{s}" in pbs:
        _assign_shape(pbs[f"FK_Forearm.{s}"], shapes["circle"], True, 0.3)
        _bone_color(pbs[f"FK_Forearm.{s}"], color)


def _setup_leg_pose(cr_obj, system, shapes):
    """Reverse foot pivot chain, IK leg constraint, knee swivel. Mechanism bones hidden."""
    pbs, s = cr_obj.pose.bones, system["side"]
    color = _side_color(s)

    if f"IK_Foot.{s}" in pbs:
        _assign_shape(pbs[f"IK_Foot.{s}"], shapes["sphere"], False, 10.0)
        _bone_color(pbs[f"IK_Foot.{s}"], color)
    if f"Pivot_Ball.{s}" in pbs:
        _assign_shape(pbs[f"Pivot_Ball.{s}"], shapes["diamond"], False, 3.0)
        pbs[f"Pivot_Ball.{s}"].custom_shape_translation = (0.0, 0.0, -7.5)
        _bone_color(pbs[f"Pivot_Ball.{s}"], color)
    if f"FK_Toe.{s}" in pbs:
        _assign_shape(pbs[f"FK_Toe.{s}"], shapes["sphere"], False, 6.0)
        _bone_color(pbs[f"FK_Toe.{s}"], color)
    if f"Pole_Knee.{s}" in pbs:
        _assign_shape(pbs[f"Pole_Knee.{s}"], shapes["sphere"], False, 4.0)
        _bone_color(pbs[f"Pole_Knee.{s}"], color)

    if f"IK_LowerLeg.{s}" in pbs:
        upper_pb = pbs.get(f"IK_UpperLeg.{s}")
        lower_pb = pbs[f"IK_LowerLeg.{s}"]
        pole_pb = pbs.get(f"Pole_Knee.{s}")
        c = lower_pb.constraints.new("IK")
        c.target, c.subtarget = cr_obj, f"IK_Ankle.{s}"
        c.pole_target, c.pole_subtarget = cr_obj, f"Pole_Knee.{s}"
        c.chain_count, c.use_stretch = 2, False
        if upper_pb and pole_pb:
            c.pole_angle = _calc_pole_angle(upper_pb, lower_pb, pole_pb.bone.head_local)

    for name in (f"IK_UpperLeg.{s}", f"IK_LowerLeg.{s}", f"IK_Ankle.{s}"):
        if name in pbs:
            pbs[name].bone.hide = True


def _setup_head_pose(cr_obj, shapes):
    """Neck and head as purple circles (central controls), head slightly larger."""
    pbs = cr_obj.pose.bones
    if "FK_Neck" in pbs:
        _assign_shape(pbs["FK_Neck"], shapes["circle"], True, 1.15)
        _bone_color(pbs["FK_Neck"], dracula.PURPLE)
    if "FK_Head" in pbs:
        _assign_shape(pbs["FK_Head"], shapes["circle"], True, (0.6, 0.8, 0.8))
        _bone_color(pbs["FK_Head"], dracula.PURPLE)


def _setup_finger_pose(cr_obj, system, shapes):
    """Finger FK bones colored by side: left=yellow, right=green."""
    pbs = cr_obj.pose.bones
    color = _side_color(system["side"])
    for i in range(len(system.get("chain") or [])):
        ctrl = _finger_ctrl_name(system, i)
        if ctrl in pbs:
            _assign_shape(pbs[ctrl], shapes["circle"], True, 0.5 if i == 0 else 0.3)
            _bone_color(pbs[ctrl], color)


def setup_control_rig_pose(cr_obj, systems, shapes):
    """Apply custom shapes, colors, and constraints to all control bones."""
    cr_obj.data.pose_position = "POSE"
    pbs = cr_obj.pose.bones
    if "FK_Root" in pbs:
        _assign_shape(pbs["FK_Root"], shapes["square"], False, 50.0)
        _bone_color(pbs["FK_Root"], dracula.PURPLE)
    for s in systems:
        t = s["type"]
        if t == "spine":
            _setup_spine_pose(cr_obj, s, shapes)
        elif t == "arm":
            _setup_arm_pose(cr_obj, s, shapes)
        elif t == "leg":
            _setup_leg_pose(cr_obj, s, shapes)
        elif t == "head":
            _setup_head_pose(cr_obj, shapes)
        elif t == "finger":
            _setup_finger_pose(cr_obj, s, shapes)


def setup_spine_splineik(cr_obj, systems, context, bone_data):
    """Create the Spline IK curve for the spine, hooked to FK_Hips and FK_Chest.

    The Spline IK constraint itself is added on the deform skeleton side in
    wire_deform_constraints. Should be called after setup_control_rig_pose while
    cr_obj is in POSE mode. Returns with cr_obj in POSE mode.
    """
    spine_sys = next((s for s in systems if s["type"] == "spine"), None)
    if spine_sys is None:
        return

    chain = spine_sys.get("vertebrae") or []
    if not chain or chain[0] not in bone_data or chain[-1] not in bone_data:
        return

    mw = cr_obj.matrix_world
    start_pos = mw @ bone_data[chain[0]]["head"]
    end_pos = mw @ bone_data[chain[-1]]["tail"]

    curve_name = cr_obj.name + "_SpineCurve"
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

    p0 = spline.bezier_points[0]
    p0.co = start_pos
    p0.handle_left_type = "FREE"
    p0.handle_right_type = "FREE"
    p0.handle_left = start_pos - spine_dir * spine_len / 3
    p0.handle_right = start_pos + spine_dir * spine_len / 3

    p1 = spline.bezier_points[1]
    p1.co = end_pos
    p1.handle_left_type = "FREE"
    p1.handle_right_type = "FREE"
    p1.handle_left = end_pos - spine_dir * spine_len / 3
    p1.handle_right = end_pos + spine_dir * spine_len / 3

    curve_obj = bpy.data.objects.new(curve_name, curve_data)
    for col in cr_obj.users_collection:
        col.objects.link(curve_obj)
    curve_obj.hide_render = True

    hook_hips = curve_obj.modifiers.new("Hook_Hips", "HOOK")
    hook_hips.object = cr_obj
    hook_hips.subtarget = "FK_Hips"

    hook_chest = curve_obj.modifiers.new("Hook_Chest", "HOOK")
    hook_chest.object = cr_obj
    hook_chest.subtarget = "FK_Chest"

    bpy.ops.object.mode_set(mode="OBJECT")
    context.view_layer.objects.active = curve_obj
    bpy.ops.object.mode_set(mode="EDIT")

    pts = curve_obj.data.splines[0].bezier_points
    last_i = len(pts) - 1
    for i, bp in enumerate(pts):
        bp.select_control_point = (i == 0)
        bp.select_left_handle = (i == 0)
        bp.select_right_handle = (i == 0)
    bpy.ops.object.hook_assign(modifier="Hook_Hips")

    for i, bp in enumerate(pts):
        bp.select_control_point = (i == last_i)
        bp.select_left_handle = (i == last_i)
        bp.select_right_handle = (i == last_i)
    bpy.ops.object.hook_assign(modifier="Hook_Chest")

    bpy.ops.object.mode_set(mode="OBJECT")
    context.view_layer.objects.active = cr_obj
    bpy.ops.object.mode_set(mode="POSE")


def _add_copy_transforms(skel_obj, cr_obj, def_bone, ctrl_bone):
    pb = skel_obj.pose.bones.get(def_bone)
    if pb is None:
        return f"SKIP {def_bone}: not found on skeleton"
    if ctrl_bone not in cr_obj.pose.bones:
        return f"SKIP {def_bone}: ctrl '{ctrl_bone}' not on CR"
    c = pb.constraints.new("COPY_TRANSFORMS")
    c.name = "CR"
    c.target, c.subtarget = cr_obj, ctrl_bone
    c.target_space, c.owner_space = "WORLD", "WORLD"
    return f"OK {def_bone} → {ctrl_bone}"


def wire_deform_constraints(skel_obj, cr_obj, systems):
    """Add Copy Transforms constraints on the skeleton wired to each CR control bone."""
    skel_obj.data.pose_position = "POSE"
    log = []
    for s in systems:
        t = s["type"]
        if t == "spine":
            if s.get("pelvis"):
                log.append(_add_copy_transforms(skel_obj, cr_obj, s["pelvis"], "FK_Hips"))
            vertebrae = s.get("vertebrae") or []
            if vertebrae:
                curve_name = cr_obj.name + "_SpineCurve"
                curve_obj = bpy.data.objects.get(curve_name)
                last_pb = skel_obj.pose.bones.get(vertebrae[-1])
                if curve_obj and last_pb:
                    c = last_pb.constraints.new("SPLINE_IK")
                    c.name = "CR"
                    c.target = curve_obj
                    c.chain_count = len(vertebrae)
                    c.use_chain_offset = False
                    c.use_even_divisions = False
                    c.use_curve_radius = False
                    c.y_scale_mode = "FIT_CURVE"
                    c.xz_scale_mode = "NONE"
                    log.append(f"OK SplineIK on {vertebrae[-1]} (chain={len(vertebrae)})")
                else:
                    log.append(f"SKIP SplineIK: curve or bone not found")
        elif t == "arm":
            side = s["side"]
            if s.get("shoulder"):
                log.append(_add_copy_transforms(skel_obj, cr_obj, s["shoulder"], f"FK_Shoulder.{side}"))
            for def_key, ctrl in (
                ("upper_arm", f"FK_UpperArm.{side}"),
                ("forearm", f"FK_Forearm.{side}"),
                ("hand", f"FK_Hand.{side}"),
            ):
                if s.get(def_key):
                    log.append(_add_copy_transforms(skel_obj, cr_obj, s[def_key], ctrl))
        elif t == "leg":
            side = s["side"]
            for def_key, ctrl in (
                ("upper_leg", f"IK_UpperLeg.{side}"),
                ("lower_leg", f"IK_LowerLeg.{side}"),
                ("foot", f"IK_Ankle.{side}"),
                ("toe", f"FK_Toe.{side}"),
            ):
                if s.get(def_key):
                    log.append(_add_copy_transforms(skel_obj, cr_obj, s[def_key], ctrl))
        elif t == "head":
            if s.get("neck"):
                log.append(_add_copy_transforms(skel_obj, cr_obj, s["neck"], "FK_Neck"))
            log.append(_add_copy_transforms(skel_obj, cr_obj, s["head"], "FK_Head"))
        elif t == "finger":
            for i, bone_name in enumerate(s.get("chain") or []):
                log.append(_add_copy_transforms(skel_obj, cr_obj, bone_name, _finger_ctrl_name(s, i)))
    return log


def cleanup_existing_cr(skel_obj):
    for pb in skel_obj.pose.bones:
        for c in list(pb.constraints):
            if c.name in ("CR", "CR_FK", "CR_IKFK"):
                pb.constraints.remove(c)
    if skel_obj.animation_data:
        for fc in list(skel_obj.animation_data.drivers):
            if '"CR_IKFK"' in fc.data_path:
                skel_obj.animation_data.drivers.remove(fc)
