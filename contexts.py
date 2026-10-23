import copy
from types import TracebackType
from typing import Self

import bpy

TRANSFORM_PROPERTY_NAMES = (
    "location",
    "rotation_quaternion",
    "rotation_euler",
    "rotation_axis_angle",
    "scale",
)


class AnimationContext:
    """A context that will restore an object's action, transform and pose on exit."""

    def __init__(self, obj: bpy.types.Object) -> None:
        self.obj = obj
        animation_data = obj.animation_data
        self.action = animation_data.action if animation_data else None
        self.action_slot = getattr(animation_data, "action_slot", None)
        self.transform = self._read_transform(obj)
        self.pose = (
            {bone.name: self._read_transform(bone) for bone in obj.pose.bones}
            if obj.pose
            else {}
        )

    @staticmethod
    def _read_transform(
        target: bpy.types.Object | bpy.types.PoseBone,
    ) -> dict[str, tuple[float, ...]]:
        return {name: tuple(getattr(target, name)) for name in TRANSFORM_PROPERTY_NAMES}

    @staticmethod
    def _write_transform(
        target: bpy.types.Object | bpy.types.PoseBone,
        transform: dict[str, tuple[float, ...]],
    ) -> None:
        for name, value in transform.items():
            setattr(target, name, value)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        animation_data = self.obj.animation_data
        if animation_data is not None:
            animation_data.action = self.action
            if self.action is not None and hasattr(animation_data, "action_slot"):
                animation_data.action_slot = self.action_slot
        self._write_transform(self.obj, self.transform)
        for name, transform in self.pose.items():
            bone = self.obj.pose.bones.get(name)
            if bone is not None:
                self._write_transform(bone, transform)


class CursorContext:
    """A context that will restore the original location of the cursor on exit."""

    def __init__(self) -> None:
        self.location = copy.copy(bpy.context.scene.cursor.location)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        bpy.context.scene.cursor.location = self.location


class FrameRangeContext:
    """A context that will restore the scene frame range on exit."""

    def __init__(self) -> None:
        scene = bpy.context.scene
        self.frame_start = scene.frame_start
        self.frame_end = scene.frame_end

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        scene = bpy.context.scene
        scene.frame_start = self.frame_start
        scene.frame_end = self.frame_end


class ModeContext:
    """A context that will switch mode and revert to the previous mode on exit."""

    def __init__(self, mode: str) -> None:
        self._mode = mode
        self.mode = bpy.context.mode

    def __enter__(self) -> Self:
        bpy.ops.object.mode_set(mode=self._mode)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        bpy.ops.object.mode_set(mode=self.mode.split("_")[0])


class DisabledConstraintsContext:
    """A context that mutes all constraints on an object's pose bones and restores them on exit."""

    def __init__(self, obj: bpy.types.Object) -> None:
        self.obj = obj
        self.muted: dict[tuple[str, str], bool] = {
            (bone.name, constraint.name): constraint.mute
            for bone in obj.pose.bones
            for constraint in bone.constraints
        }

    def __enter__(self) -> Self:
        for bone in self.obj.pose.bones:
            for constraint in bone.constraints:
                constraint.mute = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        for bone in self.obj.pose.bones:
            for constraint in bone.constraints:
                constraint.mute = self.muted[(bone.name, constraint.name)]


class MutedFcurvesContext:
    """A context that mutes the given fcurves and restores their mute state on exit."""

    def __init__(self, fcurves: list[bpy.types.FCurve]) -> None:
        self.muted: list[tuple[bpy.types.FCurve, bool]] = [
            (fcurve, fcurve.mute) for fcurve in fcurves
        ]

    def __enter__(self) -> Self:
        for fcurve, _ in self.muted:
            fcurve.mute = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        for fcurve, mute in self.muted:
            fcurve.mute = mute


class VisibleContext:
    """A context that will restore the visibility state of an object on exit."""

    def __init__(self, obj: bpy.types.Object) -> None:
        self.obj = obj
        self.hide_viewport: bool = obj.hide_viewport
        self.hide: bool = obj.hide_get()

    def __enter__(self) -> Self:
        self.obj.hide_viewport = False
        self.obj.hide_set(False)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        self.obj.hide_viewport = self.hide_viewport
        self.obj.hide_set(self.hide)


class SelectionContext:
    """A context that will restore the original selection on exit."""

    def __init__(self) -> None:
        self.selected: list[bpy.types.Object] = [
            obj for obj in bpy.context.view_layer.objects.selected
        ]
        self.active: bpy.types.Object | None = bpy.context.view_layer.objects.active

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in self.selected:
            try:
                obj.select_set(True)
            except ReferenceError:
                pass
        try:
            bpy.context.view_layer.objects.active = self.active
        except ReferenceError:
            pass
