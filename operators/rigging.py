import bpy
import mathutils

from .. import functions
from ..contexts import CursorContext


class AlignBoneRollsOperator(bpy.types.Operator):
    bl_idname = "editable_bones.align_bone_rolls"
    bl_label = "Align bone rolls"
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


class DistributeBonesEvenlyOperator(bpy.types.Operator):
    bl_idname = "editable_bones.distribute_bones_evenly"
    bl_label = "Distribute bones evenly"
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


class AlignBonesOperator(bpy.types.Operator):
    bl_idname = "editable_bones.align_bones"
    bl_label = "Align bones"
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


class GenerateTwistBonesOperator(bpy.types.Operator):
    _count_key = "yello_generate_twist_bones_count"

    bl_idname = "editable_bones.generate_twist_bones"
    bl_label = "Generate twist bones"
    bl_description = "Generate twist bone chains parented to the selected bones."

    count = bpy.props.IntProperty(name="Count", default=3)

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
        bpy.ops.object.mode_set(mode="POSE")
        for created in createds:
            bpy.context.object.pose.bones[created].bone.hide = True
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.context.scene.world[self._count_key] = self.count
        return {"FINISHED"}


class GenerateBlendBoneOperator(bpy.types.Operator):
    bl_idname = "editable_bones.generate_blend_bone"
    bl_label = "Generate blend bone"
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
        splits = bone.name.split(".")
        edit_bones = context.object.data.edit_bones
        new_bone = edit_bones.new(".".join(splits[:-1] + ["Blend", splits[-1]]))
        new_bone.envelope_weight = bones[-1].envelope_weight
        new_bone.envelope_distance = bones[-1].envelope_distanc
        new_bone.head_radius = bones[-1].head_radius
        new_bone.tail_radius = bones[-1].tail_radius
        new_bone.hide = True
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
        new_bone.tail = tail.normalized() * 0.05 + new_bone.head
        new_bone.parent = bones[0]
        # TODO: There is still some imperfection with this roll calculation.
        normal = parent_bone_vector.cross(child_bone_vector)
        bpy.ops.armature.select_all(action="DESELECT")
        with CursorContext():
            bpy.context.scene.cursor.location = normal + new_bone.head
            bpy.context.object.data.edit_bones.active = new_bone
            bpy.ops.armature.calculate_roll(type="CURSOR")
        return {"FINISHED"}
