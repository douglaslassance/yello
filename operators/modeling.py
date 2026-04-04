import os
import bpy

from .. import functions
from .. import contexts


class ExportMeshOperator(bpy.types.Operator):
    bl_idname = "object.export_mesh"
    bl_label = "Export Mesh"
    bl_description = "Export selected meshes and armatures to a single FBX"

    file_format: bpy.props.EnumProperty(
        name="File Format",
        description="The file format to export.",
        items=[
            ("FBX", "FBX", "FBX"),
            ("GLTF", "GLTF", "GLTF"),
        ],
    )  # pyright: ignore [reportInvalidTypeForm]

    join_meshes: bpy.props.BoolProperty(
        name="Join Meshes",
        description="Join selected meshes in a single mesh.",
    )  # pyright: ignore [reportInvalidTypeForm]

    include_children: bpy.props.BoolProperty(
        name="Include Children",
        description="Will add all children from selected parents.",
    )  # pyright: ignore [reportInvalidTypeForm]

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if bpy.data.filepath:
            if context.mode and context.selected_objects:
                return True
        return False

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context) -> set[str]:
        exports = bpy.context.selected_objects
        if self.include_children:
            for obj in bpy.context.selected_objects:
                for child in obj.children:
                    if child not in exports:
                        exports.append(child)
        if self.join_meshes:
            meshes = []
            joined_exports = []
            for obj in exports:
                if obj.type == "MESH":
                    meshes.append(obj)
                else:
                    joined_exports.append(obj)
            joined_mesh = functions.join_objects(meshes)
            if joined_mesh:
                joined_exports.append(joined_mesh)
            exports = joined_exports
        dirname, basename = os.path.split(bpy.data.filepath)
        filename = os.path.join(dirname, f"{os.path.splitext(basename)[0]}")
        if self.file_format == "FBX":
            functions.export_fbx(exports, filename + ".fbx")
        elif self.file_format == "GLTF":
            functions.export_gltf(exports, filename + ".glb", animations=False)
        if self.join_meshes and joined_mesh:
            functions.delete_objects([joined_mesh])
        return {"FINISHED"}


class ExportMeshesOperator(bpy.types.Operator):
    bl_idname = "object.export_meshes"
    bl_label = "Export Meshes"
    bl_description = "Export selected meshes to individual files"

    prefix: bpy.props.StringProperty(
        name="Prefix",
        description="The prefix for this file's name",
    )  # pyright: ignore [reportInvalidTypeForm]

    separator: bpy.props.StringProperty(
        name="Separator",
        default="_",
        description="The object name separator to use",
    )  # pyright: ignore [reportInvalidTypeForm]

    remove_pre_existing: bpy.props.BoolProperty(
        name="Remove Pre-Existing Files",
        default=False,
        description="Remove pre-existing FBX files that match this export prefix",
    )  # pyright: ignore [reportInvalidTypeForm]

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if bpy.data.filepath:
            if context.mode and context.selected_objects:
                return True
        return False

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        basename = os.path.basename(bpy.data.filepath)
        self.prefix = os.path.splitext(basename)[0]
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context) -> set[str]:
        selection = bpy.context.selected_objects
        dirname, basename = os.path.split(bpy.data.filepath)
        if self.remove_pre_existing:
            for fbx_file in self.find_pre_existing(dirname, self.prefix):
                os.remove(fbx_file)
        for object in selection:
            object_name = object.name.replace(".", self.separator)
            filename = os.path.join(
                dirname,
                f"{self.prefix}{self.separator}{object_name}.fbx",
            )
            functions.export_fbx([object], filename)
        return {"FINISHED"}

    def find_pre_existing(self, dirname: str, prefix: str) -> list[str]:
        """Find FBX files corresponding to this scene file export."""
        fbx_files = []
        for basename in os.listdir(dirname):
            if basename.startswith(prefix) and basename.endswith(".fbx"):
                fbx_files.append(os.path.join(dirname, basename))
        return fbx_files


class GenerateMeshIntersectionsOperator(bpy.types.Operator):
    bl_idname = "object.slice_meshes_with_collection"
    bl_label = "Generate Mesh Intersections"
    bl_description = (
        "Generate intersection meshes between selected meshes and a collection of mesh."
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.mode == "OBJECT" and context.selected_objects:
            return True
        return False

    def execute(self, context: bpy.types.Context) -> set[str]:
        sources = bpy.context.selected_objects
        collection = bpy.context.collection
        collection_objects = collection.objects
        if set(sources).intersection(collection_objects):
            self.report(
                {"ERROR"},
                "Selected meshes cannot be in the collection of meshes to intersect with.",
            )
            return {"FINISHED"}
        intersections = []
        for cutter in collection_objects:
            if not cutter.type == "MESH":
                continue
            cuts = []
            for source in sources:
                if not source.type == "MESH":
                    continue
                cut = functions.duplicate_object(source)
                functions.apply_all_modifiers(cut)
                cut.name = f"{source.name}_{cutter.name}"
                modifier = cut.modifiers.new(name="Subdivision", type="BOOLEAN")
                modifier.operation = "INTERSECT"
                modifier.object = cutter
                bpy.context.view_layer.objects.active = cut
                bpy.ops.object.modifier_apply(modifier=modifier.name)
                with contexts.SelectionContext():
                    functions.select_objects([cut])
                    with contexts.CursorContext():
                        bpy.context.scene.cursor.location = cutter.location
                        bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
                if len(cut.data.vertices) == 0:
                    bpy.data.objects.remove(cut)
                    continue
                cuts.append(cut)
            intersection = None
            if len(cuts) > 1:
                functions.select_objects(cuts)
                bpy.ops.object.join()
            elif len(cuts) == 1:
                bpy.context.view_layer.objects.active = cuts[0]
                intersection = cuts[0]
            if intersection:
                intersection = bpy.context.view_layer.objects.active
                intersection.name = f"{collection.name}.{cutter.name}"
                intersections.append(intersection)
        functions.select_objects(intersections)
        return {"FINISHED"}
