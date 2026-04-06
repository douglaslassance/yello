"""Tests for Ollama prompt correctness.

Run with: python -m pytest tests/test_prompts.py -v
Requires Ollama to be running locally with codestral:latest.
"""

import json
import unittest
import urllib.request
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
OLLAMA_URL = "http://localhost:11434"
MODEL = "codestral:latest"


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
    with urllib.request.urlopen(req, timeout=120) as response:
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


def _classify_bones(bones: list[str]) -> list[dict]:
    """Call classify_bones prompts and return systems list."""
    system = _load_prompt("classify_bones_system.md")
    bone_list = "\n".join(f"  - {n}" for n in sorted(bones))
    user = _load_prompt("classify_bones_user.md").replace("{bone_list}", bone_list)
    data = _chat(system, user)
    return data.get("systems", [])


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
        types = [s["type"] for s in systems]
        self.assertIn("spine", types)

    def test_spine_pelvis_is_hips(self):
        """Hips bone must be classified as pelvis, not as a vertebra."""
        systems = _classify_bones(self.MIXAMO_BONES)
        spine = next((s for s in systems if s["type"] == "spine"), None)
        self.assertIsNotNone(spine)
        self.assertEqual(spine.get("pelvis"), "Hips")
        self.assertNotIn("Hips", spine.get("vertebrae", []))

    def test_arms_identified(self):
        systems = _classify_bones(self.MIXAMO_BONES)
        arm_sides = {s["side"] for s in systems if s["type"] == "arm"}
        self.assertIn("L", arm_sides)
        self.assertIn("R", arm_sides)

    def test_legs_with_toes(self):
        systems = _classify_bones(self.MIXAMO_BONES)
        legs = [s for s in systems if s["type"] == "leg"]
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
        left_arm = next((s for s in systems if s["type"] == "arm" and s.get("side") == "L"), None)
        self.assertIsNotNone(left_arm)
        self.assertEqual(left_arm.get("upper_arm"), "LeftArm")
        self.assertNotEqual(left_arm.get("shoulder"), "LeftArm")


if __name__ == "__main__":
    unittest.main()
