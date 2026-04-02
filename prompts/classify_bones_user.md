Bone names:
{bone_list}

Return ONLY a JSON object. Omit any top-level key you cannot confidently identify.
All bone name values must be copied VERBATIM from the list above.

Use EXACTLY this schema:

{
  "arm_L":  { "shoulder": "...", "upper": "...", "lower": "...", "hand": "..." },
  "arm_R":  { "shoulder": "...", "upper": "...", "lower": "...", "hand": "..." },
  "leg_L":  { "upper": "...", "lower": "...", "foot": "...", "toe": "..." },
  "leg_R":  { "upper": "...", "lower": "...", "foot": "...", "toe": "..." },
  "spine":  ["bone1", "bone2", "..."],
  "neck":   "...",
  "head":   "...",
  "pelvis": "...",
  "fingers_L": {
    "thumb":  ["b1", "b2", "b3"],
    "index":  ["b1", "b2", "b3"],
    "middle": ["b1", "b2", "b3"],
    "ring":   ["b1", "b2", "b3"],
    "pinky":  ["b1", "b2", "b3"]
  },
  "fingers_R": { "thumb": [...], "index": [...], "middle": [...], "ring": [...], "pinky": [...] }
}

Key meanings:
- arm shoulder  = clavicle or shoulder bone (optional — set to null if absent)
- arm upper     = upper arm / humerus. NOTE: some rigs simply call this bone "Arm" — include it here.
- arm lower     = forearm / ulna / radius
- arm hand      = hand / wrist
- leg upper     = thigh / upper leg
- leg lower     = shin / calf / lower leg
- leg foot      = foot / ankle
- leg toe       = toe / ball (optional — set to null if absent)
- spine         = ONLY vertebrae from hips to chest/upper-back. Do NOT include neck or head. Ordered low to high.
- neck          = neck bone (single bone; use the first/main neck bone if there are several)
- head          = head bone (single bone)
- pelvis        = root hip / pelvis bone
- fingers_L/R   = ordered chains from knuckle to fingertip. Omit fingers you cannot find.

Rules:
- shoulder, toe, fingers are optional. Set single optional values to null if not found.
- Omit an entire top-level key if you cannot find its required bones.
- spine must NOT contain neck or head bones.
