import copy
import bpy


class CursorContext:
    """A context that will restore the original location of the cursor on exit."""

    def __init__(self) -> None:
        self.location = copy.copy(bpy.context.scene.cursor.location)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        bpy.context.scene.cursor.location = self.location


class ModeContext:
    """A context that will switch mode and revert to the previous mode on exit."""

    def __init__(self, mode: str) -> None:
        self._mode = mode
        self.mode = bpy.context.mode

    def __enter__(self):
        bpy.ops.object.mode_set(mode=self._mode)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        bpy.ops.object.mode_set(mode=self.mode.split("_")[0])


class DisabledConstraintsContext:
    """A context that mutes all constraints on an object's pose bones and restores them on exit."""

    def __init__(self, obj) -> None:
        self.obj = obj
        self.muted = {
            (bone.name, constraint.name): constraint.mute
            for bone in obj.pose.bones
            for constraint in bone.constraints
        }

    def __enter__(self):
        for bone in self.obj.pose.bones:
            for constraint in bone.constraints:
                constraint.mute = True
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        for bone in self.obj.pose.bones:
            for constraint in bone.constraints:
                constraint.mute = self.muted[(bone.name, constraint.name)]


class VisibleContext:
    """A context that will restore the visibility state of an object on exit."""

    def __init__(self, obj) -> None:
        self.obj = obj
        self.hide_viewport = obj.hide_viewport
        self.hide = obj.hide_get()

    def __enter__(self):
        self.obj.hide_viewport = False
        self.obj.hide_set(False)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.obj.hide_viewport = self.hide_viewport
        self.obj.hide_set(self.hide)


class SelectionContext:
    """A context that will restore the original selection on exit."""

    def __init__(self) -> None:
        self.selected = [obj for obj in bpy.context.view_layer.objects.selected]
        self.active = bpy.context.view_layer.objects.active

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
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
