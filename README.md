# custom_clevr_stimgen

## Summary

A customized version of the CLEVR dataset's stimulus generation code.

The original code was downloaded from https://cs.stanford.edu/people/jcjohns/clevr/ .

The ```output/``` folder contains copies of the files that will be (re)generated, should you run this code.

## Requirements

- Only tested on Ubuntu 22.04 with Blender 2.83.20. Due to instabilities in Blender's python interface and OS requirements across versions, other OS/Blender version combinations may not work.
- Python is not needed - Blender packs its own version of Python 3.7 and will call the python script within that environment.

## Setup & Running
1) Install Blender 2.83.20. Download the file from [...](...) (preferred), [https://www.blender.org/download/lts/2-83/](https://www.blender.org/download/lts/2-83/), or [https://www.blender.org/download/release/Blender2.83/blender-2.83.20-linux-x64.tar.xz/](https://www.blender.org/download/release/Blender2.83/blender-2.83.20-linux-x64.tar.xz/) and unzip into ```custom_clevr_stimgen/```. There should now be a ```custom_clevr_stimgen/blender-2.83.20-linux-x64``` directory.
2) In bash, cd to ```custom_clevr_stimgen/```, then run: ```echo $PWD/image_generation >> blender-2.83.20-linux-x64/2.83/python/lib/python3.7/site-packages/clevr.pth```
3) From the ```custom_clevr_stimgen/image_generation/``` folder, run ```./renderscript.sh```. This will call blender which will call ```config_images.py``` then ```render_images.py```, and generate the json files in the ```output/``` folder, the images provided in the ```output/images/``` folder, and some blender files. If for some reason this script cannot be run, you may need to execute ```chmod a+x ./renderscript.sh```. Note: Blender is very randomly unstable, so it is possible that a few images won't render. To get any missing images, you can rerun ```./renderscript.sh```.
