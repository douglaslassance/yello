import os
import logging
import subprocess
import bpy
import mathutils


def create_collection(name="Collection", find_existing=True):
    if name not in bpy.data.collections:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
    else:
        collection = bpy.data.collections[name]
    return collection


def add_object_to_collection(obj, collection):
    if obj.name not in bpy.data.collections[collection.name]:
        bpy.data.collections[collection.name].objects.link(obj)


def remove_object_from_all_collections(obj):
    for col in obj.users_collection:
        col.objects.unlink(obj)


def map_values(value, old_min, old_max, new_max, new_min):
    return (((value - old_min) * (new_max - new_min)) / (old_max - old_min)) + new_min


def run_command(command: list):
    process = subprocess.Popen(
        command,
        cwd=os.path.dirname(filename),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    output, err = process.communicate()
    if output:
        logging.warning(output)
    if err:
        logging.error(err)
    return process.returncode


def lock_file(filename):
    """Lock a file using Git LFS.

    Args:
        filename (string): The filename of the file to lock.
    """
    if not os.path.exists(filename):
        return False
    command = ["git", "lfs", "lock", ".\\{}".format(os.path.basename(filename))]
    return run_command(command)


def has_conflict(filename):
    """Check if Gitarmony says we'd have a conflicting touching this file.

    Args:
        filename (string): The filename of the file to check conflict for.
    """
    if not os.path.exists(filename):
        return False
    command = ["gitarmony", "has-conflict", ".\\{}".format(os.path.basename(filename))]
    return run_command(command)


def make_writable(filename):
    """Make file writable safely using Gitarmony.

    Args:
        filename (string): The filename of the file to make writable.
    """
    if not os.path.exists(filename):
        return False
    command = ["gitarmony", "make-writable", ".\\{}".format(os.path.basename(filename))]
    return run_command(command)


def is_ancestor_bone(ancestor, descendant):
    """Returns whether a bone is an ancestor (a remote parent) of another one.

    Args:
        ancestor ([type]): [description]
        descendant ([type]): [description]

    Returns:
        [type]: [description]
    """
    bone = descendant
    while bone.parent:
        if bone.parent == ancestor:
            return True
        bone = bone.parent
    return False


def get_projected_vector(vector: mathutils.Vector, normal: mathutils.Vector):
    """[summary]

    Args:
        vector (mathutils.Vector): The vector to project.
        normal (mathutils.Vector): The normal of the plane to project onto. Expects a normalized vector.
    """
    return vector - normal * vector.dot(normal)
