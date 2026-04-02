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
            summary = [f"{s['type']}.{s.get('side', '-')}" for s in systems]
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
            fingers = {}
            for fname, chain in (entry.get("fingers") or {}).items():
                resolved = resolve_chain(chain)
                if resolved:
                    fingers[fname] = resolved
            systems.append({
                "type": "arm",
                "side": str(entry.get("side") or "L"),
                "parent": entry.get("parent"),
                "shoulder": resolve(entry.get("shoulder")),
                "upper_arm": upper_arm,
                "forearm": forearm,
                "hand": hand,
                "fingers": fingers,
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
            for chain in (s.get("fingers") or {}).values():
                names.update(chain)
        elif t == "leg":
            for key in ("upper_leg", "lower_leg", "foot", "toe"):
                if s.get(key):
                    names.add(s[key])
        elif t == "head":
            for key in ("neck", "head"):
                if s.get(key):
                    names.add(s[key])
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


def create_root_shape(name):
    s = 1.0
    square = [(-s, 0, s), (s, 0, s), (s, 0, -s), (-s, 0, -s)]
    return _wire_shape(name, [
        (square, True),
        ([(-s, 0, 0), (s, 0, 0)], False),
        ([(0, 0, -s), (0, 0, s)], False),
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


def _build_spine_system(ebs, system, bd, root_eb):
    """Build spine control bones.

    Returns (hips_eb, chest_eb, deform_to_ctrl) where deform_to_ctrl maps
    deform bone names to their primary edit bones for parent resolution.
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
        ctrl_name = "FK_Chest" if i == len(chain) - 1 else f"FK_{name}"
        connected = prev_data is not None and _connected(d["head"], prev_data["tail"])
        ctrl_eb = _eb(ebs, ctrl_name, d["head"], d["tail"], d["roll"], prev, connected)
        deform_to_ctrl[name] = ctrl_eb
        prev, prev_data = ctrl_eb, d
        chest_eb = ctrl_eb

    return hips_eb, chest_eb, deform_to_ctrl


def _build_arm_system(ebs, system, bd, parent_eb):
    """Build arm FK control bones including fingers."""
    s = system["side"]
    arm_root = parent_eb

    if system.get("shoulder") and system["shoulder"] in bd:
        d = bd[system["shoulder"]]
        sh_eb = _eb(ebs, f"FK_Shoulder.{s}", d["head"], d["tail"], d["roll"], parent_eb, False)
        arm_root = sh_eb

    u_data = bd[system["upper_arm"]]
    upper_eb = _eb(ebs, f"FK_UpperArm.{s}", u_data["head"], u_data["tail"], u_data["roll"], arm_root, False)

    f_data = bd[system["forearm"]]
    forearm_eb = _eb(ebs, f"FK_Forearm.{s}", f_data["head"], f_data["tail"], f_data["roll"], upper_eb,
                     _connected(f_data["head"], u_data["tail"]))

    h_data = bd[system["hand"]]
    hand_eb = _eb(ebs, f"FK_Hand.{s}", h_data["head"], h_data["tail"], h_data["roll"], forearm_eb,
                  _connected(h_data["head"], f_data["tail"]))

    for finger_name, chain in (system.get("fingers") or {}).items():
        prev, prev_data = hand_eb, None
        for bone_name in chain:
            if bone_name not in bd:
                continue
            d = bd[bone_name]
            connected = prev_data is not None and _connected(d["head"], prev_data["tail"])
            prev = _eb(ebs, f"FK_{bone_name}", d["head"], d["tail"], d["roll"], prev, connected)
            prev_data = d


def _build_leg_system(ebs, system, bd, parent_eb):
    """Build leg IK control bones with a hidden mechanism chain and a free foot target."""
    s = system["side"]
    u_data = bd[system["upper_leg"]]
    l_data = bd[system["lower_leg"]]
    f_data = bd[system["foot"]]
    ik_u = _eb(ebs, f"IK_UpperLeg.{s}", u_data["head"], u_data["tail"], u_data["roll"], parent_eb, False)
    _eb(ebs, f"IK_LowerLeg.{s}", l_data["head"], l_data["tail"], l_data["roll"], ik_u,
        _connected(l_data["head"], u_data["tail"]))
    _eb(ebs, f"IK_Foot.{s}", f_data["head"], f_data["tail"], f_data["roll"])
    pole = _calc_pole_pos(u_data["head"], u_data["tail"], l_data["tail"])
    _eb(ebs, f"Pole_Knee.{s}", pole, pole + mathutils.Vector((0.0, 0.05, 0.0)), 0.0)


def _build_head_system(ebs, system, bd, parent_eb):
    """Build neck and head FK control bones."""
    neck_eb = None
    if system.get("neck") and system["neck"] in bd:
        d = bd[system["neck"]]
        neck_eb = _eb(ebs, "FK_Neck", d["head"], d["tail"], d["roll"], parent_eb, False)
    if system["head"] in bd:
        d = bd[system["head"]]
        _eb(ebs, "FK_Head", d["head"], d["tail"], d["roll"], neck_eb or parent_eb, False)


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
            parent_eb = deform_to_ctrl.get(s.get("parent")) or chest_eb
            _build_arm_system(ebs, s, bone_data, parent_eb)
        elif t == "leg":
            parent_eb = hips_eb or deform_to_ctrl.get(s.get("parent")) or chest_eb
            _build_leg_system(ebs, s, bone_data, parent_eb)
        elif t == "head":
            parent_eb = deform_to_ctrl.get(s.get("parent")) or chest_eb
            _build_head_system(ebs, s, bone_data, parent_eb)


def _setup_spine_pose(cr_obj, system, shapes):
    """Pelvis as yellow oval, vertebrae as pink circles."""
    pbs = cr_obj.pose.bones
    if "FK_Pelvis" in pbs:
        _assign_shape(pbs["FK_Pelvis"], shapes["pelvis"], True, 3.0)
        _bone_color(pbs["FK_Pelvis"], dracula.YELLOW)
    if "FK_Hips" in pbs:
        _assign_shape(pbs["FK_Hips"], shapes["pelvis"], True, 2.0)
        _bone_color(pbs["FK_Hips"], dracula.YELLOW)
    chain = system.get("vertebrae") or []
    for i, name in enumerate(chain):
        ctrl = "FK_Chest" if i == len(chain) - 1 else f"FK_{name}"
        if ctrl in pbs:
            _assign_shape(pbs[ctrl], shapes["circle"], True, 1.25)
            _bone_color(pbs[ctrl], dracula.PINK)


def _setup_arm_pose(cr_obj, system, shapes):
    """Arm FK bones as purple circles. Forearm and fingers smaller than upper arm and hand."""
    pbs, s = cr_obj.pose.bones, system["side"]
    if f"FK_Shoulder.{s}" in pbs:
        _assign_shape(pbs[f"FK_Shoulder.{s}"], shapes["circle"], True, 0.3)
        _bone_color(pbs[f"FK_Shoulder.{s}"], dracula.PURPLE)
    for name in (f"FK_UpperArm.{s}", f"FK_Hand.{s}"):
        if name in pbs:
            _assign_shape(pbs[name], shapes["circle"], True, 0.4)
            _bone_color(pbs[name], dracula.PURPLE)
    if f"FK_Forearm.{s}" in pbs:
        _assign_shape(pbs[f"FK_Forearm.{s}"], shapes["circle"], True, 0.3)
        _bone_color(pbs[f"FK_Forearm.{s}"], dracula.PURPLE)
    for chain in (system.get("fingers") or {}).values():
        for bone_name in chain:
            ctrl = f"FK_{bone_name}"
            if ctrl in pbs:
                _assign_shape(pbs[ctrl], shapes["circle"], True, 0.3)
                _bone_color(pbs[ctrl], dracula.PURPLE)


def _setup_leg_pose(cr_obj, system, shapes):
    """IK foot as cyan box, knee pole as orange diamond. Mechanism chain hidden."""
    pbs, s = cr_obj.pose.bones, system["side"]
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


def _setup_head_pose(cr_obj, shapes):
    """Neck and head as pink circles, head slightly larger."""
    pbs = cr_obj.pose.bones
    if "FK_Neck" in pbs:
        _assign_shape(pbs["FK_Neck"], shapes["circle"], True, 0.6)
        _bone_color(pbs["FK_Neck"], dracula.PINK)
    if "FK_Head" in pbs:
        _assign_shape(pbs["FK_Head"], shapes["circle"], True, 0.8)
        _bone_color(pbs["FK_Head"], dracula.PINK)


def setup_control_rig_pose(cr_obj, systems, shapes):
    """Apply custom shapes, colors, and constraints to all control bones."""
    cr_obj.data.pose_position = "POSE"
    pbs = cr_obj.pose.bones
    if "FK_Root" in pbs:
        _assign_shape(pbs["FK_Root"], shapes["root"], False, 50.0)
        _bone_color(pbs["FK_Root"], dracula.GREEN)
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
            chain = s.get("vertebrae") or []
            for i, name in enumerate(chain):
                ctrl = "FK_Chest" if i == len(chain) - 1 else f"FK_{name}"
                log.append(_add_copy_transforms(skel_obj, cr_obj, name, ctrl))
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
            for chain in (s.get("fingers") or {}).values():
                for bone_name in chain:
                    log.append(_add_copy_transforms(skel_obj, cr_obj, bone_name, f"FK_{bone_name}"))
        elif t == "leg":
            side = s["side"]
            for def_key, ctrl in (
                ("upper_leg", f"IK_UpperLeg.{side}"),
                ("lower_leg", f"IK_LowerLeg.{side}"),
                ("foot", f"IK_Foot.{side}"),
            ):
                if s.get(def_key):
                    log.append(_add_copy_transforms(skel_obj, cr_obj, s[def_key], ctrl))
        elif t == "head":
            if s.get("neck"):
                log.append(_add_copy_transforms(skel_obj, cr_obj, s["neck"], "FK_Neck"))
            log.append(_add_copy_transforms(skel_obj, cr_obj, s["head"], "FK_Head"))
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
