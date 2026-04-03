import bpy
import math
import mathutils

from .. import functions
from ..contexts import CursorContext, ModeContext
from .. import ollama
from .. import rigging


class AlignBoneRollsOperator(bpy.types.Operator):
    bl_idname = "armature.align_bone_rolls"
    bl_label = "Align Bone Rolls"
    bl_description = "Align bone rolls to the plane formed by the angle between bones."

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is not None:
            if obj.mode == "EDIT":
                return True
        return False

    def execute(self, context):
        bones = context.editable_bones
        if not bones or len(bones) < 2:
            self.report({"ERROR"}, "A minimum of 2 bones should be selected")
            return {"FINISHED"}
        bones.reverse()
        for bone in bones[:-1]:
            parent_index = bones.index(bone) + 1
            if not bone.parent == bones[parent_index]:
                self.report({"ERROR"}, "Selected bones need to be connected")
                return {"FINISHED"}
        bones.reverse()
        first_bone_vector = bones[0].tail - bones[0].head
        last_bone_vector = bones[-1].head - bones[-1].tail
        normal = first_bone_vector.cross(last_bone_vector).normalized()
        # TODO: Intersection is calculated in local space.
        # This won't work if the amature transform is not zeroed out.
        intersections = mathutils.geometry.intersect_line_line(
            bones[0].head,
            bones[0].head + first_bone_vector * 10,
            bones[-1].tail,
            bones[-1].tail + last_bone_vector * 10,
        )
        if not intersections:
            self.report(
                {"WARNING"},
                "Could not align bone rolls probably because they form a straight line",
            )
            return {"FINISHED"}
        intersection = intersections[0]
        with CursorContext():
            bpy.context.scene.cursor.location = intersection + normal
            bpy.ops.armature.calculate_roll(type="CURSOR")
        return {"FINISHED"}


class AlignBonesOperator(bpy.types.Operator):
    bl_idname = "armature.align_bones"
    bl_label = "Align Bones"
    bl_description = "Align bones to the plane formed by the angle between the first and last bone of a chain."

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is not None:
            if obj.mode == "EDIT":
                return True
        return False

    def execute(self, context):
        bones = context.editable_bones
        if not bones or len(bones) < 2:
            self.report({"ERROR"}, "A minimum of 2 bones should be selected")
            return {"FINISHED"}
        bones.reverse()
        for bone in bones[:-1]:
            parent_index = bones.index(bone) + 1
            if not bone.parent == bones[parent_index]:
                self.report({"ERROR"}, "Selected bones need to be connected")
                return {"FINISHED"}
        bones.reverse()
        start = bones[0].head
        mid = bones[0].tail
        end = bones[-1].tail
        normal = (mid - start).cross(end - mid).normalized()
        for bone in bones[1:-1]:
            bone_vector = bone.tail - bone.head
            projected_vector = functions.get_projected_vector(bone_vector, normal)
            bone.tail = projected_vector + bone.head
        return {"FINISHED"}


class CreateBoneAlignedObjectOperator(bpy.types.Operator):
    bl_idname = "pose.create_bone_aligned_object"
    bl_label = "Create Bone Aligned Object"
    bl_description = "Creates an empty object aligned to the active bone in pose mode."

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is not None:
            if obj.mode == "POSE":
                return True
        return False

    def execute(self, context):
        pose_bone = context.active_pose_bone
        if not pose_bone:
            self.report({"ERROR"}, "One bone should be selected and active.")
            return {"FINISHED"}
        bone = pose_bone.id_data
        matrix_final = bone.matrix_world @ pose_bone.matrix
        obj = bpy.data.objects.new("Test", None)
        collection = functions.create_collection("Bone Aligned")
        collection.objects.link(obj)
        obj.name = bone.name
        obj.matrix_world = matrix_final
        obj.empty_display_size = 0.25
        obj.empty_display_type = "ARROWS"
        return {"FINISHED"}


class DistributeBonesEvenlyOperator(bpy.types.Operator):
    bl_idname = "armature.distribute_bones_evenly"
    bl_label = "Distribute Bones Evenly"
    bl_description = "Straighen a chain and distribute bone length evenly."

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is not None:
            if obj.mode == "EDIT":
                return True
        return False

    def execute(self, context):
        bones = context.editable_bones
        if not bones or len(bones) < 2:
            self.report({"ERROR"}, "A minimum of 2 bones should be selected")
            return {"FINISHED"}
        bones.reverse()
        for bone in bones[:-1]:
            parent_index = bones.index(bone) + 1
            if not bone.parent == bones[parent_index]:
                self.report({"ERROR"}, "Selected bones need to be connected")
                return {"FINISHED"}
        head = bones[-1].head
        overarching_vector = bones[0].tail - head
        length = overarching_vector.length
        normalized = overarching_vector.normalized()
        bone_count = len(bones)
        bone_number = 0
        bones.reverse()
        for bone in bones[:-1]:
            bone_number += 1
            bone.tail = head + normalized * length / bone_count * bone_number
        for bone in bones:
            bone.roll = 0
        return {"FINISHED"}


class GenerateTwistBonesOperator(bpy.types.Operator):
    _count_key = "yello_generate_twist_bones_count"

    bl_idname = "armature.generate_twist_bones"
    bl_label = "Generate Twist Bones"
    bl_description = "Generate twist bone chains parented to the selected bones."

    count: bpy.props.IntProperty(name="Count", default=3)

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is not None:
            if obj.mode == "EDIT":
                return True
        return False

    def invoke(self, context, event):
        bones = context.editable_bones
        if not bones:
            self.report({"ERROR"}, "At least one bone should be selected")
            return {"FINISHED"}
        if self._count_key in bpy.context.scene.world:
            self.count = bpy.context.scene.world[self._count_key]
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        bones = context.editable_bones
        for bone in bones:
            length = bone.length / float(self.count)
            direction = (bone.tail - bone.head).normalized()
            previous = bone
            edit_bones = context.object.data.edit_bones
            createds = []
            for number in range(self.count):
                splits = bone.name.split(".")
                name = ".".join(
                    splits[:-1] + ["Twist.{:03d}".format(number + 1), splits[-1]]
                )
                new_bone = edit_bones.new(name)
                new_bone.envelope_weight = bone.envelope_weight
                new_bone.envelope_distance = bone.envelope_distance
                new_bone.head_radius = bone.head_radius * 1.25
                new_bone.tail_radius = bone.tail_radius * 1.24
                new_bone.head = bone.head + direction * length * number
                new_bone.tail = new_bone.head + direction * length
                # TODO: calculate the roll interpolation been the root bone and next.
                # For now we are matching the parent on all twists bones.
                new_bone.roll = bone.roll
                new_bone.parent = previous
                if new_bone.head == previous.tail:
                    new_bone.use_connect = True
                createds.append(new_bone.name)
                previous = new_bone
            bone.use_deform = False
        with ModeContext("POSE"):
            for created in createds:
                bpy.context.object.pose.bones[created].bone.hide = True
        bpy.context.scene.world[self._count_key] = self.count
        return {"FINISHED"}


class GenerateBlendBoneOperator(bpy.types.Operator):
    bl_idname = "armature.generate_blend_bone"
    bl_label = "Generate Blend Bone"
    bl_description = (
        "Generate intermediary bone rotated halfway between two selected bones."
    )

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is not None:
            if obj.mode == "EDIT":
                return True
        return False

    def execute(self, context):
        bones = context.editable_bones
        if not bones or len(bones) < 2:
            self.report({"ERROR"}, "A minimum of 2 bones should be selected")
            return {"FINISHED"}
        bones.reverse()
        for bone in bones[:-1]:
            parent_index = bones.index(bone) + 1
            if not bone.parent == bones[parent_index]:
                self.report({"ERROR"}, "Selected bones need to be connected")
                return {"FINISHED"}
        bones.reverse()
        splits = bones[-1].name.split(".")
        edit_bones = context.object.data.edit_bones
        new_name = ".".join(splits[:-1] + ["Blend", splits[-1]])
        for child in bones[0].children:
            if child.name == new_name:
                new_bone = child
                break
        else:
            new_bone = edit_bones.new(new_name)
        new_bone.envelope_weight = bones[-1].envelope_weight
        new_bone.envelope_distance = bones[-1].envelope_distance
        new_bone.head_radius = bones[-1].head_radius
        new_bone.tail_radius = bones[-1].tail_radius
        new_bone.head = bones[-1].head
        parent_bone_vector = bones[0].head - bones[0].tail
        child_bone_vector = bones[-1].tail - bones[-1].head
        if bones[0].length <= bones[-1].length:
            tail = (parent_bone_vector) + (child_bone_vector).normalized() * bones[
                0
            ].length
        else:
            tail = (child_bone_vector) + (parent_bone_vector).normalized() * bones[
                -1
            ].length
        new_bone.tail = tail.normalized() * 4.0 + new_bone.head
        new_bone.parent = bones[0]
        # TODO: There is still some imperfection with this roll calculation.
        normal = parent_bone_vector.cross(child_bone_vector)
        bpy.ops.armature.select_all(action="DESELECT")
        with CursorContext():
            bpy.context.scene.cursor.location = normal + new_bone.head
            bpy.context.object.data.edit_bones.active = new_bone
            bpy.ops.armature.calculate_roll(type="CURSOR")
        with ModeContext("POSE"):
            bpy.context.object.pose.bones[new_bone.name].bone.hide = True
        return {"FINISHED"}


class BuildControlRigOperator(bpy.types.Operator):
    bl_idname = "armature.build_control_rig"
    bl_label = "Build Control Rig"
    bl_description = (
        "Detect arm/leg bones by name and build an IK/FK control rig armature. "
        "Deform bones are wired via Copy Transforms driven by an ik_fk property."
    )

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "ARMATURE" and obj.mode == "OBJECT"

    def invoke(self, context, event):
        if not ollama.reachable():
            return context.window_manager.invoke_props_dialog(self, width=300)
        return self.execute(context)

    def draw(self, context):
        self.layout.label(text="Ollama is offline.", icon="ERROR")
        self.layout.label(text=f"Make sure Ollama is running at {ollama.URL}.")

    def execute(self, context):
        skeleton = context.object

        if not ollama.reachable():
            return {"CANCELLED"}

        bone_names = [b.name for b in skeleton.data.bones]
        systems, message, raw = rigging.classify_bones(bone_names)
        self.report({"INFO"}, f"Ollama: {raw}")
        if not systems:
            self.report({"ERROR"}, message)
            return {"CANCELLED"}
        self.report({"INFO"}, message)

        all_bone_names = rigging.extract_bone_names(systems)

        bpy.ops.object.mode_set(mode="POSE")
        rigging.cleanup_existing_control_rig(skeleton)
        bpy.ops.object.mode_set(mode="OBJECT")

        bpy.ops.object.mode_set(mode="EDIT")
        bone_data = {}
        for name in all_bone_names:
            if name in skeleton.data.edit_bones:
                edit_bone = skeleton.data.edit_bones[name]
                bone_data[name] = {
                    "head": edit_bone.head.copy(),
                    "tail": edit_bone.tail.copy(),
                    "roll": edit_bone.roll,
                }
        bpy.ops.object.mode_set(mode="OBJECT")

        shapes = {
            "circle": rigging.get_or_create_shape("Shape_Circle", rigging.create_circle_shape),
            "box": rigging.get_or_create_shape("Shape_Box", rigging.create_box_shape),
            "diamond": rigging.get_or_create_shape("Shape_Diamond", rigging.create_diamond_shape),
            "sphere": rigging.get_or_create_shape("Shape_Sphere", rigging.create_sphere_shape),
            "square": rigging.get_or_create_shape("Shape_Square", rigging.create_square_shape),
            "master": rigging.get_or_load_blend_shape("base_controller.034"),
            "pelvis_hips": rigging.get_or_load_blend_shape("other_controller.003"),
        }

        control_rig_name = skeleton.name + "_ControlRig"
        if control_rig_name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[control_rig_name], do_unlink=True)

        control_rig_arm_data = bpy.data.armatures.new(control_rig_name)
        control_rig = bpy.data.objects.new(control_rig_name, control_rig_arm_data)
        for col in skeleton.users_collection:
            col.objects.link(control_rig)
        if not skeleton.users_collection:
            context.scene.collection.objects.link(control_rig)
        control_rig.matrix_world = skeleton.matrix_world.copy()

        for shape in shapes.values():
            if shape is not None:
                rigging.parent_to_control_rig(shape, control_rig)

        context.view_layer.objects.active = control_rig
        bpy.ops.object.mode_set(mode="EDIT")
        rigging.build_control_bones(control_rig_arm_data, systems, bone_data)
        bpy.ops.object.mode_set(mode="OBJECT")

        bpy.ops.object.mode_set(mode="POSE")
        rigging.setup_control_rig_pose(control_rig, systems, shapes)
        rigging.setup_spine_splineik(control_rig, systems, context, bone_data)
        bpy.ops.object.mode_set(mode="OBJECT")

        context.view_layer.objects.active = skeleton
        bpy.ops.object.mode_set(mode="POSE")
        wire_log = rigging.wire_deform_constraints(skeleton, control_rig, systems)
        bpy.ops.object.mode_set(mode="OBJECT")

        control_rig.show_in_front = False
        control_rig_arm_data.display_type = "WIRE"
        control_rig_arm_data.show_bone_custom_shapes = True
        control_rig_arm_data.show_bone_colors = True

        skeleton.hide_set(True)

        context.view_layer.objects.active = control_rig
        bpy.context.scene.frame_set(bpy.context.scene.frame_current)
        for line in wire_log:
            if line:
                self.report({"INFO"}, line)
        self.report({"INFO"}, f"Control rig built: {control_rig_name}")
        return {"FINISHED"}


class RemoveControlRigOperator(bpy.types.Operator):
    bl_idname = "armature.remove_control_rig"
    bl_label = "Remove Control Rig"
    bl_description = "Remove the control rig and all constraints from the skeleton armature."

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "ARMATURE" and obj.mode == "OBJECT"

    @staticmethod
    def _resolve_skeleton(context):
        """Return the skeleton object whether the user selected the CR or the skeleton."""
        obj = context.object
        if obj is None or obj.type != "ARMATURE":
            return None
        # If the selected object ends with _ControlRig, the skeleton is the name without it
        if obj.name.endswith("_ControlRig"):
            skeleton_name = obj.name[:-len("_ControlRig")]
            return bpy.data.objects.get(skeleton_name)
        return obj

    def execute(self, context):
        skeleton = self._resolve_skeleton(context)
        if skeleton is None:
            self.report({"ERROR"}, "Could not find the skeleton armature.")
            return {"CANCELLED"}
        control_rig_name = skeleton.name + "_ControlRig"

        skeleton.hide_viewport = False
        skeleton.hide_set(False)
        context.view_layer.objects.active = skeleton
        bpy.ops.object.mode_set(mode="POSE")
        rigging.cleanup_existing_control_rig(skeleton)
        bpy.ops.object.mode_set(mode="OBJECT")

        control_rig = bpy.data.objects.get(control_rig_name)
        if control_rig:
            for child in list(control_rig.children):
                bpy.data.objects.remove(child, do_unlink=True)
            bpy.data.objects.remove(control_rig, do_unlink=True)
            self.report({"INFO"}, f"Removed control rig: {control_rig_name}")
        else:
            self.report({"WARNING"}, f"No control rig found ({control_rig_name})")

        return {"FINISHED"}


class NormalizeBoneRollOperator(bpy.types.Operator):
    bl_idname = "armature.normalize_bone_roll"
    bl_label = "Normalize Bone Roll"
    bl_description = "Set the roll closest to zero."

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is not None:
            if obj.mode == "EDIT":
                return True
        return False

    def execute(self, context):
        bones = context.editable_bones
        for bone in bones:
            roll = bone.roll
            if roll == 0:
                continue
            closest = False
            sign = 1 if roll < 0 else -1
            while not closest:
                new_roll = roll + math.pi / 2.0 * sign
                if abs(roll) < abs(new_roll):
                    closest = True
                else:
                    roll = new_roll
            bone.roll = roll
        return {"FINISHED"}
