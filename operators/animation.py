import os
import datetime

import bpy
from bpy_extras.io_utils import ImportHelper

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
        "Export all actions on the selected armature, "
        "baking deform bone transforms and excluding control rig bones."
    )

    file_format: bpy.props.EnumProperty(
        name="File Format",
        description="The file format to export.",
        items=[
            ("GLTF", "glTF", "glTF"),
            ("FBX", "FBX", "FBX"),
        ],
        default="GLTF",
    )  # pyright: ignore [reportInvalidTypeForm]

    materials: bpy.props.EnumProperty(
        name="Materials",
        description="How to handle materials on exported meshes (ignored with FBX).",
        items=[
            ("EXPORT", "Export", "Export all materials used by included objects."),
            (
                "PLACEHOLDER",
                "Placeholder",
                "Do not export materials but keep material slots.",
            ),
            (
                "VIEWPORT",
                "Viewport",
                "Export minimal materials as defined in viewport display.",
            ),
            ("NONE", "No Export", "Do not export materials."),
        ],
        default="EXPORT",
    )  # pyright: ignore [reportInvalidTypeForm]

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

        extension = ".glb" if self.file_format == "GLTF" else ".fbx"
        filename = os.path.splitext(bpy.data.filepath)[0] + extension
        year = datetime.datetime.now().year
        misc.make_writable(filename)
        with VisibleContext(skeleton):
            with SelectionContext():
                misc.select_objects(objects)
                if self.file_format == "GLTF":
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
                        export_materials=self.materials,
                        will_save_settings=self.save_settings,
                    )
                else:
                    bpy.ops.export_scene.fbx(
                        filepath=filename,
                        check_existing=False,
                        use_selection=True,
                        use_visible=False,
                        add_leaf_bones=False,
                        apply_scale_options="FBX_SCALE_NONE",
                        apply_unit_scale=True,
                        armature_nodetype="NULL",
                        axis_forward="-Z",
                        axis_up="Y",
                        bake_anim=True,
                        bake_anim_use_all_actions=True,
                        bake_anim_use_nla_strips=False,
                        bake_space_transform=False,
                        global_scale=1.0,
                        mesh_smooth_type="FACE",
                        object_types={"ARMATURE", "MESH"},
                        primary_bone_axis="Y",
                        secondary_bone_axis="X",
                        use_armature_deform_only=True,
                        use_space_transform=True,
                    )
        return {"FINISHED"}


class CleanupOrphanFcurvesOperator(bpy.types.Operator):
    """Remove fcurves whose data paths do not resolve on the active armature.

    Walks every action's slotted layer/strip/channelbag structure. For each
    channelbag, an fcurve is considered orphan when its data path cannot be
    resolved on the active armature (typically a bone that no longer exists).
    Channelbags where no fcurve resolves are skipped entirely, since the action
    targets a different rig.
    """

    bl_idname = "armature.cleanup_orphan_fcurves"
    bl_label = "Cleanup Orphan Fcurves"
    bl_description = (
        "Remove fcurves on bones that do not exist on the active armature, "
        "across all actions targeting this rig."
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.object
        return obj is not None and obj.type == "ARMATURE"

    def execute(self, context: bpy.types.Context) -> set[str]:
        skeleton = context.object
        path_resolve = skeleton.path_resolve
        removed_total = 0
        affected_actions = 0
        for action in bpy.data.actions:
            removed_in_action = 0
            for layer in action.layers:
                for strip in layer.strips:
                    if not hasattr(strip, "channelbags"):
                        continue
                    for channelbag in strip.channelbags:
                        if not channelbag.fcurves:
                            continue
                        orphans = []
                        valid_count = 0
                        for fcurve in channelbag.fcurves:
                            path = fcurve.data_path
                            if fcurve.array_index:
                                path = f"{path}[{fcurve.array_index}]"
                            try:
                                path_resolve(path)
                            except ValueError:
                                orphans.append(fcurve)
                            else:
                                valid_count += 1
                        if valid_count == 0:
                            continue
                        for fcurve in orphans:
                            channelbag.fcurves.remove(fcurve)
                            removed_in_action += 1
            if removed_in_action:
                affected_actions += 1
                removed_total += removed_in_action
        self.report(
            {"INFO"},
            f"Removed {removed_total} orphan fcurve(s) "
            f"from {affected_actions} action(s).",
        )
        return {"FINISHED"}


class ImportAnimationOperator(bpy.types.Operator, ImportHelper):
    """Import animation from a file and retarget it onto the active control rig.

    The active object must be a control rig. The source skeleton is classified
    with Ollama, its scale is normalized to the target, and every source action
    is baked onto the control bones through temporary world-space constraints.
    The imported source objects and actions are removed afterwards, leaving only
    the baked actions on the control rig.
    """

    bl_idname = "armature.import_animation"
    bl_label = "Import Animation"
    bl_description = (
        "Import an FBX, glTF, or blend file and retarget all of its actions onto "
        "the active control rig. Bones are matched by role, the source is scaled "
        "to fit, and each action is baked onto the controls through temporary "
        "constraints. Use this to bring in external animation from another rig."
    )
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".fbx"
    filter_glob: bpy.props.StringProperty(
        default="*.fbx;*.glb;*.gltf;*.blend",
        options={"HIDDEN"},
    )  # pyright: ignore [reportInvalidTypeForm]

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.object
        if obj is None or obj.type != "ARMATURE" or obj.mode != "OBJECT":
            return False
        return any(rigging.CONTROL_SUFFIX in bone.name for bone in obj.data.bones)

    def draw(self, context: bpy.types.Context) -> None:
        if not ollama.reachable():
            self.layout.label(text="Ollama is not running.", icon="ERROR")

    def _cleanup(
        self,
        imported: list[bpy.types.Object],
        source_actions: list[bpy.types.Action],
    ) -> None:
        for obj in imported:
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        for action in source_actions:
            if action.name in bpy.data.actions:
                bpy.data.actions.remove(action)

    def execute(self, context: bpy.types.Context) -> set[str]:
        target = context.object
        if not ollama.reachable():
            self.report({"ERROR"}, "Ollama is not running.")
            return {"CANCELLED"}

        extension = os.path.splitext(self.filepath)[1].lower()
        existing_actions = set(bpy.data.actions)
        if extension == ".fbx":
            imported = io.import_fbx(self.filepath)
        elif extension in (".glb", ".gltf"):
            imported = io.import_gltf(self.filepath)
        elif extension == ".blend":
            imported = io.append_blend(self.filepath)
        else:
            self.report({"ERROR"}, f"Unsupported file type: {extension}")
            return {"CANCELLED"}

        source = next((obj for obj in imported if obj.type == "ARMATURE"), None)
        source_actions = [a for a in bpy.data.actions if a not in existing_actions]

        if source is None:
            self._cleanup(imported, source_actions)
            self.report({"ERROR"}, "No armature found in the imported file.")
            return {"CANCELLED"}

        source_bone_names = [bone.name for bone in source.data.bones]
        systems, message, raw = rigging.classify_bones(source_bone_names)
        self.report({"INFO"}, f"Ollama: {raw}")
        if not systems:
            self._cleanup(imported, source_actions)
            self.report({"ERROR"}, message)
            return {"CANCELLED"}

        constrained = rigging.bind_controls_to_source(target, source, systems)
        if not constrained:
            self._cleanup(imported, source_actions)
            self.report({"ERROR"}, "No matching control bones to retarget.")
            return {"CANCELLED"}

        context.view_layer.objects.active = target
        bpy.ops.object.mode_set(mode="POSE")
        for bone in target.data.bones:
            bone.select = bone.name in constrained

        if source.animation_data is None:
            source.animation_data_create()

        actions_to_bake = source_actions or (
            [source.animation_data.action] if source.animation_data.action else []
        )
        first_target_action = None
        baked = 0
        for source_action in actions_to_bake:
            if source_action is None:
                continue
            animation.assign_action(source, source_action)

            frame_start, frame_end = source_action.frame_range
            context.scene.frame_start = int(frame_start)
            context.scene.frame_end = int(frame_end)

            if target.animation_data is None:
                target.animation_data_create()
            target.animation_data.action = None
            bpy.ops.nla.bake(
                frame_start=int(frame_start),
                frame_end=int(frame_end),
                only_selected=True,
                visual_keying=True,
                clear_constraints=False,
                clear_parents=False,
                use_current_action=False,
                bake_types={"POSE"},
            )
            new_action = target.animation_data.action
            if new_action is not None:
                new_action.name = source_action.name
                new_action.use_fake_user = True
                baked += 1
                if first_target_action is None:
                    first_target_action = new_action

        bpy.ops.object.mode_set(mode="OBJECT")
        rigging.remove_retarget_constraints(target)
        self._cleanup(imported, source_actions)

        if first_target_action is not None:
            animation.assign_action(target, first_target_action)

        context.view_layer.objects.active = target
        self.report({"INFO"}, f"Imported and retargeted {baked} action(s).")
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
        "Copy actions from the file onto the selected armatures by matching bones "
        "and rewriting fcurves, without baking or scaling. Matches control bones "
        "when present, otherwise deform bones. Best for rigs that already share a "
        "rest pose. To retarget external animation onto a control rig, use Import "
        "Animation instead."
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
                animation.assign_action(target, first_target_action)

        self.report(
            {"INFO"},
            f"Transferred {total_transferred} fcurves to {len(targets)} target(s).",
        )
        return {"FINISHED"}
