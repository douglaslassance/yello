import contextlib
import bpy


class SelectionContext:
    """A context that will restore the original selection on exit."""

    def __enter__(self, *args, **kwargs):
        self.selected = [obj for obj in bpy.context.view_layer.objects.selected]
        self.active = bpy.context.view_layer.objects.active
        return self

    def __exit__(self, *args, **kwargs):
        bpy.ops.object.select_all(action="DESELECT")
        for obj in self.selected:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = self.active