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
