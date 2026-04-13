import bpy

from .. import ollama
from .. import retargeting
from .. import rigging


def _source_skeleton_items(self, context: bpy.types.Context):
    """Return armatures in the scene that are not the active object."""
    active = context.object
    return [
        (obj.name, obj.name, "")
        for obj in context.scene.objects
        if obj.type == "ARMATURE" and obj is not active
    ]


class RetargetAnimationOperator(bpy.types.Operator):
    """Retarget animation from a source armature onto this skeleton's control rig.

    Uses Ollama to match source bones to control bones, adds temporary
    COPY_TRANSFORMS constraints, bakes the result to keyframes, then cleans up.
    """

    bl_idname = "armature.retarget_animation"
    bl_label = "Retarget Animation"
    bl_description = (
        "Match a source armature's bones to this skeleton's control rig using "
        "Ollama, bake the animation to keyframes, then remove the constraints."
    )

    source_skeleton_name: bpy.props.EnumProperty(
        name="Source",
        description="Armature to retarget animation from.",
        items=_source_skeleton_items,
    )  # pyright: ignore [reportInvalidTypeForm]

    frame_start: bpy.props.IntProperty(
        name="Frame Start",
        description="First frame of the range to bake.",
        default=1,
        min=0,
    )  # pyright: ignore [reportInvalidTypeForm]

    frame_end: bpy.props.IntProperty(
        name="Frame End",
        description="Last frame of the range to bake.",
        default=250,
        min=1,
    )  # pyright: ignore [reportInvalidTypeForm]

    action_name: bpy.props.StringProperty(
        name="Action Name",
        description="Name for the baked action.",
        default="Retargeted",
    )  # pyright: ignore [reportInvalidTypeForm]

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.object
        if obj is None or obj.type != "ARMATURE" or obj.mode != "OBJECT":
            return False
        if not retargeting.has_control_rig(obj):
            return False
        armatures = [
            o for o in context.scene.objects if o.type == "ARMATURE" and o is not obj
        ]
        return len(armatures) > 0

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        scene = context.scene
        self.frame_start = scene.frame_start
        self.frame_end = scene.frame_end
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        if not ollama.reachable():
            layout.label(text="Ollama is offline.", icon="ERROR")
            layout.label(text=f"Make sure Ollama is running at {ollama.URL}.")
        layout.prop(self, "source_skeleton_name")
        layout.prop(self, "action_name")
        row = layout.row(align=True)
        row.prop(self, "frame_start")
        row.prop(self, "frame_end")

    def execute(self, context: bpy.types.Context) -> set[str]:
        if not ollama.reachable():
            self.report({"ERROR"}, "Ollama is not reachable.")
            return {"CANCELLED"}

        target_skeleton = context.object
        source_skeleton = context.scene.objects.get(self.source_skeleton_name)
        if source_skeleton is None:
            self.report({"ERROR"}, f"Source armature '{self.source_skeleton_name}' not found.")
            return {"CANCELLED"}

        source_bone_names = [bone.name for bone in source_skeleton.data.bones]
        target_bone_names = [bone.name for bone in target_skeleton.data.bones]

        pairs, message, raw = rigging.match_bones(source_bone_names, target_bone_names)
        self.report({"INFO"}, f"Ollama: {raw}")
        if pairs is None:
            self.report({"ERROR"}, message)
            return {"CANCELLED"}
        self.report({"INFO"}, message)

        bone_mapping = {source: target for source, target in pairs}

        bpy.ops.object.mode_set(mode="POSE")
        constraint_count = retargeting.add_retarget_constraints(
            target_skeleton, source_skeleton, bone_mapping
        )
        if constraint_count == 0:
            self.report({"WARNING"}, "No constraints could be added — check bone names.")
            bpy.ops.object.mode_set(mode="OBJECT")
            return {"CANCELLED"}

        action = retargeting.bake_retarget_action(
            target_skeleton,
            frame_start=self.frame_start,
            frame_end=self.frame_end,
            action_name=self.action_name,
        )

        retargeting.remove_retarget_constraints(target_skeleton)
        bpy.ops.object.mode_set(mode="OBJECT")

        if action is None:
            self.report({"WARNING"}, "Bake completed but no action was produced.")
            return {"FINISHED"}

        self.report(
            {"INFO"},
            f"Retargeted '{source_skeleton.name}' → '{target_skeleton.name}' "
            f"({constraint_count} bones, action '{action.name}').",
        )
        return {"FINISHED"}
