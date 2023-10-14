# yello

Yello is Playsthetic's integration inside Blender. It adds functionalities that should make things more efficient for our general tasks within the application. You may wonder where the name Yello comes from. Blender is named after one song of the Swiss electronic band [Yello](https://en.wikipedia.org/wiki/Yello).

## Pre-requisites

- Blender >=3.6

## Installation

Download Yellow following [this link](https://github.com/playsthetic/yello/archive/refs/heads/master.zip).
Once downloaded, simply install the plugin following [the official Blender instructions](https://docs.blender.org/manual/en/latest/editors/preferences/addons.html#installing-add-ons).

## Usage

The plugin introduces a couple automated event handlers for opening or saving files.
Most of functionalities will be found in the "Yello" tab on the right side of each 3D Viewport.
Buttons feature tooltips so you can have an idea of what they do.

## Development

It's recommanded to develop using [Visual Studio Code](https://code.visualstudio.com/) and the incredible [Blender Development](https://marketplace.visualstudio.com/items?itemName=JacquesLucke.blender-development) plugin. For proper linting and auto-complete, point your interpreter to a Python 3.10 virtual environment and install `fake-bpy` using `pip install fake-bpy-module-latest`.
