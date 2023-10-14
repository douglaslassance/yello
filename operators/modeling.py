import bpy

from .. import functions
from .. import contexts


class GenerateMeshIntersectionsOperator(bpy.types.Operator):
    bl_idname = "object.slice_meshes_with_collection"
    bl_label = "Generate mesh intersections"
    bl_description = (
        "Generate intersection meshes between selected meshes and a collection of mesh."
    )

    @classmethod
    def poll(cls, context):
        if context.mode == "OBJECT" and context.selected_objects:
            return True
        return False

    def execute(self, context):
        sources = bpy.context.selected_objects
        collection = bpy.context.collection
        collection_objects = collection.objects
        if set(sources).intersection(collection_objects):
            self.report(
                {"ERROR"},
                "Selected meshes cannot be in the collection of meshes to intersect with",
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
                slice = functions.duplicate_object(source)
                slice.name = f"{source.name}_{cutter.name}"
                modifier = slice.modifiers.new(name="Subdivision", type="BOOLEAN")
                modifier.operation = "INTERSECT"
                modifier.object = cutter
                bpy.context.view_layer.objects.active = slice
                bpy.ops.object.modifier_apply(modifier=modifier.name)
                with contexts.CursorContext():
                    bpy.context.scene.cursor.location = cutter.location
                    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
                cuts.append(slice)
            intersection = None
            if len(cuts) > 1:
                functions.select_objects(cuts)
                bpy.ops.object.join()
                intersection = bpy.context.view_layer.objects.active
                intersection.name = f"{collection.name}.{cutter.name}"
            elif len(cuts) == 1:
                intersection = cuts[0]
            if intersection:
                intersections.append(intersection)
        functions.select_objects(intersections)
        return {"FINISHED"}
