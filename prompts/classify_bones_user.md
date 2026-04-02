Bone names:
{bone_list}

Return ONLY a JSON object with a "systems" array.
All bone name values must be copied VERBATIM from the list above.

---

SYSTEMS

Each entry in "systems" has a "type" and type-specific fields.
A character may have any number of each system type (e.g. multiple arms, multiple legs).

spine
  Required: vertebrae — ordered list of bones from pelvis to chest, low to high. Do NOT include neck or head.
  Optional: pelvis — the root hip bone that sits below the spine.

arm
  Required: upper_arm, forearm, hand
  Optional: shoulder, fingers (object mapping finger name to ordered chain of bones, knuckle to tip)
  Also: side (e.g. "L", "R", "L2"), parent (name of the deform bone this arm attaches to)

leg
  Required: upper_leg, lower_leg, foot
  Optional: toe
  Also: side (e.g. "L", "R"), parent (name of the deform bone this leg attaches to)

head
  Required: head
  Optional: neck
  Also: parent (name of the deform bone this head attaches to)

---

SYNONYMS

pelvis     = pelvis, hips, hip. NOTE: a bone named "Hips" or "Hip" is the pelvis — map it here, not in vertebrae.
upper_arm  = upper arm, arm, humerus. NOTE: a bone simply called "Arm" is the upper arm.
forearm    = forearm, lower arm, fore arm
shoulder   = shoulder, clavicle, collar, collarbone
upper_leg  = upper leg, thigh, femur
lower_leg  = lower leg, shin, calf
foot       = foot, ankle
toe        = toe, ball, toebase, toe base
vertebrae  = spine, back, torso bones between pelvis and neck

---

SCHEMA

{
  "systems": [
    {
      "type": "spine",
      "pelvis": "<bone name or null>",
      "vertebrae": ["<bone1>", "<bone2>", "..."]
    },
    {
      "type": "arm",
      "side": "<L or R>",
      "parent": "<deform bone this arm attaches to>",
      "shoulder": "<bone name or null>",
      "upper_arm": "<bone name>",
      "forearm": "<bone name>",
      "hand": "<bone name>",
      "fingers": {
        "thumb":  ["<b1>", "<b2>", "..."],
        "index":  ["<b1>", "<b2>", "..."],
        "middle": ["<b1>", "<b2>", "..."],
        "ring":   ["<b1>", "<b2>", "..."],
        "pinky":  ["<b1>", "<b2>", "..."]
      }
    },
    {
      "type": "leg",
      "side": "<L or R>",
      "parent": "<deform bone this leg attaches to>",
      "upper_leg": "<bone name>",
      "lower_leg": "<bone name>",
      "foot": "<bone name>",
      "toe": "<bone name or null>"
    },
    {
      "type": "head",
      "parent": "<deform bone this head attaches to>",
      "neck": "<bone name or null>",
      "head": "<bone name>"
    }
  ]
}

---

EXAMPLE (Mixamo-style rig)

{
  "systems": [
    {
      "type": "spine",
      "pelvis": "Hips",
      "vertebrae": ["Spine", "Spine1", "Spine2"]
    },
    {
      "type": "arm",
      "side": "L",
      "parent": "Spine2",
      "shoulder": "LeftShoulder",
      "upper_arm": "LeftArm",
      "forearm": "LeftForeArm",
      "hand": "LeftHand",
      "fingers": {
        "thumb": ["LeftHandThumb1", "LeftHandThumb2", "LeftHandThumb3"],
        "index": ["LeftHandIndex1", "LeftHandIndex2", "LeftHandIndex3"]
      }
    },
    {
      "type": "arm",
      "side": "R",
      "parent": "Spine2",
      "shoulder": "RightShoulder",
      "upper_arm": "RightArm",
      "forearm": "RightForeArm",
      "hand": "RightHand",
      "fingers": {
        "thumb": ["RightHandThumb1", "RightHandThumb2", "RightHandThumb3"],
        "index": ["RightHandIndex1", "RightHandIndex2", "RightHandIndex3"]
      }
    },
    {
      "type": "leg",
      "side": "L",
      "parent": "Hips",
      "upper_leg": "LeftUpLeg",
      "lower_leg": "LeftLeg",
      "foot": "LeftFoot",
      "toe": "LeftToeBase"
    },
    {
      "type": "leg",
      "side": "R",
      "parent": "Hips",
      "upper_leg": "RightUpLeg",
      "lower_leg": "RightLeg",
      "foot": "RightFoot",
      "toe": "RightToeBase"
    },
    {
      "type": "head",
      "parent": "Spine2",
      "neck": "Neck",
      "head": "Head"
    }
  ]
}
