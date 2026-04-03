import os
import subprocess
import platform
import bpy

from .. import functions


class ExportMeshOperator(bpy.types.Operator):
    bl_idname = "object.export_mesh"
    bl_label = "Export Mesh"
    bl_description = "Export selected meshes and armatures to a single FBX"

    file_format: bpy.props.EnumProperty(
        name="File format",
        description="The file format to export.",
        items=[
            ("FBX", "FBX", "FBX"),
            ("GLTF", "GLTF", "GLTF"),
        ],
    )  # pyright: ignore [reportInvalidTypeForm]

    join_meshes: bpy.props.BoolProperty(
        name="Join meshes",
        description="Join selected meshes in a single mesh.",
    )  # pyright: ignore [reportInvalidTypeForm]

    include_children: bpy.props.BoolProperty(
        name="Include children",
        description="Will add all children from selected parents.",
    )  # pyright: ignore [reportInvalidTypeForm]

    @classmethod
    def poll(cls, context):
        if bpy.data.filepath:
            if context.mode and context.selected_objects:
                return True
        return False

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        exports = bpy.context.selected_objects
        if self.include_children:
            for obj in bpy.context.selected_objects:
                for child in obj.children:
                    if child not in exports:
                        exports.append(child)
        if self.join_meshes:
            meshes = []
            joined_exports = []
            for obj in exports:
                if obj.type == "MESH":
                    meshes.append(obj)
                else:
                    joined_exports.append(obj)
            joined_mesh = functions.join_objects(meshes)
            if joined_mesh:
                joined_exports.append(joined_mesh)
            exports = joined_exports
        dirname, basename = os.path.split(bpy.data.filepath)
        filename = os.path.join(dirname, f"{os.path.splitext(basename)[0]}")
        if self.file_format == "FBX":
            functions.export_fbx(exports, filename + ".fbx")
        elif self.file_format == "GLTF":
            functions.export_gltf(exports, filename + ".glb", animations=False)
        if self.join_meshes and joined_mesh:
            functions.delete_objects([joined_mesh])
        return {"FINISHED"}


class ExportMeshesOperator(bpy.types.Operator):
    bl_idname = "object.export_meshes"
    bl_label = "Export Meshes"
    bl_description = "Export selected meshes to individual files"

    prefix: bpy.props.StringProperty(
        name="Prefix",
        description="The prefix for this file's name",
    )  # pyright: ignore [reportInvalidTypeForm]

    separator: bpy.props.StringProperty(
        name="Separator",
        default="_",
        description="The object name separator to use",
    )  # pyright: ignore [reportInvalidTypeForm]

    remove_pre_existing: bpy.props.BoolProperty(
        name="Remove pre-existing files",
        default=False,
        description="Remove pre-existing FBX files that match this export prefix",
    )  # pyright: ignore [reportInvalidTypeForm]

    @classmethod
    def poll(cls, context):
        if bpy.data.filepath:
            if context.mode and context.selected_objects:
                return True
        return False

    def invoke(self, context, event):
        basename = os.path.basename(bpy.data.filepath)
        self.prefix = os.path.splitext(basename)[0]
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        selection = bpy.context.selected_objects
        dirname, basename = os.path.split(bpy.data.filepath)
        if self.remove_pre_existing:
            for fbx_file in self.find_pre_existing(dirname, self.prefix):
                os.remove(fbx_file)
        for object in selection:
            object_name = object.name.replace(".", self.separator)
            filename = os.path.join(
                dirname,
                f"{self.prefix}{self.separator}{object_name}.fbx",
            )
            functions.export_fbx([object], filename)
        return {"FINISHED"}

    def find_pre_existing(self, dirname, prefix):
        """Find FBX files corresponding to this scene file export."""
        fbx_files = []
        for basename in os.listdir(dirname):
            if basename.startswith(prefix) and basename.endswith(".fbx"):
                fbx_files.append(os.path.join(dirname, basename))
        return fbx_files


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
        cr_obj, skel_obj = self._find_cr()
        if cr_obj is None:
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
                m.type == "ARMATURE" and m.object == skel_obj for m in obj.modifiers
            )
        ]

        skel_obj.hide_viewport = False
        skel_obj.hide_set(False)

        original_cr_action = (
            cr_obj.animation_data.action if cr_obj.animation_data else None
        )

        if skel_obj.animation_data is None:
            skel_obj.animation_data_create()

        baked_actions = []
        renamed_sources = []

        try:
            for action in actions:
                if cr_obj.animation_data is None:
                    cr_obj.animation_data_create()

                original_name = action.name
                action.name = f"__src_{original_name}"
                renamed_sources.append((action, original_name))

                cr_obj.animation_data.action = action
                skel_obj.animation_data.action = None

                frame_start = int(action.frame_range[0])
                frame_end = int(action.frame_range[1])

                context.view_layer.objects.active = skel_obj
                bpy.ops.object.mode_set(mode="POSE")
                bpy.ops.nla.bake(
                    frame_start=frame_start,
                    frame_end=frame_end,
                    only_selected=False,
                    visual_keying=True,
                    clear_constraints=False,
                    use_current_action=False,
                    bake_types={"POSE"},
                )
                bpy.ops.object.mode_set(mode="OBJECT")

                if skel_obj.animation_data and skel_obj.animation_data.action:
                    baked = skel_obj.animation_data.action
                    baked.name = original_name
                    baked_actions.append(baked)
                    track = skel_obj.animation_data.nla_tracks.new()
                    track.name = original_name
                    track.strips.new(original_name, frame_start, baked)
                    skel_obj.animation_data.action = None

            context.view_layer.objects.active = cr_obj

            for obj in context.selected_objects:
                obj.select_set(False)
            skel_obj.select_set(True)
            for mesh in skinned_meshes:
                mesh.select_set(True)

            filename = os.path.splitext(bpy.data.filepath)[0] + ".glb"
            functions.make_writable(filename)
            bpy.ops.export_scene.gltf(
                filepath=filename,
                export_format="GLB",
                use_selection=True,
                export_apply=True,
                export_def_bones=True,
                export_animations=True,
                export_animation_mode="NLA_TRACKS",
                export_reset_pose_bones=True,
                export_armature_object_remove=True,
                export_bake_animation=True,
            )

            self.report(
                {"INFO"}, f"Exported {len(baked_actions)} action(s) to {filename}"
            )

        finally:
            for action, original_name in renamed_sources:
                action.name = original_name
            if skel_obj.animation_data:
                for track in list(skel_obj.animation_data.nla_tracks):
                    skel_obj.animation_data.nla_tracks.remove(track)
                skel_obj.animation_data.action = None
            for baked in baked_actions:
                bpy.data.actions.remove(baked)
            if cr_obj.animation_data:
                cr_obj.animation_data.action = original_cr_action
            skel_obj.hide_set(True)

        return {"FINISHED"}


class MakeWritableOperator(bpy.types.Operator):
    bl_idname = "object.make_writable"
    bl_label = "Make Writable"
    bl_description = "Perform a Gitarmony make writable on the current file"

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.filepath)

    def execute(self, context):
        functions.make_writable(bpy.data.filepath)
        return {"FINISHED"}


class OpenContainingFolderOperator(bpy.types.Operator):
    bl_idname = "object.open_containing_folder"
    bl_label = "Open Containing Folder"

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.filepath)

    def execute(self, context):
        filepath = bpy.data.filepath
        if platform.system() == "Windows":
            subprocess.Popen(["explorer", "/select,", filepath])
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-R", filepath])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(filepath)])
        return {"FINISHED"}
