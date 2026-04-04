import os
import bpy
import datetime

from ..contexts import SelectionContext, VisibleContext

from .. import functions


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
    def poll(cls, context):
        if bpy.data.filepath:
            if context.mode and context.selected_objects:
                return True
        return False

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        objects = list(context.selected_objects)
        if self.include_children:
            for obj in list(objects):
                objects.extend(functions.get_children(obj, recursive=True))
        filename = os.path.splitext(bpy.data.filepath)[0] + ".fbx"
        functions.export_fbx(
            objects, filename, animations=True, object_types={"ARMATURE"}
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

    @classmethod
    def poll(cls, context):
        if not bpy.data.filepath:
            return False
        obj = context.object
        return obj is not None and obj.type == "ARMATURE" and obj.mode == "OBJECT"

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        skeleton = context.object
        objects = [skeleton]
        if self.include_children:
            objects += functions.get_children(skeleton, recursive=True)

        filename = os.path.splitext(bpy.data.filepath)[0] + ".glb"
        year = datetime.datetime.now().year
        functions.make_writable(filename)
        with VisibleContext(skeleton):
            with SelectionContext():
                functions.select_objects(objects)
                bpy.ops.export_scene.gltf(
                    filepath=filename,
                    check_existing=False,
                    use_selection=True,
                    use_visible=False,
                    export_yup=True,
                    export_reset_pose_bones=True,
                    export_copyright=f"© {year} Playsthetic",
                    export_format="GLB",
                    export_all_vertex_colors=True,
                    export_bake_animation=True,
                    export_merge_animation="NONE",
                    export_apply=True,
                    export_animations=True,
                    export_animation_mode="ACTIONS",
                    export_def_bones=True,
                    will_save_settings=True,
                )
        return {"FINISHED"}
