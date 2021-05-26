import bpy
import mathutils

from .. import functions
from ..contexts import CursorContext


class AlignBoneRollsOperator(bpy.types.Operator):
    bl_idname = "editable_bones.align_bone_rolls"
    bl_label = "Align bone rolls"

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
            self.iterations = bpy.context.scene.world[self._count_key]
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        bones = context.editable_bones
        for bone in bones:
            length = bone.length / float(self.count + 1)
            direction = (bone.tail - bone.head).normalized()
            previous = bone
            edit_bones = context.object.data.edit_bones
            for i in range(self.count):
                number = i + 1
                splits = bone.name.split(".")
                name = ".".join(splits[:-1] + ["{:03d}".format(number), splits[-1]])
                twist = edit_bones.new(name)
                twist.head = bone.head + direction * length * number
                twist.tail = twist.head + direction * length
                # TODO: calculate the roll interpolation been the root bone and next.
                # For now we are matching the parent on all twists bones.
                twist.roll = bone.roll
                twist.parent = previous
                if twist.head == previous.tail:
                    twist.use_connect = True
                previous = twist
        bpy.context.scene.world[self._count_key] = self.count
        return {"FINISHED"}
