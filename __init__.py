# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import os
import bpy
from bpy.app.handlers import persistent
from . import functions
from . import auto_load

bl_info = {
    "name": "Yello",
    "author": "Douglas Lassance",
    "description": "Playsthetic integration in Blender.",
    "blender": (2, 92, 0),
    "version": (0, 1, 0),
    "location": "View3D",
    "warning": (
        "To take advantage of all functionalities Git LFS "
        "should be installed on your system."
    ),
    "category": "Integration",
}

auto_load.init()


@persistent
def save_pre_handler(*args, **kwargs):
    functions.lock_file(bpy.data.filepath)


def register():
    bpy.app.handlers.save_pre.append(save_pre_handler)
    auto_load.register()


def unregister():
    bpy.app.handlers.save_pre.remove(save_pre_handler)
    auto_load.unregister()
