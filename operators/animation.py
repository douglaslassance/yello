import os
import datetime

import bpy

from ..contexts import SelectionContext, VisibleContext

from .. import animation
from .. import misc
from .. import io
from .. import ollama
from .. import rigging


class ExportAnimationOperator(bpy.types.Operator):
    bl_idname = "object.export_animation"
    bl_label = "Export Animation"
    bl_description = "Export selection to animated FBX."

    include_children: bpy.props.BoolProperty(
        name="Include Children",
        description="Include child objects of the selection.",
        default=True,
    )  # pyright: ignore [reportInvalidTypeForm]

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if bpy.data.filepath:
            if context.mode and context.selected_objects:
                return True
        return False

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context) -> set[str]:
        objects = list(context.selected_objects)
        if self.include_children:
            for obj in list(objects):
                objects.extend(misc.get_children(obj, recursive=True))
        filename = os.path.splitext(bpy.data.filepath)[0] + ".fbx"
        io.export_fbx(
            objects, filename, animations=True, object_types={"ARMATURE"}
        )
        return {"FINISHED"}


class ExportAnimatedMeshOperator(bpy.types.Operator):
    bl_idname = "object.export_animated_mesh"
    bl_label = "Export Animated Mesh"
    bl_description = "Export selected animated meshes to Alembic."

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if bpy.data.filepath:
            if context.mode and context.selected_objects:
                return True
        return False

    def execute(self, context: bpy.types.Context) -> set[str]:
        filename = os.path.splitext(bpy.data.filepath)[0] + ".abc"
        misc.make_writable(filename)
        bpy.ops.wm.alembic_export(
            apply_subdiv=True,
            check_existing=False,
            filepath=filename,
            selected=True,
            triangulate=True,
            use_instancing=False,
            uvs=False,
        )
        return {"FINISHED"}


class ExportActionsOperator(bpy.types.Operator):
    bl_idname = "armature.export_actions"
    bl_label = "Export Actions"
    bl_description = (
        "Export all actions on the selected armature to GLB, "
        "baking deform bone transforms and excluding control rig bones."
    )

    include_children: bpy.props.BoolProperty(
        name="Include Children",
        description="Include child objects of the armature.",
        default=True,
    )  # pyright: ignore [reportInvalidTypeForm]

    save_settings: bpy.props.BoolProperty(
        name="Save Settings",
        description="Remember export settings in the blend file.",
    )  # pyright: ignore [reportInvalidTypeForm]

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if not bpy.data.filepath:
            return False
        obj = context.object
        return obj is not None and obj.type == "ARMATURE" and obj.mode == "OBJECT"

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context) -> set[str]:
        skeleton = context.object
        objects = [skeleton]
        if self.include_children:
            objects += misc.get_children(skeleton, recursive=True)

        filename = os.path.splitext(bpy.data.filepath)[0] + ".glb"
        year = datetime.datetime.now().year
        misc.make_writable(filename)
        with VisibleContext(skeleton):
            with SelectionContext():
                misc.select_objects(objects)
                bpy.ops.export_scene.gltf(
                    filepath=filename,
                    check_existing=False,
                    use_selection=True,
                    use_visible=False,
                    export_yup=True,
                    export_reset_pose_bones=True,
                    export_copyright=f"© {year} Douglas Lassance",
                    export_format="GLB",
                    export_all_vertex_colors=True,
                    export_bake_animation=True,
                    export_merge_animation="NONE",
                    export_apply=True,
                    export_animations=True,
                    export_animation_mode="ACTIONS",
                    export_def_bones=True,
                    will_save_settings=self.save_settings,
                )
        return {"FINISHED"}


class ActionSelectionItem(bpy.types.PropertyGroup):
    """A single action entry in the transfer checklist."""

    selected: bpy.props.BoolProperty(
        name="", default=True
    )  # pyright: ignore [reportInvalidTypeForm]


class TransferAnimationOperator(bpy.types.Operator):
    """Transfer animation to selected armatures using Ollama-based bone matching.

    The operator lists all actions in the file as a checklist in the dialog.
    Bone names are extracted from each action's fcurves, so no source armature
    is required. Each selected action is copied and remapped for every target
    armature in the viewport selection.
    """

    bl_idname = "armature.transfer_animation"
    bl_label = "Transfer Animation"
    bl_description = (
        "Transfer actions to the selected armatures using Ollama-based bone matching."
    )

    action_items: bpy.props.CollectionProperty(
        type=ActionSelectionItem
    )  # pyright: ignore [reportInvalidTypeForm]

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.mode != "OBJECT":
            return False
        armatures = [obj for obj in context.selected_objects if obj.type == "ARMATURE"]
        return len(armatures) >= 1 and bool(bpy.data.actions)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        self.action_items.clear()
        for action in bpy.data.actions:
            item = self.action_items.add()
            item.name = action.name
            item.selected = True
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        if not ollama.reachable():
            layout.label(text="Ollama is not running.", icon="ERROR")
        layout.label(text="Actions to transfer:")
        for item in self.action_items:
            row = layout.row()
            row.prop(item, "selected", text=item.name)

    def execute(self, context: bpy.types.Context) -> set[str]:
        targets = [obj for obj in context.selected_objects if obj.type == "ARMATURE"]
        if not targets:
            self.report({"ERROR"}, "Select at least one armature as a target.")
            return {"CANCELLED"}

        actions = [
            bpy.data.actions[item.name]
            for item in self.action_items
            if item.selected and item.name in bpy.data.actions
        ]
        if not actions:
            self.report({"WARNING"}, "No actions selected.")
            return {"CANCELLED"}

        total_transferred = 0
        for target in targets:
            target_bone_names = [bone.name for bone in target.data.bones]
            first_target_action = None

            for action in actions:
                source_bone_names = animation.get_action_bone_names(action)
                if not source_bone_names:
                    self.report({"WARNING"}, f"{action.name}: no bone fcurves found.")
                    continue

                pairs, message, raw = rigging.match_bones(
                    source_bone_names, target_bone_names
                )
                self.report({"INFO"}, f"Ollama ({action.name} -> {target.name}): {raw}")
                if pairs is None:
                    self.report(
                        {"WARNING"}, f"{target.name} / {action.name}: {message}"
                    )
                    continue

                self.report({"INFO"}, f"{target.name} / {action.name}: {message}")

                bone_mapping = dict(pairs)
                target_action_name = f"{target.name}_{action.name}"
                target_action = animation.copy_and_remap_animation(
                    action, target_action_name, bone_mapping
                )
                if target_action is None:
                    continue

                target_action.use_fake_user = True
                fcurves = animation.get_action_fcurves(target_action)
                total_transferred += len(list(fcurves)) if fcurves is not None else 0

                if first_target_action is None:
                    first_target_action = target_action

            if first_target_action is not None:
                if target.animation_data is None:
                    target.animation_data_create()
                target.animation_data.action = first_target_action
                if (
                    hasattr(target.animation_data, "action_slot")
                    and first_target_action.slots
                ):
                    target.animation_data.action_slot = first_target_action.slots[0]

        self.report(
            {"INFO"},
            f"Transferred {total_transferred} fcurves to {len(targets)} target(s).",
        )
        return {"FINISHED"}
