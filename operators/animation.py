import datetime
import os

import bpy
from bpy_extras.io_utils import ImportHelper

from .. import animation, io, misc, ollama, rigging, vertex_animation
from ..contexts import (
    AnimationContext,
    FrameRangeContext,
    ModeContext,
    MutedFcurvesContext,
    SelectionContext,
    VisibleContext,
)


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
        return bool(bpy.data.filepath and context.mode and context.selected_objects)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context) -> set[str]:
        objects = list(context.selected_objects)
        if self.include_children:
            for obj in list(objects):
                objects.extend(misc.get_children(obj, recursive=True))
        filename = os.path.splitext(bpy.data.filepath)[0] + ".fbx"
        io.export_fbx(objects, filename, animations=True, object_types={"ARMATURE"})
        return {"FINISHED"}


class ExportAnimatedMeshOperator(bpy.types.Operator):
    bl_idname = "object.export_animated_mesh"
    bl_label = "Export Animated Mesh"
    bl_description = (
        "Export selected animated meshes to Alembic or a vertex animation texture."
    )

    file_format: bpy.props.EnumProperty(
        name="File Format",
        description="The file format to export.",
        items=[
            ("ALEMBIC", "Alembic", "An Alembic cache"),
            (
                "VERTEX_ANIMATION_TEXTURE",
                "Vertex Animation Texture",
                (
                    "A GLB of the first frame and an EXR of its vertex positions "
                    "on every frame, which needs the same vertex count throughout"
                ),
            ),
        ],
        default="ALEMBIC",
    )  # pyright: ignore [reportInvalidTypeForm]

    normals: bpy.props.EnumProperty(
        name="Normals",
        description="Where each frame's vertex normals go.",
        items=[
            (
                vertex_animation.NORMALS_PACKED_IN_ALPHA,
                "Packed in Alpha",
                (
                    "Fold each normal into the alpha of its position texel, accurate "
                    "to about 0.04°. The EXR stays the size of the positions alone"
                ),
            ),
            (
                vertex_animation.NORMALS_BOTTOM_HALF,
                "Bottom Half",
                "Write normals in rows under the positions, doubling the EXR's height",
            ),
            (
                vertex_animation.NORMALS_SEPARATE_FILE,
                "Separate File",
                (
                    "Write normals to an 8 bit PNG beside the EXR, named after it with "
                    "a _normals suffix and accurate to about half a degree"
                ),
            ),
            (
                vertex_animation.NORMALS_NONE,
                "None",
                "Write no normals, so the game has to work them out",
            ),
        ],
        default=vertex_animation.NORMALS_PACKED_IN_ALPHA,
    )  # pyright: ignore [reportInvalidTypeForm]

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(bpy.data.filepath and context.mode and context.selected_objects)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.prop(self, "file_format")
        if self.file_format == "VERTEX_ANIMATION_TEXTURE":
            layout.prop(self, "normals")

    def execute(self, context: bpy.types.Context) -> set[str]:
        if self.file_format == "VERTEX_ANIMATION_TEXTURE":
            return self._export_vertex_animation_texture(context)
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

    def _export_vertex_animation_texture(self, context: bpy.types.Context) -> set[str]:
        meshes = [obj for obj in context.selected_objects if obj.type == "MESH"]
        if not meshes:
            self.report({"ERROR"}, "Select at least one mesh.")
            return {"CANCELLED"}
        filename = os.path.splitext(bpy.data.filepath)[0] + ".glb"
        try:
            with ModeContext("OBJECT"):
                io.export_vertex_animation_texture(
                    meshes, filename, normals=self.normals
                )
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
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

    disable_armature_animation: bpy.props.BoolProperty(
        name="Disable Armature Animation",
        description=(
            "Ignore keys on the armature object itself so only bone animation "
            "is exported. The armature holds the first frame of its active action."
        ),
        default=True,
    )  # pyright: ignore [reportInvalidTypeForm]

    export_markers: bpy.props.BoolProperty(
        name="Export Markers",
        description=(
            "Add each action's pose markers to the extras of its animation "
            "(ignored with FBX)."
        ),
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

    @staticmethod
    def _armature_transform_fcurves(
        skeleton: bpy.types.Object,
    ) -> list[bpy.types.FCurve]:
        """Return the object transform fcurves of actions the skeleton can play."""
        animation_data = skeleton.animation_data
        active_action = animation_data.action if animation_data else None
        fcurves = []
        for action in bpy.data.actions:
            if action == active_action or animation.get_action_bone_names(action):
                fcurves += animation.get_object_transform_fcurves(action)
        return fcurves

    @staticmethod
    def _hold_active_action_start(skeleton: bpy.types.Object) -> None:
        """Set the skeleton's own transform to the first frame of its active action."""
        action = skeleton.animation_data.action if skeleton.animation_data else None
        if action is None:
            return
        frame = action.frame_range[0]
        for fcurve in animation.get_object_transform_fcurves(action):
            values = getattr(skeleton, fcurve.data_path)
            values[fcurve.array_index] = fcurve.evaluate(frame)

    def execute(self, context: bpy.types.Context) -> set[str]:
        skeleton = context.object
        objects = [skeleton]
        if self.include_children:
            objects += misc.get_children(skeleton, recursive=True)

        extension = ".glb" if self.file_format == "GLTF" else ".fbx"
        filename = os.path.splitext(bpy.data.filepath)[0] + extension
        year = datetime.datetime.now().year
        misc.make_writable(filename)
        muted_fcurves = (
            self._armature_transform_fcurves(skeleton)
            if self.disable_armature_animation
            else []
        )
        with (
            VisibleContext(skeleton),
            AnimationContext(skeleton),
            MutedFcurvesContext(muted_fcurves),
            SelectionContext(),
        ):
            if muted_fcurves:
                self._hold_active_action_start(skeleton)
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
        if self.file_format == "GLTF" and self.export_markers:
            tagged = io.add_glb_action_markers(filename)
            self.report({"INFO"}, f"Added markers to {tagged} animation(s).")
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
    """Import animation from a file and retarget it onto the active armature."""

    bl_idname = "armature.import_animation"
    bl_label = "Import Animation"
    bl_description = (
        "Import an FBX, glTF, or blend file and retarget all of its actions onto "
        "the active armature. Both skeletons are classified so bones are matched "
        "by role. An armature with a control rig receives the animation on its "
        "controls, any other armature on its deform bones."
    )
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".fbx"
    filter_glob: bpy.props.StringProperty(
        default="*.fbx;*.glb;*.gltf;*.blend",
        options={"HIDDEN"},
    )  # pyright: ignore [reportInvalidTypeForm]

    method: bpy.props.EnumProperty(
        name="Method",
        description="How the imported animation reaches the target bones",
        items=[
            (
                animation.IMPORT_METHOD_BAKE,
                "Bake",
                (
                    "Drive the target bones from the source skeleton through temporary "
                    "world space constraints and bake the result. The source is scaled to "
                    "the target first, so different proportions and rest poses line up"
                ),
            ),
            (
                animation.IMPORT_METHOD_COPY,
                "Copy",
                (
                    "Copy the animation curves onto the matching bones as they are. Exact "
                    "and fast when both skeletons share proportions, rest pose and bone "
                    "orientations"
                ),
            ),
        ],
        default=animation.IMPORT_METHOD_BAKE,
    )  # pyright: ignore [reportInvalidTypeForm]

    reclassify: bpy.props.BoolProperty(
        name="Re-classify Bones",
        description=(
            "Classify the target's bones again with Ollama instead of reusing the "
            "result stored on the armature. Enable this after adding, removing, or "
            "renaming bones"
        ),
        default=False,
    )  # pyright: ignore [reportInvalidTypeForm]

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.object
        return obj is not None and obj.type == "ARMATURE" and obj.mode == "OBJECT"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        if not ollama.reachable():
            layout.label(text="Ollama is not running.", icon="ERROR")
        layout.prop(self, "method")
        target = context.object
        if (
            target is not None
            and not rigging.has_control_rig(target)
            and rigging.load_systems(target) is not None
        ):
            layout.prop(self, "reclassify")

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

    def _copy(
        self,
        target: bpy.types.Object,
        source: bpy.types.Object,
        source_systems: list[rigging.SystemDict],
        target_systems: list[rigging.SystemDict] | None,
        actions: list[bpy.types.Action],
    ) -> list[tuple[bpy.types.Action, str]] | None:
        """Copy each action's curves onto the target bones bound to the source."""
        bone_mapping = {
            binding.source_bone: binding.target_bone
            for binding in rigging.retarget_bindings(
                target, source_systems, target_systems
            )
            if binding.source_bone
            and binding.source_bone in source.pose.bones
            and binding.target_bone in target.pose.bones
        }
        if not bone_mapping:
            return None
        animation.match_rotation_modes(source, target, bone_mapping)
        copied = []
        for source_action in actions:
            new_action = animation.copy_and_remap_animation(
                source_action, source_action.name, bone_mapping
            )
            if new_action is not None:
                new_action.use_fake_user = True
                copied.append((new_action, source_action.name))
        return copied

    def _bake(
        self,
        context: bpy.types.Context,
        target: bpy.types.Object,
        source: bpy.types.Object,
        source_systems: list[rigging.SystemDict],
        target_systems: list[rigging.SystemDict] | None,
        actions: list[bpy.types.Action],
    ) -> list[tuple[bpy.types.Action, str]] | None:
        """Bake each action onto the target through temporary constraints."""
        constrained = rigging.bind_to_source(
            target, source, source_systems, target_systems
        )
        if not constrained:
            return None

        context.view_layer.objects.active = target
        bpy.ops.object.mode_set(mode="POSE")
        for pose_bone in target.pose.bones:
            # Blender 5.0 moved pose selection from Bone to PoseBone.
            selectable = pose_bone if hasattr(pose_bone, "select") else pose_bone.bone
            selectable.select = pose_bone.name in constrained

        baked = []
        with FrameRangeContext():
            for source_action in actions:
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
                    new_action.use_fake_user = True
                    baked.append((new_action, source_action.name))

        bpy.ops.object.mode_set(mode="OBJECT")
        rigging.remove_retarget_constraints(target)
        return baked

    def execute(self, context: bpy.types.Context) -> set[str]:
        target = context.object
        if not ollama.reachable():
            self.report({"ERROR"}, "Ollama is not running.")
            return {"CANCELLED"}

        target_systems = rigging.load_systems(target)
        if not rigging.has_control_rig(target) and (
            target_systems is None or self.reclassify
        ):
            target_systems, message, raw = rigging.classify_skeleton(target)
            self.report({"INFO"}, f"Ollama: {raw}")
            if not target_systems:
                self.report({"ERROR"}, message)
                return {"CANCELLED"}
            rigging.store_systems(target, target_systems)

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

        source_systems, message, raw = rigging.classify_skeleton(source)
        self.report({"INFO"}, f"Ollama: {raw}")
        if not source_systems:
            self._cleanup(imported, source_actions)
            self.report({"ERROR"}, message)
            return {"CANCELLED"}

        if source.animation_data is None:
            source.animation_data_create()
        actions = source_actions or (
            [source.animation_data.action] if source.animation_data.action else []
        )

        if self.method == animation.IMPORT_METHOD_COPY:
            retargeted = self._copy(
                target, source, source_systems, target_systems, actions
            )
        else:
            retargeted = self._bake(
                context, target, source, source_systems, target_systems, actions
            )
        self._cleanup(imported, source_actions)
        if retargeted is None:
            self.report({"ERROR"}, "No matching bones to retarget.")
            return {"CANCELLED"}

        # Renamed only once cleanup has freed the source action names.
        for retargeted_action, name in retargeted:
            retargeted_action.name = name
        if retargeted:
            animation.assign_action(target, retargeted[0][0])

        context.view_layer.objects.active = target
        self.report({"INFO"}, f"Imported and retargeted {len(retargeted)} action(s).")
        return {"FINISHED"}


class ActionSelectionItem(bpy.types.PropertyGroup):
    """A single action entry in the transfer checklist."""

    selected: bpy.props.BoolProperty(name="", default=True)  # pyright: ignore [reportInvalidTypeForm]


class TransferAnimationOperator(bpy.types.Operator):
    """Transfer actions from the file to the selected armatures using Ollama-based bone matching."""

    bl_idname = "armature.transfer_animation"
    bl_label = "Transfer Animation"
    bl_description = (
        "Transfer actions from the file onto the selected armatures, matching bones "
        "by role. Matches control bones when present, otherwise deform bones. To "
        "retarget external animation onto a control rig, use Import Animation "
        "instead."
    )

    method: bpy.props.EnumProperty(
        name="Method",
        description=(
            "How the animation reaches the target. Copy rewrites the action's curves "
            "as they are; bake plays the action on its source armature and keys the "
            "result"
        ),
        items=[
            (
                animation.TRANSFER_METHOD_COPY,
                "Copy",
                (
                    "Rename the action's fcurves onto the matched bones and keep every key "
                    "as it is. Fast and lossless, but the target must share the source's "
                    "rest pose, bone axes, rotation mode and proportions. Use this for "
                    "variants of the same skeleton"
                ),
            ),
            (
                animation.TRANSFER_METHOD_BAKE,
                "Bake",
                (
                    "Play the action on its source armature in the scene and key the "
                    "matched bones on every frame. Differences in bone axes, rolls, "
                    "rotation modes and proportions are compensated, and root motion is "
                    "scaled to fit. Both rigs should still rest in a similar pose, such as "
                    "a T-pose"
                ),
            ),
        ],
        default=animation.TRANSFER_METHOD_COPY,
    )  # pyright: ignore [reportInvalidTypeForm]

    action_items: bpy.props.CollectionProperty(type=ActionSelectionItem)  # pyright: ignore [reportInvalidTypeForm]

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
        layout.prop(self, "method")
        layout.label(text="Actions to Transfer:")
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

        armatures = [obj for obj in context.scene.objects if obj.type == "ARMATURE"]
        total_transferred = 0
        for target in targets:
            target_bone_names = [bone.name for bone in target.data.bones]
            candidates = [armature for armature in armatures if armature != target]
            first_target_action = None

            for action in actions:
                source_bone_names = animation.get_action_bone_names(action)
                if not source_bone_names:
                    self.report({"WARNING"}, f"{action.name}: no bone fcurves found.")
                    continue

                source = None
                if self.method == animation.TRANSFER_METHOD_BAKE:
                    source = animation.find_source_armature(action, candidates)
                    if source is None:
                        self.report(
                            {"WARNING"},
                            f"{target.name} / {action.name}: no armature in the "
                            "scene holds the action's bones to bake from.",
                        )
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
                if self.method == animation.TRANSFER_METHOD_BAKE:
                    target_action = animation.bake_remapped_animation(
                        source, action, target, target_action_name, bone_mapping
                    )
                else:
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
