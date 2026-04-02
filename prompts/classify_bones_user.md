Bone names:
{bone_list}

Return ONLY a JSON object with a "systems" array.
All bone name values must be copied VERBATIM from the list above.
Always include optional fields explicitly — set them to null when not found, never omit them.

---

SYSTEMS

Each entry in "systems" has a "type" and type-specific fields.
A character may have any number of each system type (e.g. multiple arms, multiple legs, many fingers).

spine
  Required: vertebrae — ordered list of bones from pelvis to chest, low to high. Do NOT include neck or head.
  Optional: pelvis — the root hip bone that sits below the spine.

arm
  Required: upper_arm, forearm, hand
  Optional: shoulder — include the clavicle/collar bone if present, set to null if absent
  Also: side (e.g. "L", "R", "L2"), parent (name of the deform bone this arm attaches to)

leg
  Required: upper_leg, lower_leg, foot
  Optional: toe — set to null if absent
  Also: side (e.g. "L", "R"), parent (name of the deform bone this leg attaches to)

head
  Required: head
  Optional: neck — set to null if absent
  Also: parent (name of the deform bone this head attaches to)

finger
  Required: chain — ordered list of bones from knuckle to fingertip
  Also: name, side, parent (name of the hand bone this finger attaches to)
  Notes on name:
    - Use "thumb", "index", "middle", "ring", or "pinky" when the rig uses standard finger names.
    - If the rig numbers fingers (e.g. finger_1, finger_2) use "finger_1", "finger_2", etc.
    - Create one finger system per finger. A typical hand has 5 fingers.
  IMPORTANT: Output ALL fingers found on ALL hands. Do not skip or omit any finger.

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
      "hand": "<bone name>"
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
    },
    {
      "type": "finger",
      "name": "<thumb | index | middle | ring | pinky | finger_1 | finger_2 | ...>",
      "side": "<L or R>",
      "parent": "<hand bone this finger attaches to>",
      "chain": ["<knuckle>", "<mid>", "<tip>", "..."]
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
      "hand": "LeftHand"
    },
    {
      "type": "arm",
      "side": "R",
      "parent": "Spine2",
      "shoulder": "RightShoulder",
      "upper_arm": "RightArm",
      "forearm": "RightForeArm",
      "hand": "RightHand"
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
    },
    {
      "type": "finger",
      "name": "thumb",
      "side": "L",
      "parent": "LeftHand",
      "chain": ["LeftHandThumb1", "LeftHandThumb2", "LeftHandThumb3"]
    },
    {
      "type": "finger",
      "name": "index",
      "side": "L",
      "parent": "LeftHand",
      "chain": ["LeftHandIndex1", "LeftHandIndex2", "LeftHandIndex3"]
    },
    {
      "type": "finger",
      "name": "middle",
      "side": "L",
      "parent": "LeftHand",
      "chain": ["LeftHandMiddle1", "LeftHandMiddle2", "LeftHandMiddle3"]
    },
    {
      "type": "finger",
      "name": "ring",
      "side": "L",
      "parent": "LeftHand",
      "chain": ["LeftHandRing1", "LeftHandRing2", "LeftHandRing3"]
    },
    {
      "type": "finger",
      "name": "pinky",
      "side": "L",
      "parent": "LeftHand",
      "chain": ["LeftHandPinky1", "LeftHandPinky2", "LeftHandPinky3"]
    },
    {
      "type": "finger",
      "name": "thumb",
      "side": "R",
      "parent": "RightHand",
      "chain": ["RightHandThumb1", "RightHandThumb2", "RightHandThumb3"]
    },
    {
      "type": "finger",
      "name": "index",
      "side": "R",
      "parent": "RightHand",
      "chain": ["RightHandIndex1", "RightHandIndex2", "RightHandIndex3"]
    },
    {
      "type": "finger",
      "name": "middle",
      "side": "R",
      "parent": "RightHand",
      "chain": ["RightHandMiddle1", "RightHandMiddle2", "RightHandMiddle3"]
    },
    {
      "type": "finger",
      "name": "ring",
      "side": "R",
      "parent": "RightHand",
      "chain": ["RightHandRing1", "RightHandRing2", "RightHandRing3"]
    },
    {
      "type": "finger",
      "name": "pinky",
      "side": "R",
      "parent": "RightHand",
      "chain": ["RightHandPinky1", "RightHandPinky2", "RightHandPinky3"]
    }
  ]
}
