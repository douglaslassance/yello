import copy
from types import TracebackType
from typing import Self

import bpy


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
