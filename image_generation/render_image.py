# Original version copyright 2017-present, Facebook, Inc. All rights reserved.
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.
# Heavy modifications copyright 2023 Brain Engineering Lab at Dartmouth. Same license as original.
# see README.md for instructions on running this script
from __future__ import print_function
import json
import os


INSIDE_BLENDER = True
try:
    import bpy
    import bpy_extras
    from mathutils import Vector
except ImportError as e:
    INSIDE_BLENDER = False

    
def main():
    assert os.path.exists("img2render.txt")
    with open("img2render.txt", "r") as f:
        img2render = int(f.read().strip())
    
    assert os.path.exists("split.txt")
    with open("split.txt", "r") as f:
        split = f.read().strip()

    with open("../output/customclevr_" + split + "_config.json", "r") as f:
        config = json.load(f)

    # set render arguments so we can get pixel coordinates later
    bpy.ops.wm.open_mainfile(filepath=config["base_scene_blendfile"]) # load the main blendfile
    load_materials(config["material_dir"]) # load materials
    render_args = bpy.context.scene.render
    render_args.engine = "CYCLES" # we use functionality specific to the CYCLES renderer so BLENDER_RENDER cannot be used
    render_args.resolution_x = 320 # the width (in pixels) for the rendered images
    render_args.resolution_y = 240 # the height (in pixels) for the rendered images
    render_args.resolution_percentage = 100
    render_args.tile_x = 512 # the tile size to use for rendering
    render_args.tile_y = 512 # the tile size to use for rendering
    # ^ render tile size should not affect the quality of the rendered image but may affect the speed;
    # CPU-based rendering may achieve better performance using smaller tile sizes,
    # while larger tile sizes may be optimal for GPU-based rendering.
    bpy.data.worlds["World"].cycles.sample_as_light  = True
    bpy.context.scene.cycles.blur_glossy             = 2.0
    bpy.context.scene.cycles.samples                 = 512 # the number of samples to use when rendering. Larger values will result in nicer images but will cause rendering to take longer.
    bpy.context.scene.cycles.transparent_min_bounces = 8 # the minimum number of bounces to use for rendering
    bpy.context.scene.cycles.transparent_max_bounces = 8 # the maximum number of bounces to use for rendering
    # for GPU (doesn't work rn)
    # bpy.context.scene.cycles.device = "GPU"
    # cycles_prefs = bpy.context.user_preferences.addons["cycles"].preferences
    # cycles_prefs.compute_device_type = "CUDA"
    
    # render
    img_path   = "../output/images/customclevr_" + config["split"] + "_%06d.png" % img2render
    blend_path = "../output/blendfiles/customclevr_" + config["split"] + "_%06d.blend" % img2render
    print("rendering " + config["split"] + " image " + str(img2render) + " of " + str(config["n_images"]) + "...")
    render_scene(config, img2render, img_path, blend_path)


def render_scene(config:dict, imgidx:int, img_path:str, blend_path:str):
    # set camera position
    bpy.data.objects["Camera"].location[0] = config["camera_location"][0]
    bpy.data.objects["Camera"].location[1] = config["camera_location"][1]
    bpy.data.objects["Camera"].location[2] = config["camera_location"][2]
    if config["camera_jitter"] > 0:
        for i in range(3):
            bpy.data.objects["Camera"].location[i] += config["camera_offset"][imgidx][i]

    # prepare to add objects
    color_name_to_rgba = {}
    for name,rgb in config["colors"].items():
        color_name_to_rgba[name] = [float(c) / 255.0 for c in rgb] + [1.0]
    
    # add objects to the current blender scene
    objnames = [[]]*config["n_objects"]
    for objidx in range(config["n_objects"]):
        x = config["pos_planex"][imgidx][objidx]
        y = config["pos_planey"][imgidx][objidx]
        objnames[objidx] = add_object(config["shape_dir"], config["shape_name"][imgidx][objidx], config["r"][imgidx][objidx], x, y, config["theta"][imgidx][objidx])

        rgba = color_name_to_rgba[config["color_name"][imgidx][objidx]]
        add_material(config["mat_name"][imgidx][objidx], Color=rgba)

    # add random jitter to lamp positions
    for i in range(3):
        if config["key_light_jitter"] > 0:
            bpy.data.objects["Lamp_Key"].location[i] += config["key_light_offset"][imgidx][i]
        if config["fill_light_jitter"] > 0:
            bpy.data.objects["Lamp_Fill"].location[i] += config["fill_light_offset"][imgidx][i]
        if config["back_light_jitter"] > 0:
            bpy.data.objects["Lamp_Back"].location[i] += config["back_light_offset"][imgidx][i]

    # render the scene
    render_args = bpy.context.scene.render
    render_args.filepath = img_path
    while True:
        try:
            bpy.ops.render.render(write_still=True)
            break
        except Exception as e:
            print(e)
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)

    # remove objects
    for name in objnames:
        objs = bpy.data.objects
        objs.remove(objs[name], do_unlink=True) # delete object based on name


def add_object(object_dir, name, scale, x, y, theta) -> str:
    """
    Load an object from a file. We assume that in the directory object_dir, there
    is a file named "$name.blend" which contains a single object named "$name"
    that has unit size and is centered at the origin.

    - scale: scalar giving the size that the object should be in the scene
    - x,y: the coordinates on the ground plane where the object should be placed
    """
    # first figure out how many of this object are already in the scene so we can give the new object a unique name
    count = 0
    for obj in bpy.data.objects:
        if obj.name.startswith(name):
            count += 1

    filename = os.path.join(object_dir, name + ".blend", "Object", name)
    bpy.ops.wm.append(filename=filename)

    # give it a new name to avoid conflicts
    new_name = "%s_%d" % (name, count)
    bpy.data.objects[name].name = new_name

    # set the new object as active, then rotate, scale, and translate it
    bpy.context.view_layer.objects.active = bpy.data.objects[new_name]
    # or (https://github.com/IBM/photorealistic-blocksworld/commit/3908f36d117cfb2b5cc4a0c50e7267ef576376bc):
    # o.select_set(state=True, view_layer=bpy.context.view_layer)
    # bpy.context.view_layer.objects.active = o
    bpy.context.object.rotation_euler[2] = theta
    bpy.ops.transform.resize(value=(scale, scale, scale))
    bpy.ops.transform.translate(value=(x, y, scale))
    # bpy.data.collections["collection0"].objects.link(bpy.data.objects[new_name])
    return new_name


def load_materials(material_dir):
    """
    Load materials from a directory. We assume that the directory contains .blend
    files with one material each. The file X.blend has a single NodeTree item named
    X; this NodeTree item must have a "Color" input that accepts an RGBA value.
    """
    for fn in os.listdir(material_dir):
        if not fn.endswith(".blend"):
            continue
        name = os.path.splitext(fn)[0]
        filepath = os.path.join(material_dir, fn, "NodeTree", name)
        bpy.ops.wm.append(filename=filepath)


def add_material(name, **properties):
    """
    Create a new material and assign it to the active object. "name" should be the
    name of a material that has been previously loaded using load_materials.
    """
    assert type(name) is str

    # figure out how many materials are already in the scene
    mat_count = len(bpy.data.materials)

    # create a new material; it is not attached to anything and it will be called "Material"
    bpy.ops.material.new()

    # Get a reference to the material we just created and rename it;
    # then the next time we make a new material it will still be called
    # "Material" and we will still be able to look it up by name
    mat = bpy.data.materials["Material"]
    mat.name = "Material_%d" % mat_count

    # attach the new material to the active object
    obj = bpy.context.active_object
    assert len(obj.data.materials) == 0 # make sure it doesn't already have materials
    obj.data.materials.append(mat)

    # Add a new GroupNode to the node tree of the active material,
    # and copy the node tree from the preloaded node group to the new group node.
    # This copying seems to happen by-value, so we can create multiple
    # materials of the same type without them clobbering each other
    group_node = mat.node_tree.nodes.new("ShaderNodeGroup")
    group_node.node_tree = bpy.data.node_groups[name]

    # find and set the "Color" input of the new group node
    for inp in group_node.inputs:
        if inp.name in properties:
            inp.default_value = properties[inp.name]

    # find the output node of the new material
    output_node = None
    for n in mat.node_tree.nodes:
        if n.name == "Material Output":
            output_node = n
            break
    assert output_node is not None

    # wire the output of the new group node to the input of the MaterialOutput node
    mat.node_tree.links.new(group_node.outputs["Shader"], output_node.inputs["Surface"])


if __name__ == "__main__":
    if INSIDE_BLENDER:
        main() # run normally
    else:
        print("this script is intended to be called by blender - see README.md")
