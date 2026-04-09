import os
import subprocess
import platform
import bpy

from .. import misc


class MakeWritableOperator(bpy.types.Operator):
    bl_idname = "object.make_writable"
    bl_label = "Make Writable"
    bl_description = "Perform a Gitalong make writable on the current file"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(bpy.data.filepath)

    def execute(self, context: bpy.types.Context) -> set[str]:
        misc.make_writable(bpy.data.filepath)
        return {"FINISHED"}


class OpenContainingFolderOperator(bpy.types.Operator):
    bl_idname = "object.open_containing_folder"
    bl_label = "Open Containing Folder"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(bpy.data.filepath)

    def execute(self, context: bpy.types.Context) -> set[str]:
        filepath = bpy.data.filepath
        if platform.system() == "Windows":
            subprocess.Popen(["explorer", "/select,", filepath])
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-R", filepath])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(filepath)])
        return {"FINISHED"}
