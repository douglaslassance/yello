"""Test setup that lets rigging.py import without Blender or Ollama.

rigging.py imports bpy, bmesh, mathutils and evaluates annotations such as
bpy.types.Object at import time, and it reaches its siblings through relative
imports (from . import dracula / ollama). This module installs lightweight
stubs for the Blender packages when they are not available and loads rigging.py
inside a synthetic package so the relative imports resolve. Tests can then
import the real classification and matching logic offline:

    from yello_ext import rigging
"""

import importlib
import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_NAME = "yello_ext"


class _StubTypes(types.ModuleType):
    """Stand-in for bpy.types that fabricates a class for any attribute.

    rigging.py evaluates annotations like bpy.types.Object at import time, so
    every referenced name must resolve to a real class for expressions such as
    ``bpy.types.Object | None`` to work.
    """

    def __getattr__(self, name):
        stub = type(name, (), {})
        setattr(self, name, stub)
        return stub


def _install_blender_stubs():
    """Register minimal bpy/bmesh/mathutils modules if they cannot be imported."""
    if "bpy" not in sys.modules:
        try:
            importlib.import_module("bpy")
        except ImportError:
            bpy = types.ModuleType("bpy")
            bpy.types = _StubTypes("bpy.types")
            bpy.props = types.ModuleType("bpy.props")
            sys.modules["bpy"] = bpy
    if "bmesh" not in sys.modules:
        try:
            importlib.import_module("bmesh")
        except ImportError:
            sys.modules["bmesh"] = types.ModuleType("bmesh")
    if "mathutils" not in sys.modules:
        try:
            importlib.import_module("mathutils")
        except ImportError:
            mathutils = types.ModuleType("mathutils")
            mathutils.Vector = type("Vector", (), {})
            sys.modules["mathutils"] = mathutils


def _load_submodule(name: str):
    """Load repo_root/<name>.py as PACKAGE_NAME.<name> and return it."""
    full_name = f"{PACKAGE_NAME}.{name}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    spec = importlib.util.spec_from_file_location(full_name, REPO_ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = PACKAGE_NAME
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


def _load_rigging():
    """Load rigging.py under a synthetic package so relative imports resolve."""
    if PACKAGE_NAME not in sys.modules:
        package = types.ModuleType(PACKAGE_NAME)
        package.__path__ = [str(REPO_ROOT)]
        sys.modules[PACKAGE_NAME] = package
    _load_submodule("dracula")
    _load_submodule("ollama")
    return _load_submodule("rigging")


_install_blender_stubs()
_load_rigging()
