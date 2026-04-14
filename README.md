# yello

Yello aims to make common Blender operations more efficient. You may wonder where the name Yello comes from. Blender is named after one song of the Swiss electronic band [Yello](https://en.wikipedia.org/wiki/Yello).

## Pre-requisites

- Blender >=3.6

## Installation

Drag and drop [this link](https://github.com/playsthetic/yello/archive/refs/heads/main.zip) on Blender's main window.

## Usage

Most of features will be found in the `Yello` tab on the right side of each 3D Viewport.
The plugin introduces a couple automated event handlers for opening or saving files.

## Features

### File
- **Make Writable**: Perform a Gitalong make-writable on the current file.
- **Open Containing Folder**: Open the folder containing the current file in the OS file browser.

### Modeling
- **Generate Inverted Hull**: Add an inverted-hull outline effect to selected meshes.
- **Slice Meshes with Collection**: Boolean-slice meshes using objects from a collection.
- **Export Mesh**: Export selected meshes and armatures to a single FBX.
- **Export Meshes**: Export selected meshes to individual FBX files.

### Rigging
- **Conform Bone Name**: Rename bones to use the `.L` / `.R` suffix convention, normalising any other suffix and its separator.
- **Create Bone Aligned Object**: Create an empty aligned to the active bone in pose mode.
- **Distribute Bones Evenly**: Straighten a chain and distribute bone lengths evenly.
- **Align Bones**: Align a bone chain to the plane formed by its first and last bone.
- **Align Bone Rolls**: Align the rolls of a selected bone chain.
- **Minimize Bone Roll**: Rotate the roll of selected bones by 90° steps until it is as close to zero as possible.
- **Generate Twist Bones**: Generate twist bone chains parented to the selected bones.
- **Generate Blend Bone**: Generate a blend bone that interpolates between two bones.
- **Transfer Weights**: Transfer vertex weights from one mesh to another.
- **Generate Control Rig**: Use Ollama to classify bones by anatomical role and generate a full control rig with IK legs, spline-IK spine, and FK arms/fingers. Control shapes are scaled adaptively from the character's skinned geometry.
- **Remove Control Rig**: Remove all control bones and their constraints from the armature.
- **Retarget Animation**: Match a source armature's bones to this skeleton's control rig using Ollama, bake the animation to keyframes, then remove the constraints.

### Animation
- **Export Animation**: Export the selection to an animated FBX.
- **Export Animated Mesh**: Export selected animated meshes to Alembic.
- **Export Actions**: Export all actions on the selected armature to GLB, baking deform bone transforms and excluding control rig bones.
- **Transfer Animation**: Transfer actions to selected armatures using Ollama-based bone matching.

### Shading
- **Smooth Normals**: Project normals from a smoothed copy of the mesh for a clean shading look.
- **Reset Normals**: Remove projected normals from the model.
- **Set Mesh Color Channel**: Set a specific vertex color channel on selected meshes.

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
