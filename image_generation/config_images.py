# Original version copyright 2017-present, Facebook, Inc. All rights reserved.
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.
# Heavy modifications copyright 2023 Brain Engineering Lab at Dartmouth. Same license as original.
# see README.md for instructions on running this script
from __future__ import print_function
import math
import random
import json
import os
import copy


INSIDE_BLENDER = True
try:
    import bpy
    import bpy_extras
    from mathutils import Vector
except ImportError as e:
    INSIDE_BLENDER = False

    
def main():
    for split in {"trnsimple","tstsimple"}:
        config = generate_config(split)

        # set render arguments so we can get pixel coordinates later
        bpy.ops.wm.open_mainfile(filepath=config["base_scene_blendfile"]) # load the main blendfile
        render_args = bpy.context.scene.render
        render_args.engine = "CYCLES" # we use functionality specific to the CYCLES renderer so BLENDER_RENDER cannot be used
        render_args.resolution_x = 320 # the width (in pixels) for the rendered images
        render_args.resolution_y = 240 # the height (in pixels) for the rendered images
        render_args.resolution_percentage = 100
        render_args.tile_x = 512 # the tile size to use for rendering
        render_args.tile_y = 512 # the tile size to use for rendering
        bpy.data.worlds["World"].cycles.sample_as_light  = True
        bpy.context.scene.cycles.blur_glossy             = 2.0
        bpy.context.scene.cycles.samples                 = 512 # the number of samples to use when rendering. Larger values will result in nicer images but will cause rendering to take longer.
        bpy.context.scene.cycles.transparent_min_bounces = 8 # the minimum number of bounces to use for rendering
        bpy.context.scene.cycles.transparent_max_bounces = 8 # the maximum number of bounces to use for rendering

        # compute the final metadata (mostly pixel_cords_*) by setting up the scene in blender (but not rendering)
        all_scenes = []
        for imgidx in range(config["n_images"]):
            print("configuring " + config["split"] + " image " + str(imgidx) + " of " + str(config["n_images"]) + "...")
            img_path = "../output/images/customclevr_" + config["split"] + "_%06d.png" % imgidx
            scene_struct = render_scene(config, imgidx, img_path)
            scene_struct["relationships"] = compute_all_relationships(scene_struct)
            all_scenes.append(scene_struct)

        # output metadata jsons
        with open("../output/customclevr_" + config["split"] + "_config.json", "w") as f:
            json.dump(config, f)
        with open("../output/customclevr_" + config["split"] + "_scenes.json", "w") as f:
            json.dump({"scenes": all_scenes}, f)


def render_scene(config:dict, imgidx:int, img_path:str) -> dict:
    """modifies config"""
    # set camera position
    bpy.data.objects["Camera"].location[0] = config["camera_location"][0]
    bpy.data.objects["Camera"].location[1] = config["camera_location"][1]
    bpy.data.objects["Camera"].location[2] = config["camera_location"][2]
    if config["camera_jitter"] > 0:
        for i in range(3):
            bpy.data.objects["Camera"].location[i] += config["camera_offset"][imgidx][i]

    # ground-truth information about the scene and its objects
    # must be after camera location is finalized
    scene_struct = {"split":config["split"], "image_index":imgidx, "image_filename":os.path.basename(img_path), "objects":[], "directions":{}}
    scene_struct["directions"] = get_plane_dirs() # save all six axis-aligned directions in the scene struct

    # prepare to add objects
    camera = bpy.data.objects["Camera"]

    # add objects to the current blender scene
    objnames = [[]]*config["n_objects"]
    for objidx in range(config["n_objects"]):
        x = config["pos_planex"][imgidx][objidx]
        y = config["pos_planey"][imgidx][objidx]
        objnames[objidx] = add_object(config["shape_dir"], config["shape_name"][imgidx][objidx], config["r"][imgidx][objidx], x, y, config["theta"][imgidx][objidx])
        
        # record data about the object in the scene data structure
        obj = bpy.context.object
        pixel_coords = get_camera_coords(camera, obj.location)
        scene_struct["objects"].append({
            "shape": config["shape_name_out"][imgidx][objidx],
            "size": config["size_name"][imgidx][objidx],
            "material": config["mat_name_out"][imgidx][objidx],
            "3d_coords": tuple(obj.location),
            "rotation": config["theta"][imgidx][objidx],
            "pixel_coords": pixel_coords,
            "color": config["color_name"][imgidx][objidx],
        })
        config["pixel_coords_x"][imgidx][objidx] = pixel_coords[0]
        config["pixel_coords_y"][imgidx][objidx] = pixel_coords[1]
    
    for objidx1 in range(config["n_objects"]):
        for objidx2 in range(objidx1+1, config["n_objects"]): # for each other object
            assert not ((config["pixel_coords_x"][imgidx][objidx1] == config["pixel_coords_x"][imgidx][objidx2]) and (config["pixel_coords_y"][imgidx][objidx1] == config["pixel_coords_y"][imgidx][objidx2]))

    # remove objects
    for name in objnames:
        objs = bpy.data.objects
        objs.remove(objs[name], do_unlink=True) # delete object based on name

    return scene_struct


def add_object(object_dir, name, scale, x, y, theta) -> str:
    """
    Load an object from a file. We assume that in the directory object_dir, there
    is a file named "$name.blend" which contains a single object named "$name"
    that has unit size and is centered at the origin.

    - scale: scalar giving the size that the object should be in the scene
    - x, y: the coordinates on the ground plane where the object should be placed
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
    bpy.context.object.rotation_euler[2] = theta
    bpy.ops.transform.resize(value=(scale, scale, scale))
    bpy.ops.transform.translate(value=(x, y, scale))
    return new_name


def generate_config(split:str) -> dict:
    config = {}
    config["n_images"] = 100 # number of images to render
    config["split"] = split # name of the split for which we are rendering
    config["shape_dir"]            = "data/shapes" # directory where .blend files for object models are stored
    config["material_dir"]         = "data/materials" # directory where .blend files for materials are stored
    config["base_scene_blendfile"] = "data/base_scene.blend" # Base blender file on which all scenes are based; includes ground plane, lights, and camera
    # min_objects = 3 # the minimum number of objects to place in each scene
    # max_objects = 10 # the maximum number of objects to place in each scene
    # config["n_objects"] = random.randint(min_objects, max_objects)
    config["n_objects"] = 6
    config["min_dist"] = 0.25 # The minimum allowed distance between object centers
    config["margin"] = 0.4
    # ^ Along all cardinal directions (left, right, front, back), all objects will be at least this distance apart.
    # This makes resolving spatial relationships slightly less ambiguous
    config["min_pixels_per_object"] = 200
    # ^ All objects will have at least this many visible pixels in the final rendered images;
    # this ensures that no objects are fully occluded by other objects
    config["max_retries"] = 50 # The number of times to try placing an object before giving up and re-placing all objects in the scene.")
  
    config["faceparts"] = ["eye","eye","nose","mouth","mouth","mouth"]
    config["facex"]     = [-2,   -2,   0,     1.75,   2,      1.75]
    config["facey"]     = [-1.5, 1.5,  0,     -1,     0,      1]

    config["shape_color_combos"] = None
    config["shapes"]    = {"cube":"SmoothCube_v2", "sphere":"Sphere", "cylinder":"SmoothCylinder"}
    config["materials"] = {"rubber":"Rubber", "metal":"MyMetal"}
    config["sizes"]     = {"large":0.35, "small":0.25}
    config["colors"] = {
        "red":[173,35,35],
        "blue":[42,75,215],
        "green":[29,105,20]
    }
    # config["colors"] = {
    #     "gray":[87,87,87],     # hard to see (Rick)
    #     "red":[173,35,35],
    #     "blue":[42,75,215],
    #     "green":[29,105,20],
    #     "brown":[129,74,25],   # deleting to get down to fewer colors (Eli)
    #     "purple":[129,38,192], # deleting to get down to fewer colors (Eli)
    #     "cyan":[41,208,208],   # deleting to get down to fewer colors (Eli)
    #     "yellow":[255,238,51]  # deleting to get down to fewer colors (Eli)
    # }

    config["key_light_jitter"]  = 1.0 # the magnitude of random jitter to add to the key light position
    config["fill_light_jitter"] = 1.0 # the magnitude of random jitter to add to the fill light position
    config["back_light_jitter"] = 1.0 # the magnitude of random jitter to add to the back light position
    config["camera_jitter"]     = 0.5 # the magnitude of random jitter to add to the camera position
    config["pos_jitter"]        = 0.05 # object position jitter
    config["camera_location"]   = [3,0,8] # camera seems to always look toward the origin
    # config["camera_location"]   = [7.4811,-6.5076,5.3437] # seems to be the default somehow

    if config["split"] == "trnsimple":
        config["seed"] = 100
    elif config["split"] == "tstsimple":
        config["seed"] = 101
    else:
        raise Exception("unexpected split")

    material_mapping = [(v, k) for k, v in config["materials"].items()] # e.g. [("Rubber","rubber"), ("MyMetal","metal")]
    object_mapping = [(v, k) for k, v in config["shapes"].items()] # e.g. [("SmoothCube_v2","cube"), ("Sphere","sphere"), ("SmoothCylinder","cylinder")]
    size_mapping = list(config["sizes"].items()) # e.g. [("large",0.7), ("small",0.35)]
    
    random.seed(config["seed"])

    config["theta"]              = [[]]*config["n_images"] # n_images x n_objects
    config["mat_name"]           = [[]]*config["n_images"] # n_images x n_objects
    config["mat_name_out"]       = [[]]*config["n_images"] # n_images x n_objects
    config["shape_name"]         = [[]]*config["n_images"] # n_images x n_objects
    config["shape_name_out"]     = [[]]*config["n_images"] # n_images x n_objects
    config["color_name"]         = [[]]*config["n_images"] # n_images x n_objects
    config["size_name"]          = [[]]*config["n_images"] # n_images x n_objects
    config["r"]                  = [[]]*config["n_images"] # n_images x n_objects
    config["pos_planex"]         = [[]]*config["n_images"] # n_images x n_objects
    config["pos_planey"]         = [[]]*config["n_images"] # n_images x n_objects
    config["camera_offset"]      = [[]]*config["n_images"] # n_images x 3
    config["key_light_offset"]   = [[]]*config["n_images"] # n_images x 3
    config["fill_light_offset"]  = [[]]*config["n_images"] # n_images x 3
    config["back_light_offset"]  = [[]]*config["n_images"] # n_images x 3
    config["randomized_obj_idx"] = [0]*config["n_images"] # n_images x 1
    config["eyes_same_color"]    = [False]*config["n_images"] # n_images x 1
    for imgidx in range(config["n_images"]):
        # add random jitter to scene
        config["camera_offset"][imgidx]     = [0,0,0]
        config["key_light_offset"][imgidx]  = [0,0,0]
        config["fill_light_offset"][imgidx] = [0,0,0]
        config["back_light_offset"][imgidx] = [0,0,0]
        for i in range(3):
            if config["camera_jitter"] > 0:
                config["camera_offset"][imgidx][i] = myrand(config["camera_jitter"])
            if config["key_light_jitter"] > 0:
                config["key_light_offset"][imgidx][i] = myrand(config["key_light_jitter"])
            if config["fill_light_jitter"] > 0:
                config["fill_light_offset"][imgidx][i] = myrand(config["fill_light_jitter"])
            if config["back_light_jitter"] > 0:
                config["back_light_offset"][imgidx][i] = myrand(config["back_light_jitter"])

        config["theta"][imgidx]          = [[]]*config["n_objects"]
        config["mat_name"][imgidx]       = [[]]*config["n_objects"]
        config["mat_name_out"][imgidx]   = [[]]*config["n_objects"]
        config["shape_name"][imgidx]     = [[]]*config["n_objects"]
        config["shape_name_out"][imgidx] = [[]]*config["n_objects"]
        config["color_name"][imgidx]     = [[]]*config["n_objects"]
        config["size_name"][imgidx]      = [[]]*config["n_objects"]
        config["r"][imgidx]              = [[]]*config["n_objects"]
        config["pos_planex"][imgidx]     = [[]]*config["n_objects"]
        config["pos_planey"][imgidx]     = [[]]*config["n_objects"]
        for objidx in range(config["n_objects"]):
            # choose random orientation for the object
            config["theta"][imgidx][objidx] = 360.0 * random.random()

            # choose material
            config["mat_name"][imgidx][objidx],config["mat_name_out"][imgidx][objidx] = random.choice(material_mapping)

            # choose color and shape
            if config["shape_color_combos"] is None:
                config["shape_name"][imgidx][objidx],config["shape_name_out"][imgidx][objidx] = random.choice(object_mapping)
                config["color_name"][imgidx][objidx] = random.choice(list(config["colors"].keys()))
            else:
                config["shape_name_out"][imgidx][objidx],color_choices = random.choice(config["shape_color_combos"])
                config["color_name"][imgidx][objidx] = random.choice(color_choices)
                config["shape_name"][imgidx][objidx] = [k for k, v in object_mapping if v == config["shape_name_out"][imgidx][objidx]][0]

            # choose a random size
            config["size_name"][imgidx][objidx],config["r"][imgidx][objidx] = random.choice(size_mapping)
            if config["shape_name"][imgidx][objidx] == "Cube":
                config["r"][imgidx][objidx] /= math.sqrt(2) # for cube, adjust the size a bit

        config["eyes_same_color"][imgidx] = (config["color_name"][imgidx][0] == config["color_name"][imgidx][1])

        # choose position
        config["pos_planex"][imgidx] = copy.deepcopy(config["facex"]) # init to a face
        config["pos_planey"][imgidx] = copy.deepcopy(config["facey"]) # init to a face
        for objidx in range(config["n_objects"]):
            config["pos_planex"][imgidx][objidx] += myrand(config["pos_jitter"]) # jitter said face
            config["pos_planey"][imgidx][objidx] += myrand(config["pos_jitter"]) # jitter said face
        if imgidx % 2 == 1:
            config["randomized_obj_idx"][imgidx] = random.randint(0, config["n_objects"] - 1) # pick a random object
            randomize_pos(config, imgidx, config["randomized_obj_idx"][imgidx]) # choose a random object to randomly place

    # randomize the order of the objects (future work)
    # for imgidx in range(config["n_images"]):
    #     idx = list(random.randrange(config["n_objects"]))
    #     config["theta"][imgidx]          = config["theta"][imgidx][idx]
    #     config["mat_name"][imgidx]       = config["mat_name"][imgidx][idx]
    #     config["mat_name_out"][imgidx]   = config["mat_name_out"][imgidx][idx]
    #     config["shape_name"][imgidx]     = config["shape_name"][imgidx][idx]
    #     config["shape_name_out"][imgidx] = config["shape_name_out"][imgidx][idx]
    #     config["color_name"][imgidx]     = config["color_name"][imgidx][idx]
    #     config["size_name"][imgidx]      = config["size_name"][imgidx][idx]
    #     config["r"][imgidx]              = config["r"][imgidx][idx]
    #     config["pos_planex"][imgidx]     = config["pos_planex"][imgidx][idx]
    #     config["pos_planey"][imgidx]     = config["pos_planey"][imgidx][idx]

    config["pixel_coords_x"] = [[]]*config["n_images"] # set in render_scene
    config["pixel_coords_y"] = [[]]*config["n_images"] # set in render_scene
    for imgidx in range(config["n_images"]):
        config["pixel_coords_x"][imgidx] = [[]]*config["n_objects"] # set in render_scene
        config["pixel_coords_y"][imgidx] = [[]]*config["n_objects"] # set in render_scene
    return config


def randomize_pos(config:dict, imgidx:int, randomized_obj_idx:int):
    """modifies config, uses rng"""
    randx = random.uniform(-2.5, 2.5)
    randy = random.uniform(-2.5, 2.5)

    # check to make sure the new object is further than min_dist from all other objects
    is_dist_good = True # no objects "intersect"
    for objidx in range(config["n_objects"]):
        x = config["pos_planex"][imgidx][objidx]
        y = config["pos_planey"][imgidx][objidx]
        dx = x - randx
        dy = y - randy
        dist = math.sqrt(dx * dx + dy * dy)
        rr = config["r"][imgidx][randomized_obj_idx]
        if dist - config["r"][imgidx][objidx] - rr < config["min_dist"]:
            is_dist_good = False
            break
    
    if is_dist_good:
        config["pos_planex"][imgidx][randomized_obj_idx] = randx
        config["pos_planey"][imgidx][randomized_obj_idx] = randy
    else:
        randomize_pos(config, imgidx, randomized_obj_idx) # try again


def myrand(L:float) -> float:
    return 2.0 * L * (random.random() - 0.5)


def get_plane_dirs() -> dict:
    # put a plane on the ground so we can compute cardinal directions
    bpy.ops.mesh.primitive_plane_add(size=5)
    plane = bpy.context.object

    # figure out the left, up, and behind directions along the plane and record them in the scene structure
    camera = bpy.data.objects["Camera"]
    plane_normal = plane.data.vertices[0].normal
    cam_behind = camera.matrix_world.to_quaternion() @ Vector((0, 0, -1))
    cam_left   = camera.matrix_world.to_quaternion() @ Vector((-1, 0, 0))
    cam_up     = camera.matrix_world.to_quaternion() @ Vector((0, 1, 0))
    plane_behind = (cam_behind - cam_behind.project(plane_normal)).normalized()
    plane_left   = (cam_left - cam_left.project(plane_normal)).normalized()
    plane_up     = cam_up.project(plane_normal).normalized()

    # Delete the plane; we only used it for normals anyway.
    # The base scene file contains the actual ground plane.
    # for o in bpy.data.objects:
    #   o.select = False
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass
    bpy.ops.object.select_all(action="DESELECT")
    plane.select_set(True)
    bpy.ops.object.delete()

    plane_dirs = {}
    plane_dirs["behind"] = tuple(plane_behind)
    plane_dirs["front"]  = tuple(-plane_behind)
    plane_dirs["left"]   = tuple(plane_left)
    plane_dirs["right"]  = tuple(-plane_left)
    plane_dirs["above"]  = tuple(plane_up)
    plane_dirs["below"]  = tuple(-plane_up)
    return plane_dirs


def compute_all_relationships(scene_struct) -> dict:
    """
    Computes relationships between all pairs of objects in the scene.
    Returns a dictionary mapping string relationship names to lists of lists of integers,
    where output[rel][i] gives a list of object indices that have the relationship rel with object i.
    For example if j is in output["left"][i] then object j is left of object i.
    """
    eps = 0.2
    all_relationships = {}
    for name, direction_vec in scene_struct["directions"].items():
        if name == "above" or name == "below":
            continue
        all_relationships[name] = []
        for i, obj1 in enumerate(scene_struct["objects"]):
            coords1 = obj1["3d_coords"]
            related = set()
            for j, obj2 in enumerate(scene_struct["objects"]):
                if obj1 == obj2:
                    continue
                coords2 = obj2["3d_coords"]
                diff = [coords2[k] - coords1[k] for k in [0, 1, 2]]
                dot = sum(diff[k] * direction_vec[k] for k in [0, 1, 2])
                if dot > eps:
                    related.add(j)
            all_relationships[name].append(sorted(list(related)))
    return all_relationships


def get_camera_coords(cam, pos):
    """
    For a specified point, get both the 3D coordinates and 2D pixel-space
    coordinates of the point from the perspective of the camera.

    Inputs:
    - cam: Camera object
    - pos: Vector giving 3D world-space position

    Returns a tuple of:
    - (px, py, pz): px and py give 2D image-space coordinates; pz gives depth in the range [-1, 1]
    """
    scene = bpy.context.scene
    x, y, z = bpy_extras.object_utils.world_to_camera_view(scene, cam, pos)
    scale = scene.render.resolution_percentage / 100.0
    w = int(scale * scene.render.resolution_x)
    h = int(scale * scene.render.resolution_y)
    px = int(round(x * w))
    py = int(round(h - y * h))
    return (px,py,z)


if __name__ == "__main__":
    if INSIDE_BLENDER:
        main() # run normally
    else:
        print("this script is intended to be called by blender - see README.md")
