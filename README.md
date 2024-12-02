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

### Requirements

- Python >=3.10
- Visual Studio Code

Open the project with Visual Studio Code and make sure to install the recommended extensions, most importantly [Blender Development](https://marketplace.visualstudio.com/items?itemName=JacquesLucke.blender-development). Once done, open a Visual Studio Code terminal and run:

```bash
python -m venv .venv
```

Visual Studio Code should now pickup the newly created Python virtual environment. To install the Python package dependencies, open a new terminal and run:

```bash
pip install -r requirements.txt
```

Run the `Blender: Start` Visual Studio Command to launch Blender with the debugger.
