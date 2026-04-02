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


def _spine_ctrl_name(index, total):
    """Return the consistent control bone name for a spine vertebra at a given index.

    The last vertebra in the chain is always named FK_Chest.
    """
    if index == total - 1:
        return "FK_Chest"
    return f"FK_Spine.{index + 1:03d}"


def _build_spine_system(ebs, system, bd, root_eb):
    """Build spine control bones.

    Returns (hips_eb, chest_eb, deform_to_ctrl) where deform_to_ctrl maps
    deform bone names to their ctrl edit bones for parent resolution by other systems.
    """
    deform_to_ctrl = {}
    pelvis_eb = None
    hips_eb = None

    if system.get("pelvis") and system["pelvis"] in bd:
        d = bd[system["pelvis"]]
        bone_len = (d["tail"] - d["head"]).length
        pelvis_eb = _eb(ebs, "FK_Pelvis", d["head"], d["tail"], d["roll"], root_eb, False)
        hips_tail = d["head"] + mathutils.Vector((0.0, 0.0, -max(bone_len * 0.5, 0.05)))
        hips_eb = _eb(ebs, "FK_Hips", d["head"], hips_tail, d["roll"], pelvis_eb, False)
        deform_to_ctrl[system["pelvis"]] = pelvis_eb

    spine_root = pelvis_eb or root_eb
    prev, prev_data = spine_root, None
    chest_eb = spine_root

    chain = [n for n in (system.get("vertebrae") or []) if n in bd]
    for i, name in enumerate(chain):
        d = bd[name]
        ctrl_eb = _eb(ebs, _spine_ctrl_name(i, len(chain)), d["head"], d["tail"], d["roll"], prev,
                      prev_data is not None and _connected(d["head"], prev_data["tail"]))
        deform_to_ctrl[name] = ctrl_eb
        prev, prev_data = ctrl_eb, d
        chest_eb = ctrl_eb

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
    """Build leg IK control bones with a hidden mechanism chain and a free foot target.

    IK_Foot and Pole_Knee are parented to FK_Root so they move with the master control.
    """
    s = system["side"]
    root_eb = ebs.get("FK_Root")
    u_data = bd[system["upper_leg"]]
    l_data = bd[system["lower_leg"]]
    f_data = bd[system["foot"]]
    ik_u = _eb(ebs, f"IK_UpperLeg.{s}", u_data["head"], u_data["tail"], u_data["roll"], parent_eb, False)
    _eb(ebs, f"IK_LowerLeg.{s}", l_data["head"], l_data["tail"], l_data["roll"], ik_u,
        _connected(l_data["head"], u_data["tail"]))
    foot_eb = _eb(ebs, f"IK_Foot.{s}", f_data["head"], f_data["tail"], f_data["roll"], root_eb)
    if system.get("toe") and system["toe"] in bd:
        t_data = bd[system["toe"]]
        _eb(ebs, f"FK_Toe.{s}", t_data["head"], t_data["tail"], t_data["roll"], foot_eb,
            _connected(t_data["head"], f_data["tail"]))
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
            parent_eb = deform_to_ctrl.get(s.get("parent")) or chest_eb
            _build_head_system(ebs, s, bone_data, parent_eb)

    for s in systems:
        if s["type"] == "finger":
            parent_eb = deform_to_ctrl.get(s.get("parent")) or chest_eb
            _build_finger_system(ebs, s, bone_data, parent_eb)


def _setup_spine_pose(cr_obj, system, shapes):
    """Pelvis and vertebrae as purple circles (central controls)."""
    pbs = cr_obj.pose.bones
    if "FK_Pelvis" in pbs:
        _assign_shape(pbs["FK_Pelvis"], shapes["circle"], True, (3.0, 3.0, 1.5))
        _bone_color(pbs["FK_Pelvis"], dracula.PURPLE)
    if "FK_Hips" in pbs:
        _assign_shape(pbs["FK_Hips"], shapes["circle"], True, (2.0, 2.0, 1.0))
        _bone_color(pbs["FK_Hips"], dracula.PURPLE)
    chain = system.get("vertebrae") or []
    for i in range(len(chain)):
        ctrl = _spine_ctrl_name(i, len(chain))
        if ctrl in pbs:
            _assign_shape(pbs[ctrl], shapes["circle"], True, 1.25)
            _bone_color(pbs[ctrl], dracula.PURPLE)


def _setup_arm_pose(cr_obj, system, shapes):
    """Arm FK bones colored by side: left=yellow, right=green."""
    pbs, s = cr_obj.pose.bones, system["side"]
    color = _side_color(s)
    if f"FK_Shoulder.{s}" in pbs:
        _assign_shape(pbs[f"FK_Shoulder.{s}"], shapes["circle"], True, 0.3)
        _bone_color(pbs[f"FK_Shoulder.{s}"], color)
    for name in (f"FK_UpperArm.{s}", f"FK_Hand.{s}"):
        if name in pbs:
            _assign_shape(pbs[name], shapes["circle"], True, 0.4)
            _bone_color(pbs[name], color)
    if f"FK_Forearm.{s}" in pbs:
        _assign_shape(pbs[f"FK_Forearm.{s}"], shapes["circle"], True, 0.3)
        _bone_color(pbs[f"FK_Forearm.{s}"], color)


def _setup_leg_pose(cr_obj, system, shapes):
    """IK foot as box, knee swivel as sphere, both colored by side. Mechanism chain hidden."""
    pbs, s = cr_obj.pose.bones, system["side"]
    color = _side_color(s)
    if f"IK_Foot.{s}" in pbs:
        _assign_shape(pbs[f"IK_Foot.{s}"], shapes["box"], False, 10.0)
        _bone_color(pbs[f"IK_Foot.{s}"], color)
    if f"FK_Toe.{s}" in pbs:
        _assign_shape(pbs[f"FK_Toe.{s}"], shapes["box"], False, 6.0)
        _bone_color(pbs[f"FK_Toe.{s}"], color)
    if f"Pole_Knee.{s}" in pbs:
        _assign_shape(pbs[f"Pole_Knee.{s}"], shapes["sphere"], False, 4.0)
        _bone_color(pbs[f"Pole_Knee.{s}"], color)
    if f"IK_LowerLeg.{s}" in pbs:
        upper_pb = pbs.get(f"IK_UpperLeg.{s}")
        lower_pb = pbs[f"IK_LowerLeg.{s}"]
        pole_pb = pbs.get(f"Pole_Knee.{s}")
        c = lower_pb.constraints.new("IK")
        c.target, c.subtarget = cr_obj, f"IK_Foot.{s}"
        c.pole_target, c.pole_subtarget = cr_obj, f"Pole_Knee.{s}"
        c.chain_count, c.use_stretch = 2, False
        if upper_pb and pole_pb:
            c.pole_angle = _calc_pole_angle(upper_pb, lower_pb, pole_pb.bone.head_local)
    for name in (f"IK_UpperLeg.{s}", f"IK_LowerLeg.{s}"):
        if name in pbs:
            pbs[name].bone.hide = True


def _setup_head_pose(cr_obj, shapes):
    """Neck and head as purple circles (central controls), head slightly larger."""
    pbs = cr_obj.pose.bones
    if "FK_Neck" in pbs:
        _assign_shape(pbs["FK_Neck"], shapes["circle"], True, 0.6)
        _bone_color(pbs["FK_Neck"], dracula.PURPLE)
    if "FK_Head" in pbs:
        _assign_shape(pbs["FK_Head"], shapes["circle"], True, 0.8)
        _bone_color(pbs["FK_Head"], dracula.PURPLE)


def _setup_finger_pose(cr_obj, system, shapes):
    """Finger FK bones colored by side: left=yellow, right=green."""
    pbs = cr_obj.pose.bones
    color = _side_color(system["side"])
    for i in range(len(system.get("chain") or [])):
        ctrl = _finger_ctrl_name(system, i)
        if ctrl in pbs:
            _assign_shape(pbs[ctrl], shapes["circle"], True, 0.3)
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
                log.append(_add_copy_transforms(skel_obj, cr_obj, s["pelvis"], "FK_Pelvis"))
            vertebrae = s.get("vertebrae") or []
            for i, name in enumerate(vertebrae):
                log.append(_add_copy_transforms(skel_obj, cr_obj, name, _spine_ctrl_name(i, len(vertebrae))))
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
                ("foot", f"IK_Foot.{side}"),
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
