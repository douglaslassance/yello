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
from types import SimpleNamespace
from unittest import mock

from yello_ext import rigging


def _http_error(code: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "http://localhost:11434/api/chat", code, "error", {}, io.BytesIO(body)
    )


class TestParseBonePairs(unittest.TestCase):
    """rigging._parse_bone_pairs: validation of raw match responses."""

    def test_valid_pairs_resolved(self):
        data = {
            "pairs": [
                {"source": "Chest_Control", "target": "Torso_Control"},
                {"source": "Pelvis_Control", "target": "Pelvis_Control"},
            ]
        }
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
        pairs = rigging._parse_bone_pairs(data, ["Chest_Control"], ["Torso_Control"])
        self.assertEqual(pairs, [("Chest_Control", "Torso_Control")])

    def test_hallucinated_names_dropped(self):
        """Pairs referencing bones absent from the input lists are discarded."""
        data = {
            "pairs": [
                {"source": "Chest_Control", "target": "MadeUp_Control"},
                {"source": "Ghost_Control", "target": "Torso_Control"},
                {"source": "Chest_Control", "target": "Torso_Control"},
            ]
        }
        pairs = rigging._parse_bone_pairs(data, ["Chest_Control"], ["Torso_Control"])
        self.assertEqual(pairs, [("Chest_Control", "Torso_Control")])

    def test_malformed_entries_skipped(self):
        data = {
            "pairs": [
                "not-a-dict",
                {"source": "Chest_Control"},
                {"target": "Torso_Control"},
                {"source": 5, "target": "Torso_Control"},
                {"source": "Chest_Control", "target": "Torso_Control"},
            ]
        }
        pairs = rigging._parse_bone_pairs(data, ["Chest_Control"], ["Torso_Control"])
        self.assertEqual(pairs, [("Chest_Control", "Torso_Control")])

    def test_no_pairs_returns_none(self):
        self.assertIsNone(rigging._parse_bone_pairs({}, ["A"], ["B"]))
        self.assertIsNone(rigging._parse_bone_pairs({"pairs": []}, ["A"], ["B"]))


class TestMatchBones(unittest.TestCase):
    """rigging.match_bones: control filtering, messaging, and error handling."""

    def test_returns_pairs_and_message(self):
        response = json.dumps(
            {
                "pairs": [
                    {"source": "Hand_Control.L", "target": "Hand_Control.L"},
                ]
            }
        )
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
        response = json.dumps(
            {
                "pairs": [
                    {"source": "Root", "target": "Root"},
                    {"source": "Hand_Control.L", "target": "Hand_Control.L"},
                ]
            }
        )
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
        data = {
            "systems": [
                {"type": "spine", "pelvis": "Hips", "vertebrae": ["Spine", "Spine1"]},
            ]
        }
        systems = rigging._parse_systems(data, ["Hips", "Spine", "Spine1"])
        self.assertEqual(
            systems,
            [
                {"type": "spine", "pelvis": "Hips", "vertebrae": ["Spine", "Spine1"]},
            ],
        )

    def test_case_insensitive_resolution(self):
        data = {"systems": [{"type": "spine", "pelvis": "hips", "vertebrae": []}]}
        systems = rigging._parse_systems(data, ["Hips"])
        self.assertEqual(systems[0]["pelvis"], "Hips")

    def test_arm_requires_full_chain(self):
        """An arm missing upper_arm, forearm, or hand is dropped entirely."""
        data = {
            "systems": [
                {
                    "type": "arm",
                    "side": "L",
                    "upper_arm": "LeftArm",
                    "forearm": "LeftForeArm",
                },
            ]
        }
        self.assertIsNone(rigging._parse_systems(data, ["LeftArm", "LeftForeArm"]))

    def test_arm_full_with_defaults_and_shoulder(self):
        data = {
            "systems": [
                {
                    "type": "arm",
                    "upper_arm": "LeftArm",
                    "forearm": "LeftForeArm",
                    "hand": "LeftHand",
                    "shoulder": "LeftShoulder",
                },
            ]
        }
        systems = rigging._parse_systems(
            data, ["LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand"]
        )
        arm = systems[0]
        self.assertEqual(arm["side"], "L")  # defaults to L when absent
        self.assertEqual(arm["shoulder"], "LeftShoulder")
        self.assertEqual(arm["upper_arm"], "LeftArm")

    def test_leg_toe_optional(self):
        data = {
            "systems": [
                {
                    "type": "leg",
                    "side": "R",
                    "upper_leg": "RightUpLeg",
                    "lower_leg": "RightLeg",
                    "foot": "RightFoot",
                },
            ]
        }
        systems = rigging._parse_systems(data, ["RightUpLeg", "RightLeg", "RightFoot"])
        self.assertEqual(systems[0]["side"], "R")
        self.assertIsNone(systems[0]["toe"])

    def test_head_requires_head(self):
        data = {"systems": [{"type": "head", "neck": "Neck"}]}
        self.assertIsNone(rigging._parse_systems(data, ["Neck"]))

    def test_finger_name_lowercased(self):
        data = {
            "systems": [
                {
                    "type": "finger",
                    "name": "Index",
                    "side": "L",
                    "chain": ["LeftHandIndex1", "LeftHandIndex2"],
                },
            ]
        }
        systems = rigging._parse_systems(data, ["LeftHandIndex1", "LeftHandIndex2"])
        self.assertEqual(systems[0]["name"], "index")
        self.assertEqual(systems[0]["chain"], ["LeftHandIndex1", "LeftHandIndex2"])

    def test_hallucinated_bones_filtered(self):
        """Bone names not in the input list are stripped from chains and slots."""
        data = {
            "systems": [
                {"type": "spine", "pelvis": "Ghost", "vertebrae": ["Spine", "Phantom"]},
            ]
        }
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
        data = {
            "systems": [
                {"spine": {"pelvis": "Hips", "vertebrae": ["Spine", "Spine1"]}},
            ]
        }
        systems = rigging._parse_systems(data, ["Hips", "Spine", "Spine1"])
        self.assertEqual(
            systems,
            [
                {"type": "spine", "pelvis": "Hips", "vertebrae": ["Spine", "Spine1"]},
            ],
        )

    def test_list_for_single_value_field_takes_first_resolved(self):
        """A list handed to a single-value slot resolves to its first valid bone."""
        data = {
            "systems": [
                {
                    "type": "head",
                    "neck": ["neck_01", "neck_02"],
                    "head": ["Head", "head_end", "headfront"],
                },
            ]
        }
        systems = rigging._parse_systems(
            data, ["neck_01", "neck_02", "Head", "head_end", "headfront"]
        )
        self.assertEqual(systems[0]["head"], "Head")
        self.assertEqual(systems[0]["neck"], "neck_01")


class TestClassifyBones(unittest.TestCase):
    """rigging.classify_bones: summary messaging and error handling."""

    def test_returns_systems_and_summary(self):
        response = json.dumps(
            {
                "systems": [
                    {
                        "type": "leg",
                        "side": "L",
                        "upper_leg": "LeftUpLeg",
                        "lower_leg": "LeftLeg",
                        "foot": "LeftFoot",
                        "toe": "LeftToeBase",
                    },
                ]
            }
        )
        bones = ["LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase"]
        with mock.patch.object(rigging.ollama, "chat", return_value=response):
            systems, message, raw = rigging.classify_bones(bones)
        self.assertEqual(len(systems), 1)
        self.assertIn("Identified", message)
        self.assertIn("toe=yes", message)

    def test_leg_without_toe_flagged_in_summary(self):
        response = json.dumps(
            {
                "systems": [
                    {
                        "type": "leg",
                        "side": "R",
                        "upper_leg": "RightUpLeg",
                        "lower_leg": "RightLeg",
                        "foot": "RightFoot",
                    },
                ]
            }
        )
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
        with mock.patch.object(rigging.ollama, "chat", side_effect=ValueError("nope")):
            systems, message, _ = rigging.classify_bones(["Head"])
        self.assertIsNone(systems)
        self.assertIn("Ollama error", message)


class TestFormatHierarchy(unittest.TestCase):
    """rigging._format_hierarchy: rendering the bone tree for the prompt."""

    def test_indented_tree(self):
        parents = {
            "Hips": None,
            "Spine02": "Hips",
            "Spine01": "Spine02",
            "Spine": "Spine01",
        }
        text = rigging._format_hierarchy(
            ["Hips", "Spine02", "Spine01", "Spine"], parents
        )
        self.assertEqual(text, "- Hips\n  - Spine02\n    - Spine01\n      - Spine")

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


class TestClassifySkeleton(unittest.TestCase):
    """rigging.classify_skeleton: reading names and parents off the armature."""

    def test_parents_read_from_armature(self):
        hips = SimpleNamespace(name="Hips", parent=None)
        spine02 = SimpleNamespace(name="Spine02", parent=hips)
        spine01 = SimpleNamespace(name="Spine01", parent=spine02)
        spine = SimpleNamespace(name="Spine", parent=spine01)
        skeleton = SimpleNamespace(
            data=SimpleNamespace(bones=[hips, spine02, spine01, spine])
        )
        with mock.patch.object(
            rigging, "classify_bones", return_value=(None, "", "")
        ) as classify_bones:
            rigging.classify_skeleton(skeleton)
        classify_bones.assert_called_once_with(
            ["Hips", "Spine02", "Spine01", "Spine"],
            {"Hips": None, "Spine02": "Hips", "Spine01": "Spine02", "Spine": "Spine01"},
        )


class TestExtractBoneNames(unittest.TestCase):
    """rigging.extract_bone_names: flattening systems to deform bone names."""

    def test_collects_names_across_system_types(self):
        systems = [
            {"type": "spine", "pelvis": "Hips", "vertebrae": ["Spine", "Spine1"]},
            {
                "type": "arm",
                "side": "L",
                "shoulder": "LeftShoulder",
                "upper_arm": "LeftArm",
                "forearm": "LeftForeArm",
                "hand": "LeftHand",
            },
            {
                "type": "leg",
                "side": "R",
                "upper_leg": "RightUpLeg",
                "lower_leg": "RightLeg",
                "foot": "RightFoot",
                "toe": None,
            },
            {"type": "head", "neck": "Neck", "head": "Head"},
            {
                "type": "finger",
                "name": "index",
                "side": "L",
                "chain": ["LeftHandIndex1", "LeftHandIndex2"],
            },
        ]
        names = rigging.extract_bone_names(systems)
        self.assertEqual(
            names,
            {
                "Hips",
                "Spine",
                "Spine1",
                "LeftShoulder",
                "LeftArm",
                "LeftForeArm",
                "LeftHand",
                "RightUpLeg",
                "RightLeg",
                "RightFoot",
                "Neck",
                "Head",
                "LeftHandIndex1",
                "LeftHandIndex2",
            },
        )
        self.assertNotIn(None, names)


class TestPairChains(unittest.TestCase):
    """rigging._pair_chains: pairing bone chains of different lengths."""

    def test_equal_lengths_pair_in_order(self):
        pairs = rigging._pair_chains(["A", "B"], ["1", "2"])
        self.assertEqual(pairs, [("A", "1"), ("B", "2")])

    def test_shorter_source_spreads_over_target(self):
        pairs = rigging._pair_chains(["A", "B", "C"], ["1", "2", "3", "4", "5"])
        self.assertEqual(pairs, [("A", "1"), ("B", "3"), ("C", "5")])

    def test_longer_source_keeps_both_ends(self):
        pairs = rigging._pair_chains(["A", "B", "C", "D", "E"], ["1", "2"])
        self.assertEqual(pairs, [("A", "1"), ("E", "2")])

    def test_single_bone_pairs_with_first(self):
        self.assertEqual(rigging._pair_chains(["A"], ["1", "2", "3"]), [("A", "1")])

    def test_empty_chain_pairs_nothing(self):
        self.assertEqual(rigging._pair_chains([], ["1"]), [])


SOURCE_SYSTEMS = [
    {"type": "spine", "pelvis": "Hips", "vertebrae": ["Spine", "Spine1", "Spine2"]},
    {
        "type": "arm",
        "side": "L",
        "shoulder": "LeftShoulder",
        "upper_arm": "LeftArm",
        "forearm": "LeftForeArm",
        "hand": "LeftHand",
    },
    {
        "type": "leg",
        "side": "R",
        "upper_leg": "RightUpLeg",
        "lower_leg": "RightLeg",
        "foot": "RightFoot",
        "toe": "RightToeBase",
    },
    {"type": "head", "neck": "Neck", "head": "Head"},
    {"type": "finger", "name": "index", "side": "L", "chain": ["LeftIndex1"]},
]


class TestDeformBindings(unittest.TestCase):
    """rigging.deform_bindings: pairing deform bones by role across skeletons."""

    def test_bones_paired_by_role_and_side(self):
        target_systems = [
            {
                "type": "spine",
                "pelvis": "pelvis",
                "vertebrae": [f"spine_0{index}" for index in range(1, 6)],
            },
            {
                "type": "arm",
                "side": "L",
                "shoulder": "clavicle_l",
                "upper_arm": "upperarm_l",
                "forearm": "lowerarm_l",
                "hand": "hand_l",
            },
            {
                "type": "leg",
                "side": "R",
                "upper_leg": "thigh_r",
                "lower_leg": "calf_r",
                "foot": "foot_r",
                "toe": None,
            },
            {"type": "head", "neck": "neck_01", "head": "head"},
        ]
        bindings = rigging.deform_bindings(SOURCE_SYSTEMS, target_systems)
        self.assertEqual(
            [(binding.source_bone, binding.target_bone) for binding in bindings],
            [
                ("Hips", "pelvis"),
                ("Spine", "spine_01"),
                ("Spine1", "spine_03"),
                ("Spine2", "spine_05"),
                ("LeftShoulder", "clavicle_l"),
                ("LeftArm", "upperarm_l"),
                ("LeftForeArm", "lowerarm_l"),
                ("LeftHand", "hand_l"),
                ("RightUpLeg", "thigh_r"),
                ("RightLeg", "calf_r"),
                ("RightFoot", "foot_r"),
                ("Neck", "neck_01"),
                ("Head", "head"),
            ],
        )
        self.assertEqual(
            [binding.target_bone for binding in bindings if binding.location],
            ["pelvis"],
        )

    def test_other_side_is_not_paired(self):
        target_systems = [
            {
                "type": "arm",
                "side": "R",
                "upper_arm": "upperarm_r",
                "forearm": "lowerarm_r",
                "hand": "hand_r",
            }
        ]
        self.assertEqual(rigging.deform_bindings(SOURCE_SYSTEMS, target_systems), [])


class TestControlBindings(unittest.TestCase):
    """rigging.control_bindings: pairing control rig controls with source bones."""

    def test_controls_bound_to_their_source_bones(self):
        bindings = {
            binding.target_bone: binding
            for binding in rigging.control_bindings(SOURCE_SYSTEMS)
        }
        self.assertEqual(bindings["Hips_Control"].source_bone, "Hips")
        self.assertTrue(bindings["Hips_Control"].location)
        self.assertEqual(bindings["Chest_Control"].source_bone, "Spine2")
        self.assertEqual(bindings["UpperArm_Control.L"].source_bone, "LeftArm")
        self.assertEqual(bindings["IK_Target_Control.R"].source_bone, "RightFoot")
        self.assertTrue(bindings["IK_Target_Control.R"].location)
        self.assertEqual(bindings["Index.001_Control.L"].source_bone, "LeftIndex1")
        self.assertFalse(bindings["Head_Control"].location)


class TestRetargetBindings(unittest.TestCase):
    """rigging.retarget_bindings: controls when rigged, deform bones otherwise."""

    @staticmethod
    def _armature(*bone_names):
        bones = [SimpleNamespace(name=name) for name in bone_names]
        return SimpleNamespace(data=SimpleNamespace(bones=bones))

    def test_control_rig_targets_controls(self):
        target = self._armature("pelvis", "Hips_Control")
        bindings = rigging.retarget_bindings(target, SOURCE_SYSTEMS, None)
        self.assertIn("Hips_Control", [binding.target_bone for binding in bindings])

    def test_plain_armature_targets_deform_bones(self):
        target = self._armature("pelvis")
        target_systems = [{"type": "spine", "pelvis": "pelvis", "vertebrae": []}]
        bindings = rigging.retarget_bindings(target, SOURCE_SYSTEMS, target_systems)
        self.assertEqual(
            [(binding.source_bone, binding.target_bone) for binding in bindings],
            [("Hips", "pelvis")],
        )


if __name__ == "__main__":
    unittest.main()
