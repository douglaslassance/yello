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
    """Ask Ollama to map bone names to limb roles.

    Returns (limbs, message) where limbs is a dict keyed by (type, side) tuples,
    or (None, error_message).
    """
    bone_list = "\n".join(f"  - {n}" for n in sorted(bone_names))
    user_msg = _load_prompt("classify_bones_user.md").replace("{bone_list}", bone_list)
    system_msg = _load_prompt("classify_bones_system.md")
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user",   "content": user_msg},
    ]

    try:
        raw = ollama.chat(messages)
        data = json.loads(raw or "{}")
        limbs = _parse_limbs(data, bone_names)
        if limbs:
            return limbs, f"Identified: {[f'{t}.{s}' for t, s in limbs.keys()]}"
        return None, f"Could not parse limbs from Ollama response: {raw[:300]}"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        return None, f"Ollama HTTP {exc.code}: {body[:200]}"
    except Exception as exc:
        return None, f"Ollama error: {exc}"


def _parse_limbs(data, bone_names):
    lookup = {n.strip().lower(): n for n in bone_names}

    def resolve(v):
        return lookup.get(v.strip().lower()) if isinstance(v, str) else None

    def resolve_chain(lst):
        return [r for r in (resolve(n) for n in lst if isinstance(n, str)) if r]

    limbs = {}
    for key, (t, side) in {
        "arm_L": ("arm", "L"), "arm_R": ("arm", "R"),
        "leg_L": ("leg", "L"), "leg_R": ("leg", "R"),
    }.items():
        entry = data.get(key)
        if not isinstance(entry, dict):
            continue
        bones = {role: resolve(name) for role, name in entry.items() if resolve(name)}
        required = ("upper", "lower", "hand") if t == "arm" else ("upper", "lower", "foot")
        if all(r in bones for r in required):
            limbs[(t, side)] = bones

    spine = resolve_chain(data.get("spine") or [])
    if spine:
        limbs[("spine", None)] = {"chain": spine}

    pelvis = resolve(data.get("pelvis"))
    if pelvis:
        limbs[("pelvis", None)] = {"root": pelvis}

    neck = resolve(data.get("neck"))
    if neck:
        limbs[("neck", None)] = {"bone": neck}

    head = resolve(data.get("head"))
    if head:
        limbs[("head", None)] = {"bone": head}

    for key, side in (("fingers_L", "L"), ("fingers_R", "R")):
        entry = data.get(key)
        if not isinstance(entry, dict):
            continue
        fingers = {name: resolve_chain(chain) for name, chain in entry.items()
                   if isinstance(chain, list)}
        fingers = {k: v for k, v in fingers.items() if v}
        if fingers:
            limbs[("fingers", side)] = fingers

    return limbs or None


def extract_bone_names(limbs):
    """Return the flat set of all deform bone names referenced by limbs."""
    names = set()
    for (limb_type, side), bones in limbs.items():
        if limb_type == "fingers":
            for chain in bones.values():
                names.update(chain)
        elif limb_type in ("neck", "head"):
            names.add(bones["bone"])
        elif limb_type == "spine":
            names.update(bones["chain"])
        else:
            for v in bones.values():
                if isinstance(v, str):
                    names.add(v)
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
        (-s, -s, -s), ( s, -s, -s), ( s,  s, -s), (-s,  s, -s),
        (-s, -s,  s), ( s, -s,  s), ( s,  s,  s), (-s,  s,  s),
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


def create_root_shape(name):
    s = 1.0
    square = [(-s, 0, s), (s, 0, s), (s, 0, -s), (-s, 0, -s)]
    return _wire_shape(name, [
        (square, True),
        ([(-s, 0, 0), (s, 0, 0)], False),
        ([(0, 0, -s), (0, 0,  s)], False),
    ])


def create_pelvis_shape(name):
    n = 16
    pts = [(1.2 * math.cos(2 * math.pi * i / n), 0.0, 0.5 * math.sin(2 * math.pi * i / n)) for i in range(n)]
    return _wire_shape(name, [(pts, True)])


def _calc_pole_pos(upper_head, upper_tail, lower_tail):
    v1 = upper_tail - upper_head
    v2 = lower_tail - upper_tail
    normal = v1.cross(v2)
    dist = v1.length
    if normal.length > 1e-4:
        return upper_tail + normal.normalized() * dist
    return upper_tail + mathutils.Vector((0.0, dist, 0.0))


def _eb(ebs, name, head, tail, roll, parent=None, connect=False):
    b = ebs.new(name)
    b.head, b.tail, b.roll, b.use_deform = head, tail, roll, False
    if parent:
        b.parent = parent
        b.use_connect = connect
    return b


def _connected(head, parent_tail):
    return (head - parent_tail).length < 1e-4


def _build_arm_bones(ebs, side, bones, bd, root_parent=None):
    """FK only. Optional shoulder/clavicle sits between chest and upper arm."""
    s = side
    u, l, h = bd[bones["upper"]], bd[bones["lower"]], bd[bones["hand"]]

    arm_root = root_parent
    if "shoulder" in bones and bones["shoulder"] in bd:
        sh = bd[bones["shoulder"]]
        fk_sh = _eb(ebs, f"FK_Shoulder.{s}", sh["head"], sh["tail"], sh["roll"], root_parent, False)
        arm_root = fk_sh

    fk_u = _eb(ebs, f"FK_UpperArm.{s}", u["head"], u["tail"], u["roll"], arm_root, False)
    fk_l = _eb(ebs, f"FK_LowerArm.{s}", l["head"], l["tail"], l["roll"], fk_u, _connected(l["head"], u["tail"]))
    _eb(ebs, f"FK_Hand.{s}", h["head"], h["tail"], h["roll"], fk_l, _connected(h["head"], l["tail"]))


def _build_leg_bones(ebs, side, bones, bd, root_parent=None):
    """IK only — hidden mechanism chain + foot control + pole. Root parented to pelvis."""
    u, l, f = bd[bones["upper"]], bd[bones["lower"]], bd[bones["foot"]]
    s = side
    ik_u = _eb(ebs, f"IK_UpperLeg.{s}", u["head"], u["tail"], u["roll"], root_parent, False)
    _eb(ebs, f"IK_LowerLeg.{s}", l["head"], l["tail"], l["roll"], ik_u, _connected(l["head"], u["tail"]))
    _eb(ebs, f"IK_Foot.{s}", f["head"], f["tail"], f["roll"])
    pole = _calc_pole_pos(u["head"], u["tail"], l["tail"])
    _eb(ebs, f"Pole_Knee.{s}", pole, pole + mathutils.Vector((0.0, 0.05, 0.0)), 0.0)


def _spine_ctrl(i, chain_len, name):
    """Return the CR bone name for spine bone at position i in a chain of chain_len."""
    return "FK_Chest" if i == chain_len - 1 else f"FK_{name}"


def _build_spine_bones(ebs, bones, bd, root_parent=None):
    chain = [n for n in bones["chain"] if n in bd]
    prev, prev_data = root_parent, None
    for i, name in enumerate(chain):
        d = bd[name]
        ctrl_name = _spine_ctrl(i, len(chain), name)
        connected = prev is not None and prev_data is not None and _connected(d["head"], prev_data["tail"])
        prev = _eb(ebs, ctrl_name, d["head"], d["tail"], d["roll"], prev, connected)
        prev_data = d


def _build_single_bone(ebs, ctrl_name, src_name, bd, parent=None):
    if src_name not in bd:
        return None
    d = bd[src_name]
    return _eb(ebs, ctrl_name, d["head"], d["tail"], d["roll"], parent, False)


def _build_finger_bones(ebs, side, bones, bd, hand_eb=None):
    """FK chain per finger, rooted at FK_Hand.{side}."""
    for finger_name, chain in bones.items():
        prev, prev_data = hand_eb, None
        for bone_name in chain:
            if bone_name not in bd:
                continue
            d = bd[bone_name]
            connected = prev is not None and prev_data is not None and _connected(d["head"], prev_data["tail"])
            prev = _eb(ebs, f"FK_{bone_name}", d["head"], d["tail"], d["roll"], prev, connected)
            prev_data = d


def _build_pelvis_bone(ebs, bones, bd, root_parent=None):
    name = bones["root"]
    if name not in bd:
        return None, None
    d = bd[name]
    bone_len = (d["tail"] - d["head"]).length
    pelvis_eb = _eb(ebs, "FK_Pelvis", d["head"], d["tail"], d["roll"], root_parent, False)
    hips_tail = d["head"] + mathutils.Vector((0.0, 0.0, -max(bone_len * 0.5, 0.05)))
    hips_eb = _eb(ebs, "FK_Hips", d["head"], hips_tail, d["roll"], pelvis_eb, False)
    return pelvis_eb, hips_eb


def build_control_bones(cr_arm_data, limbs, bone_data):
    ebs = cr_arm_data.edit_bones

    root_tail = mathutils.Vector((0.0, 0.1, 0.0))
    root_eb = _eb(ebs, "FK_Root", mathutils.Vector((0.0, 0.0, 0.0)), root_tail, 0.0)

    pelvis_eb, hips_eb = None, None
    for (limb_type, side), bones in limbs.items():
        if limb_type == "pelvis":
            pelvis_eb, hips_eb = _build_pelvis_bone(ebs, bones, bone_data, root_parent=root_eb)
    spine_root = pelvis_eb or root_eb

    spine_top_eb = None
    for (limb_type, side), bones in limbs.items():
        if limb_type == "spine":
            _build_spine_bones(ebs, bones, bone_data, root_parent=spine_root)
            if bones["chain"]:
                spine_top_eb = ebs.get("FK_Chest")
    chest_eb = spine_top_eb or spine_root

    neck_eb = None
    for (limb_type, side), bones in limbs.items():
        if limb_type == "neck":
            neck_eb = _build_single_bone(ebs, "FK_Neck", bones["bone"], bone_data, chest_eb)
        elif limb_type == "head":
            _build_single_bone(ebs, "FK_Head", bones["bone"], bone_data, neck_eb or chest_eb)

    for (limb_type, side), bones in limbs.items():
        if limb_type == "arm":
            _build_arm_bones(ebs, side, bones, bone_data, chest_eb)
        elif limb_type == "leg":
            _build_leg_bones(ebs, side, bones, bone_data, hips_eb or spine_root)

    for (limb_type, side), bones in limbs.items():
        if limb_type == "fingers":
            _build_finger_bones(ebs, side, bones, bone_data, ebs.get(f"FK_Hand.{side}"))


def _bone_color(pb, color):
    pb.color.palette = "CUSTOM"
    pb.color.custom.normal = color
    pb.color.custom.select = tuple(min(1.0, c + 0.2) for c in color)
    pb.color.custom.active = (1.0, 1.0, 1.0)


def _assign_shape(pb, shape, use_bone_size=True, scale=1.0):
    pb.custom_shape = shape
    pb.use_custom_shape_bone_size = use_bone_size
    pb.custom_shape_scale_xyz = (scale, scale, scale)
    pb.custom_shape_wire_width = 3.0


def _setup_arm_pose(cr_obj, side, shapes):
    """FK circles — purple. Shoulder slightly smaller."""
    pbs, s = cr_obj.pose.bones, side
    if f"FK_Shoulder.{s}" in pbs:
        _assign_shape(pbs[f"FK_Shoulder.{s}"], shapes["circle"], True, 0.3)
        _bone_color(pbs[f"FK_Shoulder.{s}"], dracula.PURPLE)
    for name in (f"FK_UpperArm.{s}", f"FK_LowerArm.{s}", f"FK_Hand.{s}"):
        if name in pbs:
            _assign_shape(pbs[name], shapes["circle"], True, 0.4)
            _bone_color(pbs[name], dracula.PURPLE)


def _setup_leg_pose(cr_obj, side, shapes):
    """IK foot box (cyan) + knee pole diamond (orange). Mechanism bones hidden."""
    pbs, s = cr_obj.pose.bones, side
    if f"IK_Foot.{s}" in pbs:
        _assign_shape(pbs[f"IK_Foot.{s}"], shapes["box"], False, 0.18)
        _bone_color(pbs[f"IK_Foot.{s}"], dracula.CYAN)
    if f"Pole_Knee.{s}" in pbs:
        _assign_shape(pbs[f"Pole_Knee.{s}"], shapes["diamond"], False, 8.0)
        _bone_color(pbs[f"Pole_Knee.{s}"], dracula.ORANGE)
    if f"IK_LowerLeg.{s}" in pbs:
        c = pbs[f"IK_LowerLeg.{s}"].constraints.new("IK")
        c.target, c.subtarget = cr_obj, f"IK_Foot.{s}"
        c.pole_target, c.pole_subtarget = cr_obj, f"Pole_Knee.{s}"
        c.pole_angle, c.chain_count, c.use_stretch = 0.0, 2, False
    for name in (f"IK_UpperLeg.{s}", f"IK_LowerLeg.{s}"):
        if name in pbs:
            pbs[name].bone.hide = True


def _setup_spine_pose(cr_obj, bones, shapes):
    """FK circles — pink. Last spine bone is always called FK_Chest."""
    pbs = cr_obj.pose.bones
    chain = bones["chain"]
    for i, name in enumerate(chain):
        ctrl = _spine_ctrl(i, len(chain), name)
        if ctrl in pbs:
            _assign_shape(pbs[ctrl], shapes["circle"], True, 0.6)
            _bone_color(pbs[ctrl], dracula.PINK)


def _setup_neck_head_pose(cr_obj, shapes):
    pbs = cr_obj.pose.bones
    if "FK_Neck" in pbs:
        _assign_shape(pbs["FK_Neck"], shapes["circle"], True, 0.6)
        _bone_color(pbs["FK_Neck"], dracula.PINK)
    if "FK_Head" in pbs:
        _assign_shape(pbs["FK_Head"], shapes["circle"], True, 0.8)
        _bone_color(pbs["FK_Head"], dracula.PINK)


def _setup_fingers_pose(cr_obj, side, bones, shapes):
    pbs = cr_obj.pose.bones
    for chain in bones.values():
        for bone_name in chain:
            ctrl = f"FK_{bone_name}"
            if ctrl in pbs:
                _assign_shape(pbs[ctrl], shapes["circle"], True, 0.25)
                _bone_color(pbs[ctrl], dracula.PURPLE)


def _setup_pelvis_pose(cr_obj, shapes):
    """FK_Pelvis: large oval (yellow). FK_Hips: medium oval (yellow)."""
    pbs = cr_obj.pose.bones
    if "FK_Pelvis" in pbs:
        _assign_shape(pbs["FK_Pelvis"], shapes["pelvis"], True, 3.0)
        _bone_color(pbs["FK_Pelvis"], dracula.YELLOW)
    if "FK_Hips" in pbs:
        _assign_shape(pbs["FK_Hips"], shapes["pelvis"], True, 2.0)
        _bone_color(pbs["FK_Hips"], dracula.YELLOW)


def setup_control_rig_pose(cr_obj, limbs, shapes):
    cr_obj.data.pose_position = "POSE"
    pbs = cr_obj.pose.bones
    if "FK_Root" in pbs:
        _assign_shape(pbs["FK_Root"], shapes["root"], False, 50.0)
        _bone_color(pbs["FK_Root"], dracula.GREEN)
    for (limb_type, side), bones in limbs.items():
        if limb_type == "arm":
            _setup_arm_pose(cr_obj, side, shapes)
        elif limb_type == "leg":
            _setup_leg_pose(cr_obj, side, shapes)
        elif limb_type == "spine":
            _setup_spine_pose(cr_obj, bones, shapes)
        elif limb_type == "pelvis":
            _setup_pelvis_pose(cr_obj, shapes)
        elif limb_type in ("neck", "head"):
            _setup_neck_head_pose(cr_obj, shapes)
        elif limb_type == "fingers":
            _setup_fingers_pose(cr_obj, side, bones, shapes)


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


def wire_deform_constraints(skel_obj, cr_obj, limbs):
    skel_obj.data.pose_position = "POSE"
    log = []
    for (limb_type, side), bones in limbs.items():
        s = side
        if limb_type == "spine":
            chain = bones["chain"]
            for i, name in enumerate(chain):
                ctrl = _spine_ctrl(i, len(chain), name)
                log.append(_add_copy_transforms(skel_obj, cr_obj, name, ctrl))
        elif limb_type == "pelvis":
            log.append(_add_copy_transforms(skel_obj, cr_obj, bones["root"], "FK_Pelvis"))
        elif limb_type == "neck":
            log.append(_add_copy_transforms(skel_obj, cr_obj, bones["bone"], "FK_Neck"))
        elif limb_type == "head":
            log.append(_add_copy_transforms(skel_obj, cr_obj, bones["bone"], "FK_Head"))
        elif limb_type == "fingers":
            for chain in bones.values():
                for bone_name in chain:
                    log.append(_add_copy_transforms(skel_obj, cr_obj, bone_name, f"FK_{bone_name}"))
        elif limb_type == "arm":
            if bones.get("shoulder"):
                log.append(_add_copy_transforms(skel_obj, cr_obj, bones["shoulder"], f"FK_Shoulder.{s}"))
            for def_bone, ctrl in (
                (bones["upper"], f"FK_UpperArm.{s}"),
                (bones["lower"], f"FK_LowerArm.{s}"),
                (bones["hand"],  f"FK_Hand.{s}"),
            ):
                log.append(_add_copy_transforms(skel_obj, cr_obj, def_bone, ctrl))
        elif limb_type == "leg":
            for def_bone, ctrl in (
                (bones["upper"], f"IK_UpperLeg.{s}"),
                (bones["lower"], f"IK_LowerLeg.{s}"),
                (bones["foot"],  f"IK_Foot.{s}"),
            ):
                log.append(_add_copy_transforms(skel_obj, cr_obj, def_bone, ctrl))
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
