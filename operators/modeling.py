import os
import bpy

from .. import contexts
from .. import misc
from .. import io


class GenerateInvertedHullOperator(bpy.types.Operator):
    """Generate an inverted hull outline on selected meshes using the ink technique."""

    bl_idname = "object.generate_inverted_hull"
    bl_label = "Generate Inverted Hull"
    bl_description = (
        "Duplicate selected meshes with flipped normals and a solidify modifier to"
        " create an ink outline effect"
    )

    thickness: bpy.props.FloatProperty(
        name="Thickness",
        description="Thickness of the inverted hull outline",
        default=0.01,
        min=0.001,
        soft_max=0.1,
        step=0.1,
        precision=3,
    )  # pyright: ignore [reportInvalidTypeForm]

    suffix: bpy.props.StringProperty(
        name="Suffix",
        description="Suffix appended to the original object name for the hull duplicate",
        default="_Hull",
    )  # pyright: ignore [reportInvalidTypeForm]

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.mode == "OBJECT" and context.selected_objects:
            for obj in context.selected_objects:
                if obj.type == "MESH":
                    return True
        return False

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context) -> set[str]:
        hull_material = self._get_or_create_hull_material()
        mesh_objects = [obj for obj in context.selected_objects if obj.type == "MESH"]
        created = []
        for obj in mesh_objects:
            duplicate = misc.duplicate_object(obj)
            duplicate.name = f"{obj.name}{self.suffix}"
            duplicate.data.materials.clear()
            duplicate.data.materials.append(hull_material)
            modifier = duplicate.modifiers.new(name="Solidify", type="SOLIDIFY")
            modifier.thickness = self.thickness
            modifier.offset = -1.0
            modifier.use_flip_normals = True
            modifier.use_rim_only = True
            duplicate.visible_shadow = False
            duplicate.parent = obj
            duplicate.matrix_parent_inverse = obj.matrix_world.inverted()
            with contexts.SelectionContext():
                misc.select_objects([duplicate])
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.select_all(action="SELECT")
                bpy.ops.mesh.flip_normals()
                bpy.ops.object.mode_set(mode="OBJECT")
            created.append(duplicate)
        misc.select_objects(created)
        self.report(
            {"INFO"},
            f"Created {len(created)} inverted hull{'s' if len(created) != 1 else ''}.",
        )
        return {"FINISHED"}

    def _get_or_create_hull_material(self) -> bpy.types.Material:
        """Return the shared Hull material, creating it if it does not exist."""
        material = bpy.data.materials.get("Hull")
        if material:
            return material
        material = bpy.data.materials.new(name="Hull")
        material.use_nodes = True
        material.use_backface_culling = True
        nodes = material.node_tree.nodes
        nodes.clear()
        output_node = nodes.new(type="ShaderNodeOutputMaterial")
        output_node.location = (300, 0)
        bsdf_node = nodes.new(type="ShaderNodeBsdfPrincipled")
        bsdf_node.location = (0, 0)
        bsdf_node.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        material.node_tree.links.new(
            bsdf_node.outputs["BSDF"], output_node.inputs["Surface"]
        )
        return material


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

    save_settings: bpy.props.BoolProperty(
        name="Save Settings",
        description="Remember export settings in the blend file (glTF only).",
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
            joined_mesh = misc.join_objects(meshes)
            if joined_mesh:
                joined_exports.append(joined_mesh)
            exports = joined_exports
        dirname, basename = os.path.split(bpy.data.filepath)
        filename = os.path.join(dirname, f"{os.path.splitext(basename)[0]}")
        if self.file_format == "FBX":
            io.export_fbx(exports, filename + ".fbx")
        elif self.file_format == "GLTF":
            io.export_gltf(
                exports,
                filename + ".glb",
                animations=False,
                save_settings=self.save_settings,
            )
        if self.join_meshes and joined_mesh:
            misc.delete_objects([joined_mesh])
        return {"FINISHED"}


class ExportMeshesOperator(bpy.types.Operator):
    bl_idname = "object.export_meshes"
    bl_label = "Export Meshes"
    bl_description = "Export selected meshes to individual files"

    file_format: bpy.props.EnumProperty(
        name="File Format",
        description="The file format to export.",
        items=[
            ("FBX", "FBX", "FBX"),
            ("GLTF", "GLTF", "GLTF"),
        ],
    )  # pyright: ignore [reportInvalidTypeForm]

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

    save_settings: bpy.props.BoolProperty(
        name="Save Settings",
        description="Remember export settings in the blend file (glTF only).",
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
        extension = ".fbx" if self.file_format == "FBX" else ".glb"
        if self.remove_pre_existing:
            for existing_file in self.find_pre_existing(
                dirname, self.prefix, extension
            ):
                os.remove(existing_file)
        for object in selection:
            object_name = object.name.replace(".", self.separator)
            filename = os.path.join(
                dirname,
                f"{self.prefix}{self.separator}{object_name}{extension}",
            )
            if self.file_format == "FBX":
                io.export_fbx([object], filename)
            elif self.file_format == "GLTF":
                io.export_gltf(
                    [object],
                    filename,
                    animations=False,
                    save_settings=self.save_settings,
                )
        return {"FINISHED"}

    def find_pre_existing(
        self, dirname: str, prefix: str, extension: str
    ) -> list[str]:
        """Find export files corresponding to this scene file export."""
        files = []
        for basename in os.listdir(dirname):
            if basename.startswith(prefix) and basename.endswith(extension):
                files.append(os.path.join(dirname, basename))
        return files


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
                cut = misc.duplicate_object(source)
                misc.apply_all_modifiers(cut)
                cut.name = f"{source.name}_{cutter.name}"
                modifier = cut.modifiers.new(name="Subdivision", type="BOOLEAN")
                modifier.operation = "INTERSECT"
                modifier.object = cutter
                bpy.context.view_layer.objects.active = cut
                bpy.ops.object.modifier_apply(modifier=modifier.name)
                with contexts.SelectionContext():
                    misc.select_objects([cut])
                    with contexts.CursorContext():
                        bpy.context.scene.cursor.location = cutter.location
                        bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
                if len(cut.data.vertices) == 0:
                    bpy.data.objects.remove(cut)
                    continue
                cuts.append(cut)
            intersection = None
            if len(cuts) > 1:
                misc.select_objects(cuts)
                bpy.ops.object.join()
            elif len(cuts) == 1:
                bpy.context.view_layer.objects.active = cuts[0]
                intersection = cuts[0]
            if intersection:
                intersection = bpy.context.view_layer.objects.active
                intersection.name = f"{collection.name}.{cutter.name}"
                intersections.append(intersection)
        misc.select_objects(intersections)
        return {"FINISHED"}
