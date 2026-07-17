"""Offline unit tests for the LLM bone mapping and classification logic.

These tests exercise the deterministic post-processing that turns a raw Ollama
JSON response into validated rig systems and bone pairs. They do not require
Ollama or Blender: the Blender modules are stubbed by conftest.py and the
Ollama transport (rigging.ollama.chat) is mocked.

Run with: python -m pytest tests/test_bone_mapping.py -v
"""

import io
import json
import unittest
import urllib.error
from unittest import mock

from yello_ext import rigging


def _http_error(code: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "http://localhost:11434/api/chat", code, "error", {}, io.BytesIO(body)
    )


class TestParseBonePairs(unittest.TestCase):
    """rigging._parse_bone_pairs: validation of raw match responses."""

    def test_valid_pairs_resolved(self):
        data = {"pairs": [
            {"source": "Chest_Control", "target": "Torso_Control"},
            {"source": "Pelvis_Control", "target": "Pelvis_Control"},
        ]}
        pairs = rigging._parse_bone_pairs(
            data,
            ["Chest_Control", "Pelvis_Control"],
            ["Torso_Control", "Pelvis_Control"],
        )
        self.assertEqual(
            pairs,
            [("Chest_Control", "Torso_Control"), ("Pelvis_Control", "Pelvis_Control")],
        )

    def test_case_insensitive_and_whitespace_resolution(self):
        """Names are resolved to the canonical casing from the input lists."""
        data = {"pairs": [{"source": "  chest_control ", "target": "TORSO_CONTROL"}]}
        pairs = rigging._parse_bone_pairs(
            data, ["Chest_Control"], ["Torso_Control"]
        )
        self.assertEqual(pairs, [("Chest_Control", "Torso_Control")])

    def test_hallucinated_names_dropped(self):
        """Pairs referencing bones absent from the input lists are discarded."""
        data = {"pairs": [
            {"source": "Chest_Control", "target": "MadeUp_Control"},
            {"source": "Ghost_Control", "target": "Torso_Control"},
            {"source": "Chest_Control", "target": "Torso_Control"},
        ]}
        pairs = rigging._parse_bone_pairs(
            data, ["Chest_Control"], ["Torso_Control"]
        )
        self.assertEqual(pairs, [("Chest_Control", "Torso_Control")])

    def test_malformed_entries_skipped(self):
        data = {"pairs": [
            "not-a-dict",
            {"source": "Chest_Control"},
            {"target": "Torso_Control"},
            {"source": 5, "target": "Torso_Control"},
            {"source": "Chest_Control", "target": "Torso_Control"},
        ]}
        pairs = rigging._parse_bone_pairs(
            data, ["Chest_Control"], ["Torso_Control"]
        )
        self.assertEqual(pairs, [("Chest_Control", "Torso_Control")])

    def test_no_pairs_returns_none(self):
        self.assertIsNone(rigging._parse_bone_pairs({}, ["A"], ["B"]))
        self.assertIsNone(rigging._parse_bone_pairs({"pairs": []}, ["A"], ["B"]))


class TestMatchBones(unittest.TestCase):
    """rigging.match_bones: control filtering, messaging, and error handling."""

    def test_returns_pairs_and_message(self):
        response = json.dumps({"pairs": [
            {"source": "Hand_Control.L", "target": "Hand_Control.L"},
        ]})
        with mock.patch.object(rigging.ollama, "chat", return_value=response):
            pairs, message, raw = rigging.match_bones(
                ["Hand_Control.L"], ["Hand_Control.L"]
            )
        self.assertEqual(pairs, [("Hand_Control.L", "Hand_Control.L")])
        self.assertIn("Matched 1 bone pairs", message)
        self.assertEqual(raw, response)

    def test_only_control_bones_are_matched(self):
        """When control bones are present, non-control bones are filtered out.

        The response maps a non-control bone (Root) that exists in the full
        input but not in the control-only subset, so it must be dropped.
        """
        response = json.dumps({"pairs": [
            {"source": "Root", "target": "Root"},
            {"source": "Hand_Control.L", "target": "Hand_Control.L"},
        ]})
        with mock.patch.object(rigging.ollama, "chat", return_value=response):
            pairs, _, _ = rigging.match_bones(
                ["Root", "Hand_Control.L"], ["Root", "Hand_Control.L"]
            )
        self.assertEqual(pairs, [("Hand_Control.L", "Hand_Control.L")])

    def test_unparseable_response_returns_none(self):
        with mock.patch.object(rigging.ollama, "chat", return_value="{}"):
            pairs, message, raw = rigging.match_bones(["A_Control"], ["A_Control"])
        self.assertIsNone(pairs)
        self.assertIn("Could not parse", message)

    def test_http_error_is_reported(self):
        with mock.patch.object(
            rigging.ollama, "chat", side_effect=_http_error(500, b"boom")
        ):
            pairs, message, raw = rigging.match_bones(["A_Control"], ["A_Control"])
        self.assertIsNone(pairs)
        self.assertIn("Ollama HTTP 500", message)
        self.assertEqual(raw, "")

    def test_generic_error_is_reported(self):
        with mock.patch.object(
            rigging.ollama, "chat", side_effect=RuntimeError("offline")
        ):
            pairs, message, raw = rigging.match_bones(["A_Control"], ["A_Control"])
        self.assertIsNone(pairs)
        self.assertIn("Ollama error", message)
        self.assertIn("offline", message)


class TestParseSystems(unittest.TestCase):
    """rigging._parse_systems: validation of raw classification responses."""

    def test_spine_pelvis_and_vertebrae(self):
        data = {"systems": [
            {"type": "spine", "pelvis": "Hips", "vertebrae": ["Spine", "Spine1"]},
        ]}
        systems = rigging._parse_systems(data, ["Hips", "Spine", "Spine1"])
        self.assertEqual(systems, [
            {"type": "spine", "pelvis": "Hips", "vertebrae": ["Spine", "Spine1"]},
        ])

    def test_case_insensitive_resolution(self):
        data = {"systems": [{"type": "spine", "pelvis": "hips", "vertebrae": []}]}
        systems = rigging._parse_systems(data, ["Hips"])
        self.assertEqual(systems[0]["pelvis"], "Hips")

    def test_arm_requires_full_chain(self):
        """An arm missing upper_arm, forearm, or hand is dropped entirely."""
        data = {"systems": [
            {"type": "arm", "side": "L", "upper_arm": "LeftArm",
             "forearm": "LeftForeArm"},
        ]}
        self.assertIsNone(
            rigging._parse_systems(data, ["LeftArm", "LeftForeArm"])
        )

    def test_arm_full_with_defaults_and_shoulder(self):
        data = {"systems": [
            {"type": "arm", "upper_arm": "LeftArm", "forearm": "LeftForeArm",
             "hand": "LeftHand", "shoulder": "LeftShoulder"},
        ]}
        systems = rigging._parse_systems(
            data, ["LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand"]
        )
        arm = systems[0]
        self.assertEqual(arm["side"], "L")  # defaults to L when absent
        self.assertEqual(arm["shoulder"], "LeftShoulder")
        self.assertEqual(arm["upper_arm"], "LeftArm")

    def test_leg_toe_optional(self):
        data = {"systems": [
            {"type": "leg", "side": "R", "upper_leg": "RightUpLeg",
             "lower_leg": "RightLeg", "foot": "RightFoot"},
        ]}
        systems = rigging._parse_systems(
            data, ["RightUpLeg", "RightLeg", "RightFoot"]
        )
        self.assertEqual(systems[0]["side"], "R")
        self.assertIsNone(systems[0]["toe"])

    def test_head_requires_head(self):
        data = {"systems": [{"type": "head", "neck": "Neck"}]}
        self.assertIsNone(rigging._parse_systems(data, ["Neck"]))

    def test_finger_name_lowercased(self):
        data = {"systems": [
            {"type": "finger", "name": "Index", "side": "L",
             "chain": ["LeftHandIndex1", "LeftHandIndex2"]},
        ]}
        systems = rigging._parse_systems(
            data, ["LeftHandIndex1", "LeftHandIndex2"]
        )
        self.assertEqual(systems[0]["name"], "index")
        self.assertEqual(systems[0]["chain"], ["LeftHandIndex1", "LeftHandIndex2"])

    def test_hallucinated_bones_filtered(self):
        """Bone names not in the input list are stripped from chains and slots."""
        data = {"systems": [
            {"type": "spine", "pelvis": "Ghost", "vertebrae": ["Spine", "Phantom"]},
        ]}
        systems = rigging._parse_systems(data, ["Spine"])
        self.assertIsNone(systems[0]["pelvis"])
        self.assertEqual(systems[0]["vertebrae"], ["Spine"])

    def test_non_dict_entries_skipped(self):
        data = {"systems": ["junk", 42, {"type": "head", "head": "Head"}]}
        systems = rigging._parse_systems(data, ["Head"])
        self.assertEqual(len(systems), 1)
        self.assertEqual(systems[0]["type"], "head")

    def test_empty_returns_none(self):
        self.assertIsNone(rigging._parse_systems({}, ["Head"]))
        self.assertIsNone(rigging._parse_systems({"systems": []}, ["Head"]))

    def test_type_keyed_entry_is_normalized(self):
        """Entries shaped as {"spine": {...}} are flattened instead of dropped."""
        data = {"systems": [
            {"spine": {"pelvis": "Hips", "vertebrae": ["Spine", "Spine1"]}},
        ]}
        systems = rigging._parse_systems(data, ["Hips", "Spine", "Spine1"])
        self.assertEqual(systems, [
            {"type": "spine", "pelvis": "Hips", "vertebrae": ["Spine", "Spine1"]},
        ])

    def test_list_for_single_value_field_takes_first_resolved(self):
        """A list handed to a single-value slot resolves to its first valid bone."""
        data = {"systems": [
            {"type": "head", "neck": ["neck_01", "neck_02"],
             "head": ["Head", "head_end", "headfront"]},
        ]}
        systems = rigging._parse_systems(
            data, ["neck_01", "neck_02", "Head", "head_end", "headfront"]
        )
        self.assertEqual(systems[0]["head"], "Head")
        self.assertEqual(systems[0]["neck"], "neck_01")


class TestClassifyBones(unittest.TestCase):
    """rigging.classify_bones: summary messaging and error handling."""

    def test_returns_systems_and_summary(self):
        response = json.dumps({"systems": [
            {"type": "leg", "side": "L", "upper_leg": "LeftUpLeg",
             "lower_leg": "LeftLeg", "foot": "LeftFoot", "toe": "LeftToeBase"},
        ]})
        bones = ["LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase"]
        with mock.patch.object(rigging.ollama, "chat", return_value=response):
            systems, message, raw = rigging.classify_bones(bones)
        self.assertEqual(len(systems), 1)
        self.assertIn("Identified", message)
        self.assertIn("toe=yes", message)

    def test_leg_without_toe_flagged_in_summary(self):
        response = json.dumps({"systems": [
            {"type": "leg", "side": "R", "upper_leg": "RightUpLeg",
             "lower_leg": "RightLeg", "foot": "RightFoot"},
        ]})
        bones = ["RightUpLeg", "RightLeg", "RightFoot"]
        with mock.patch.object(rigging.ollama, "chat", return_value=response):
            _, message, _ = rigging.classify_bones(bones)
        self.assertIn("toe=NO", message)

    def test_unparseable_response_returns_none(self):
        with mock.patch.object(rigging.ollama, "chat", return_value="{}"):
            systems, message, _ = rigging.classify_bones(["Head"])
        self.assertIsNone(systems)
        self.assertIn("Could not parse", message)

    def test_http_error_is_reported(self):
        with mock.patch.object(
            rigging.ollama, "chat", side_effect=_http_error(404, b"missing")
        ):
            systems, message, raw = rigging.classify_bones(["Head"])
        self.assertIsNone(systems)
        self.assertIn("Ollama HTTP 404", message)
        self.assertEqual(raw, "")

    def test_generic_error_is_reported(self):
        with mock.patch.object(
            rigging.ollama, "chat", side_effect=ValueError("nope")
        ):
            systems, message, _ = rigging.classify_bones(["Head"])
        self.assertIsNone(systems)
        self.assertIn("Ollama error", message)


class TestFormatHierarchy(unittest.TestCase):
    """rigging._format_hierarchy: rendering the bone tree for the prompt."""

    def test_indented_tree(self):
        parents = {
            "Hips": None, "Spine02": "Hips", "Spine01": "Spine02", "Spine": "Spine01",
        }
        text = rigging._format_hierarchy(
            ["Hips", "Spine02", "Spine01", "Spine"], parents
        )
        self.assertEqual(
            text, "- Hips\n  - Spine02\n    - Spine01\n      - Spine"
        )

    def test_orphan_parent_treated_as_root(self):
        """A parent that is not itself in the bone list starts a new root."""
        text = rigging._format_hierarchy(["A", "B"], {"A": "Missing", "B": "A"})
        self.assertEqual(text, "- A\n  - B")


class TestClassifyBonesHierarchy(unittest.TestCase):
    """classify_bones threads the hierarchy into the prompt when given parents."""

    def _capture_user_prompt(self, *args):
        captured = {}

        def fake_chat(messages, *rest, **kwargs):
            captured["user"] = messages[-1]["content"]
            return "{}"

        with mock.patch.object(rigging.ollama, "chat", side_effect=fake_chat):
            rigging.classify_bones(*args)
        return captured["user"]

    def test_hierarchy_rendered_when_parents_given(self):
        prompt = self._capture_user_prompt(
            ["Hips", "Spine"], {"Hips": None, "Spine": "Hips"}
        )
        self.assertIn("- Hips", prompt)
        self.assertIn("  - Spine", prompt)

    def test_absent_marker_when_no_parents(self):
        prompt = self._capture_user_prompt(["Hips"])
        self.assertIn("(not provided)", prompt)


class TestExtractBoneNames(unittest.TestCase):
    """rigging.extract_bone_names: flattening systems to deform bone names."""

    def test_collects_names_across_system_types(self):
        systems = [
            {"type": "spine", "pelvis": "Hips", "vertebrae": ["Spine", "Spine1"]},
            {"type": "arm", "side": "L", "shoulder": "LeftShoulder",
             "upper_arm": "LeftArm", "forearm": "LeftForeArm", "hand": "LeftHand"},
            {"type": "leg", "side": "R", "upper_leg": "RightUpLeg",
             "lower_leg": "RightLeg", "foot": "RightFoot", "toe": None},
            {"type": "head", "neck": "Neck", "head": "Head"},
            {"type": "finger", "name": "index", "side": "L",
             "chain": ["LeftHandIndex1", "LeftHandIndex2"]},
        ]
        names = rigging.extract_bone_names(systems)
        self.assertEqual(
            names,
            {
                "Hips", "Spine", "Spine1",
                "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
                "RightUpLeg", "RightLeg", "RightFoot",
                "Neck", "Head",
                "LeftHandIndex1", "LeftHandIndex2",
            },
        )
        self.assertNotIn(None, names)


if __name__ == "__main__":
    unittest.main()
