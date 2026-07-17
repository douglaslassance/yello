"""Tests for Ollama prompt correctness.

Run with: python -m pytest tests/test_prompts.py -v
Requires Ollama running locally with qwen2.5:32b (override with YELLO_TEST_MODEL).
"""

import json
import os
import unittest
import urllib.request
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
OLLAMA_URL = "http://localhost:11434"
MODEL = os.environ.get("YELLO_TEST_MODEL", "qwen2.5:32b")


def _ollama_reachable() -> bool:
    """Return True if an Ollama server is answering locally."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


requires_ollama = unittest.skipUnless(
    _ollama_reachable(), "Ollama not reachable at localhost:11434"
)


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _chat(system: str, user: str) -> dict:
    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as response:
        return json.loads(json.loads(response.read())["message"]["content"])


def _match_bones(source: list[str], target: list[str]) -> dict[str, str]:
    """Call match_bones prompts and return {source: target} dict."""
    system = _load_prompt("match_bones_system.md")
    source_list = "\n".join(f"  - {n}" for n in sorted(source))
    target_list = "\n".join(f"  - {n}" for n in sorted(target))
    user = (
        _load_prompt("match_bones_user.md")
        .replace("{source_bone_list}", source_list)
        .replace("{target_bone_list}", target_list)
    )
    data = _chat(system, user)
    return {pair["source"]: pair["target"] for pair in data.get("pairs", [])}


def _format_hierarchy(bones: list[str], parents: dict[str, str]) -> str:
    """Render an indented parent-to-child tree, matching rigging._format_hierarchy."""
    name_set = set(bones)
    children: dict[str, list[str]] = {}
    roots: list[str] = []
    for name in bones:
        parent = parents.get(name)
        if parent and parent in name_set:
            children.setdefault(parent, []).append(name)
        else:
            roots.append(name)
    lines: list[str] = []

    def walk(node: str, depth: int) -> None:
        lines.append(f"{'  ' * depth}- {node}")
        for child in children.get(node, []):
            walk(child, depth + 1)

    for root in roots:
        walk(root, 0)
    return "\n".join(lines)


def _classify_bones(bones: list[str], parents: dict[str, str] | None = None) -> list[dict]:
    """Call classify_bones prompts and return systems list.

    When parents is given, the bone hierarchy is included so the model can order
    chains by anatomy rather than by the numbering in the names.
    """
    system = _load_prompt("classify_bones_system.md")
    bone_list = "\n".join(f"  - {n}" for n in sorted(bones))
    hierarchy = _format_hierarchy(bones, parents) if parents else "(not provided)"
    user = (
        _load_prompt("classify_bones_user.md")
        .replace("{bone_list}", bone_list)
        .replace("{hierarchy}", hierarchy)
    )
    data = _chat(system, user)
    return data.get("systems", [])


@requires_ollama
class TestMatchBones(unittest.TestCase):

    def test_exact_match_takes_priority_over_synonym(self):
        """Pelvis_Control must map to itself even though Hips_Control is also present."""
        source = ["Pelvis_Control", "Chest_Control"]
        target = ["Pelvis_Control", "Hips_Control", "Torso_Control"]
        mapping = _match_bones(source, target)
        self.assertEqual(mapping.get("Pelvis_Control"), "Pelvis_Control")

    def test_synonym_match_when_no_exact(self):
        """Chest_Control must map to Torso_Control when Chest_Control is not in target."""
        source = ["Chest_Control"]
        target = ["Torso_Control", "Hips_Control"]
        mapping = _match_bones(source, target)
        self.assertEqual(mapping.get("Chest_Control"), "Torso_Control")

    def test_no_hallucinated_target_names(self):
        """Every target value must come from the target list."""
        source = ["Chest_Control", "Pelvis_Control", "UpperArm_Control.L"]
        target = ["Torso_Control", "Hips_Control", "Pelvis_Control", "UpperArm_Control.L"]
        target_set = set(target)
        mapping = _match_bones(source, target)
        for source_bone, target_bone in mapping.items():
            self.assertIn(target_bone, target_set, f"{source_bone} mapped to hallucinated name {target_bone!r}")

    def test_full_rig_transfer(self):
        """Full control rig transfer: exact matches stay, Chest maps to Torso, Pelvis stays."""
        source = [
            "Chest_Control", "Pelvis_Control", "Shoulder_Control.L", "Shoulder_Control.R",
            "UpperArm_Control.L", "UpperArm_Control.R", "Forearm_Control.L", "Forearm_Control.R",
            "Hand_Control.L", "Hand_Control.R", "Head_Control",
            "Leg_Pole_Control.L", "Leg_Pole_Control.R",
            "Leg_Target_Control.L", "Leg_Target_Control.R",
        ]
        target = [
            "Torso_Control", "Pelvis_Control", "Hips_Control",
            "Shoulder_Control.L", "Shoulder_Control.R",
            "UpperArm_Control.L", "UpperArm_Control.R", "Forearm_Control.L", "Forearm_Control.R",
            "Hand_Control.L", "Hand_Control.R", "Head_Control", "Neck_Control",
            "Leg_Pole_Control.L", "Leg_Pole_Control.R",
            "Leg_Target_Control.L", "Leg_Target_Control.R",
            "IK_Target_Control.L", "IK_Target_Control.R",
        ]
        target_set = set(target)
        mapping = _match_bones(source, target)

        self.assertEqual(mapping.get("Chest_Control"), "Torso_Control")
        self.assertEqual(mapping.get("Pelvis_Control"), "Pelvis_Control")
        self.assertEqual(mapping.get("Leg_Target_Control.L"), "Leg_Target_Control.L")
        self.assertEqual(mapping.get("Leg_Target_Control.R"), "Leg_Target_Control.R")
        for source_bone, target_bone in mapping.items():
            self.assertIn(target_bone, target_set, f"Hallucinated: {source_bone} -> {target_bone!r}")

    def test_twist_bones_ignored(self):
        """Twist bones must never appear in the output."""
        source = ["UpperArm_Control.L", "UpperArm.Twist.001.L", "Forearm_Control.L"]
        target = ["UpperArm_Control.L", "UpperArm.Twist.001.L", "Forearm_Control.L"]
        mapping = _match_bones(source, target)
        for source_bone in mapping:
            self.assertNotIn("Twist", source_bone)
        for target_bone in mapping.values():
            self.assertNotIn("Twist", target_bone)


@requires_ollama
class TestClassifyBones(unittest.TestCase):

    MIXAMO_BONES = [
        "Hips", "Spine", "Spine1", "Spine2",
        "Neck", "Head",
        "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
        "RightShoulder", "RightArm", "RightForeArm", "RightHand",
        "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase",
        "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase",
        "LeftHandThumb1", "LeftHandThumb2", "LeftHandThumb3",
        "LeftHandIndex1", "LeftHandIndex2", "LeftHandIndex3",
        "RightHandThumb1", "RightHandThumb2", "RightHandThumb3",
        "RightHandIndex1", "RightHandIndex2", "RightHandIndex3",
    ]

    def _get_systems_by_type(self, systems: list[dict]) -> dict:
        result = {}
        for system in systems:
            key = (system["type"], system.get("side", system.get("name", "")))
            result[key] = system
        return result

    def test_spine_identified(self):
        systems = _classify_bones(self.MIXAMO_BONES)
        types = [s.get("type") for s in systems]
        self.assertIn("spine", types)

    def test_spine_pelvis_is_hips(self):
        """Hips bone must be classified as pelvis, not as a vertebra."""
        systems = _classify_bones(self.MIXAMO_BONES)
        spine = next((s for s in systems if s.get("type") == "spine"), None)
        self.assertIsNotNone(spine)
        self.assertEqual(spine.get("pelvis"), "Hips")
        self.assertNotIn("Hips", spine.get("vertebrae", []))

    def test_arms_identified(self):
        systems = _classify_bones(self.MIXAMO_BONES)
        arm_sides = {s["side"] for s in systems if s.get("type") == "arm"}
        self.assertIn("L", arm_sides)
        self.assertIn("R", arm_sides)

    def test_legs_with_toes(self):
        systems = _classify_bones(self.MIXAMO_BONES)
        legs = [s for s in systems if s.get("type") == "leg"]
        self.assertEqual(len(legs), 2)
        for leg in legs:
            self.assertIsNotNone(leg.get("toe"), f"Leg {leg.get('side')} missing toe")

    def test_no_hallucinated_bone_names(self):
        """Every bone name in the output must come from the input list."""
        bone_set = set(self.MIXAMO_BONES)
        systems = _classify_bones(self.MIXAMO_BONES)
        for system in systems:
            for key, value in system.items():
                if key in ("type", "side", "name", "parent"):
                    continue
                if isinstance(value, str):
                    self.assertIn(value, bone_set, f"Hallucinated bone {value!r} in field {key!r}")
                elif isinstance(value, list):
                    for bone in value:
                        self.assertIn(bone, bone_set, f"Hallucinated bone {bone!r} in field {key!r}")

    def test_upper_arm_not_shoulder(self):
        """LeftArm must be classified as upper_arm, not shoulder."""
        systems = _classify_bones(self.MIXAMO_BONES)
        left_arm = next((s for s in systems if s.get("type") == "arm" and s.get("side") == "L"), None)
        self.assertIsNotNone(left_arm)
        self.assertEqual(left_arm.get("upper_arm"), "LeftArm")
        self.assertNotEqual(left_arm.get("shoulder"), "LeftArm")


@requires_ollama
class TestClassifyMetaHuman(unittest.TestCase):
    """Classify the MetaHuman / Unreal Engine 5 Mannequin body skeleton.

    MetaHuman characters deform on the same body skeleton as the UE5 Mannequin
    (Manny/Quinn). Beyond the standard chains this exercises conventions Mixamo
    lacks: lowercase _l/_r sides, clavicle/calf/ball synonyms, and the twist,
    IK, and root helper bones that must never be pulled into a rig system.
    """

    METAHUMAN_BONES = [
        "root",
        "pelvis",
        "spine_01", "spine_02", "spine_03", "spine_04", "spine_05",
        "neck_01", "neck_02", "head",
        "clavicle_l", "upperarm_l", "upperarm_twist_01_l",
        "lowerarm_l", "lowerarm_twist_01_l", "hand_l",
        "clavicle_r", "upperarm_r", "upperarm_twist_01_r",
        "lowerarm_r", "lowerarm_twist_01_r", "hand_r",
        "thigh_l", "thigh_twist_01_l", "calf_l", "calf_twist_01_l",
        "foot_l", "ball_l",
        "thigh_r", "thigh_twist_01_r", "calf_r", "calf_twist_01_r",
        "foot_r", "ball_r",
        "thumb_01_l", "thumb_02_l", "thumb_03_l",
        "index_01_l", "index_02_l", "index_03_l",
        "middle_01_l", "middle_02_l", "middle_03_l",
        "ring_01_l", "ring_02_l", "ring_03_l",
        "pinky_01_l", "pinky_02_l", "pinky_03_l",
        "thumb_01_r", "thumb_02_r", "thumb_03_r",
        "index_01_r", "index_02_r", "index_03_r",
        "middle_01_r", "middle_02_r", "middle_03_r",
        "ring_01_r", "ring_02_r", "ring_03_r",
        "pinky_01_r", "pinky_02_r", "pinky_03_r",
        "ik_foot_root", "ik_foot_l", "ik_foot_r",
        "ik_hand_root", "ik_hand_gun", "ik_hand_l", "ik_hand_r",
    ]

    def test_pelvis_is_pelvis_not_vertebra(self):
        systems = _classify_bones(self.METAHUMAN_BONES)
        spine = next((s for s in systems if s.get("type") == "spine"), None)
        self.assertIsNotNone(spine)
        self.assertEqual(spine.get("pelvis"), "pelvis")
        self.assertNotIn("pelvis", spine.get("vertebrae", []))

    def test_arms_use_clavicle_and_upperarm(self):
        """clavicle_l is the shoulder and upperarm_l is the upper_arm, not vice versa."""
        systems = _classify_bones(self.METAHUMAN_BONES)
        left_arm = next(
            (s for s in systems if s.get("type") == "arm" and s.get("side") == "L"), None
        )
        self.assertIsNotNone(left_arm)
        self.assertEqual(left_arm.get("upper_arm"), "upperarm_l")
        self.assertEqual(left_arm.get("forearm"), "lowerarm_l")
        self.assertEqual(left_arm.get("shoulder"), "clavicle_l")

    def test_legs_use_calf_and_ball(self):
        systems = _classify_bones(self.METAHUMAN_BONES)
        legs = [s for s in systems if s.get("type") == "leg"]
        self.assertEqual(len(legs), 2)
        for leg in legs:
            side = leg.get("side")
            self.assertEqual(leg.get("lower_leg"), f"calf_{side.lower()}")
            self.assertEqual(leg.get("toe"), f"ball_{side.lower()}")

    def test_twist_ik_and_root_bones_excluded(self):
        """Helper bones (twist/IK/root) must never appear in any rig system."""
        systems = _classify_bones(self.METAHUMAN_BONES)
        for system in systems:
            for value in system.values():
                values = value if isinstance(value, list) else [value]
                for bone in values:
                    if not isinstance(bone, str):
                        continue
                    self.assertNotIn("twist", bone.lower(), f"twist bone used: {bone}")
                    self.assertFalse(
                        bone.lower().startswith("ik_"), f"IK bone used: {bone}"
                    )
                    self.assertNotEqual(bone, "root", "root bone used as a rig bone")

    def test_no_hallucinated_bone_names(self):
        bone_set = set(self.METAHUMAN_BONES)
        systems = _classify_bones(self.METAHUMAN_BONES)
        for system in systems:
            for key, value in system.items():
                if key in ("type", "side", "name", "parent"):
                    continue
                values = value if isinstance(value, list) else [value]
                for bone in values:
                    if isinstance(bone, str):
                        self.assertIn(
                            bone, bone_set, f"Hallucinated bone {bone!r} in {key!r}"
                        )


@requires_ollama
class TestClassifyMeshy(unittest.TestCase):
    """Classify a Meshy AI biped skeleton (Crimson Titan sample).

    Meshy uses Mixamo-style limbs but quirks that Mixamo lacks: an inverted
    spine (Spine02 sits at the hips, bare Spine is the chest), mixed case (lower
    "neck", upper "Head"), leaf/helper head bones (head_end, headfront) that
    must be excluded, and no finger bones.
    """

    MESHY_BONES = [
        "Hips",
        "Spine", "Spine01", "Spine02",
        "neck", "Head", "head_end", "headfront",
        "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
        "RightShoulder", "RightArm", "RightForeArm", "RightHand",
        "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase",
        "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase",
    ]

    MESHY_PARENTS = {
        "Hips": None,
        "Spine02": "Hips", "Spine01": "Spine02", "Spine": "Spine01",
        "neck": "Spine", "Head": "neck", "head_end": "Head", "headfront": "Head",
        "LeftShoulder": "Spine", "LeftArm": "LeftShoulder",
        "LeftForeArm": "LeftArm", "LeftHand": "LeftForeArm",
        "RightShoulder": "Spine", "RightArm": "RightShoulder",
        "RightForeArm": "RightArm", "RightHand": "RightForeArm",
        "LeftUpLeg": "Hips", "LeftLeg": "LeftUpLeg",
        "LeftFoot": "LeftLeg", "LeftToeBase": "LeftFoot",
        "RightUpLeg": "Hips", "RightLeg": "RightUpLeg",
        "RightFoot": "RightLeg", "RightToeBase": "RightFoot",
    }

    def test_spine_pelvis_and_vertebrae(self):
        """Hips is the pelvis and all three spine bones are collected (names only)."""
        systems = _classify_bones(self.MESHY_BONES)
        spine = next((s for s in systems if s.get("type") == "spine"), None)
        self.assertIsNotNone(spine)
        self.assertEqual(spine.get("pelvis"), "Hips")
        self.assertEqual(
            set(spine.get("vertebrae", [])), {"Spine", "Spine01", "Spine02"}
        )

    def test_spine_ordered_by_hierarchy(self):
        """With the hierarchy provided, the inverted spine is ordered correctly.

        Meshy numbers the spine from the chest down, so low-to-high is
        Spine02, Spine01, Spine. The classifier must follow the hierarchy, not
        the digits.
        """
        systems = _classify_bones(self.MESHY_BONES, self.MESHY_PARENTS)
        spine = next((s for s in systems if s.get("type") == "spine"), None)
        self.assertIsNotNone(spine)
        self.assertEqual(
            spine.get("vertebrae"), ["Spine02", "Spine01", "Spine"]
        )

    def test_arms_identified(self):
        systems = _classify_bones(self.MESHY_BONES)
        left_arm = next(
            (s for s in systems if s.get("type") == "arm" and s.get("side") == "L"), None
        )
        self.assertIsNotNone(left_arm)
        self.assertEqual(left_arm.get("upper_arm"), "LeftArm")
        self.assertEqual(left_arm.get("shoulder"), "LeftShoulder")

    def test_legs_with_toes(self):
        systems = _classify_bones(self.MESHY_BONES)
        legs = [s for s in systems if s.get("type") == "leg"]
        self.assertEqual(len(legs), 2)
        for leg in legs:
            self.assertIsNotNone(leg.get("toe"), f"Leg {leg.get('side')} missing toe")

    def test_head_uses_lowercase_neck(self):
        """The lowercase 'neck' and capitalized 'Head' resolve to the head system."""
        systems = _classify_bones(self.MESHY_BONES)
        head = next((s for s in systems if s.get("type") == "head"), None)
        self.assertIsNotNone(head)
        self.assertEqual(head.get("head"), "Head")
        self.assertEqual(head.get("neck"), "neck")

    def test_head_helper_bones_excluded(self):
        """Leaf/helper bones head_end and headfront must not enter any system."""
        systems = _classify_bones(self.MESHY_BONES)
        for system in systems:
            for value in system.values():
                values = value if isinstance(value, list) else [value]
                for bone in values:
                    if isinstance(bone, str):
                        self.assertNotIn(bone, ("head_end", "headfront"))

    def test_no_finger_systems(self):
        systems = _classify_bones(self.MESHY_BONES)
        self.assertEqual([s for s in systems if s.get("type") == "finger"], [])

    def test_no_hallucinated_bone_names(self):
        bone_set = set(self.MESHY_BONES)
        systems = _classify_bones(self.MESHY_BONES)
        for system in systems:
            for key, value in system.items():
                if key in ("type", "side", "name", "parent"):
                    continue
                values = value if isinstance(value, list) else [value]
                for bone in values:
                    if isinstance(bone, str):
                        self.assertIn(
                            bone, bone_set, f"Hallucinated bone {bone!r} in {key!r}"
                        )

if __name__ == "__main__":
    unittest.main()
