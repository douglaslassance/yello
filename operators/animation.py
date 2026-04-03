import os
import bpy
from ..contexts import SelectionContext

from .. import functions


class ExportAnimationOperator(bpy.types.Operator):
    bl_idname = "object.export_animation"
    bl_label = "Export Animation"
    bl_description = "Export selection to animated FBX."

    @classmethod
    def poll(cls, context):
        if bpy.data.filepath:
            if context.mode and context.selected_objects:
                return True
        return False

    def execute(self, context):
        filename = os.path.splitext(bpy.data.filepath)[0] + ".fbx"
        functions.make_writable(filename)
        bpy.ops.export_scene.fbx(
            add_leaf_bones=False,
            apply_scale_options="FBX_SCALE_NONE",
            apply_unit_scale=True,
            armature_nodetype="NULL",
            axis_forward="-Z",
            axis_up="Y",
            bake_anim=True,
            bake_space_transform=False,
            filepath=filename,
            global_scale=1.0,
            mesh_smooth_type="FACE",
            object_types={"ARMATURE"},
            primary_bone_axis="Y",
            secondary_bone_axis="X",
            use_selection=True,
            use_space_transform=True,
        )
        return {"FINISHED"}


class ExportAnimatedMeshOperator(bpy.types.Operator):
    bl_idname = "object.export_animated_mesh"
    bl_label = "Export Animated Mesh"
    bl_description = "Export selected animated meshes to Alembic."

    @classmethod
    def poll(cls, context):
        if bpy.data.filepath:
            if context.mode and context.selected_objects:
                return True
        return False

    def execute(self, context):
        filename = os.path.splitext(bpy.data.filepath)[0] + ".abc"
        functions.make_writable(filename)
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


class ExportControlRigAnimationsOperator(bpy.types.Operator):
    bl_idname = "armature.export_control_rig_animations"
    bl_label = "Export Control Rig Animations"
    bl_description = (
        "Bake all actions from the control rig onto the deform skeleton "
        "and export the result as a GLB alongside the current file."
    )

    @classmethod
    def _find_cr(cls):
        """Return the first ControlRig armature that has a matching deform skeleton."""
        for obj in bpy.data.objects:
            if obj.type == "ARMATURE" and obj.name.endswith("_ControlRig"):
                skel = bpy.data.objects.get(obj.name[: -len("_ControlRig")])
                if skel is not None:
                    return obj, skel
        return None, None

    @classmethod
    def poll(cls, context):
        if not bpy.data.filepath:
            return False
        cr_obj, _ = cls._find_cr()
        return cr_obj is not None

    def execute(self, context):
        control_rig, skeleton = self._find_cr()
        if control_rig is None:
            self.report({"ERROR"}, "No control rig found in the scene.")
            return {"CANCELLED"}

        actions = list(bpy.data.actions)
        if not actions:
            self.report({"WARNING"}, "No actions to export.")
            return {"CANCELLED"}

        skinned_meshes = [
            obj
            for obj in bpy.data.objects
            if obj.type == "MESH"
            and any(
                m.type == "ARMATURE" and m.object == skeleton for m in obj.modifiers
            )
        ]

        skeleton.hide_viewport = False
        skeleton.hide_set(False)

        initial_control_rig_action = (
            control_rig.animation_data.action if control_rig.animation_data else None
        )
        initial_active = context.view_layer.objects.active
        initial_selected = list(context.selected_objects)

        if skeleton.animation_data is None:
            skeleton.animation_data_create()

        baked_actions = []
        source_actions = []

        try:
            # for action in actions:
            #     if control_rig.animation_data is None:
            #         control_rig.animation_data_create()

            #     original_name = action.name
            #     action.name = f"__src_{original_name}"
            #     source_actions.append((action, original_name))

            #     control_rig.animation_data.action = action
            #     skeleton.animation_data.action = None

            #     frame_start = int(action.frame_range[0])
            #     frame_end = int(action.frame_range[1])

            #     context.view_layer.objects.active = skeleton
            #     bpy.ops.object.mode_set(mode="POSE")
            #     bpy.ops.nla.bake(
            #         frame_start=frame_start,
            #         frame_end=frame_end,
            #         only_selected=False,
            #         visual_keying=True,
            #         clear_constraints=False,
            #         use_current_action=False,
            #         bake_types={"POSE"},
            #     )
            #     bpy.ops.object.mode_set(mode="OBJECT")

            #     if skeleton.animation_data and skeleton.animation_data.action:
            #         baked = skeleton.animation_data.action
            #         baked.name = original_name
            #         baked_actions.append(baked)
            #         track = skeleton.animation_data.nla_tracks.new()
            #         track.name = original_name
            #         track.strips.new(original_name, frame_start, baked)
            #         skeleton.animation_data.action = None

            # context.view_layer.objects.active = control_rig

            # for obj in context.selected_objects:
            #     obj.select_set(False)
            # skeleton.select_set(True)
            # for mesh in skinned_meshes:
            #     mesh.select_set(True)

            with SelectionContext():
                filename = os.path.splitext(bpy.data.filepath)[0] + ".glb"
                functions.make_writable(filename)
                functions.select_objects([skeleton])
                bpy.ops.export_scene.gltf(
                    filepath=filename,
                    export_format="GLB",
                    use_selection=True,
                    export_apply=True,
                    export_def_bones=True,
                    export_animations=True,
                    export_bake_animation=True,
                    export_animation_mode="ACTIONS",
                    export_reset_pose_bones=True,
                    export_armature_object_remove=True,
                )

        finally:
            pass
            # self._cleanup(
            #     control_rig,
            #     skeleton,
            #     source_actions,
            #     baked_actions,
            #     initial_control_rig_action,
            #     initial_active,
            #     initial_selected,
            # )

        return {"FINISHED"}

    def _cleanup(
        self,
        control_rig,
        skeleton,
        source_actions,
        baked_actions,
        initial_control_rig_action,
        initial_active,
        initial_selected,
    ):
        """Clean up after exporting control rig animations."""
        for action, original_name in source_actions:
            action.name = original_name
        if skeleton.animation_data:
            for track in list(skeleton.animation_data.nla_tracks):
                skeleton.animation_data.nla_tracks.remove(track)
            skeleton.animation_data.action = None
        for baked in baked_actions:
            bpy.data.actions.remove(baked)
        if control_rig.animation_data:
            control_rig.animation_data.action = initial_control_rig_action
        skeleton.hide_set(True)
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        for obj in initial_selected:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = initial_active
