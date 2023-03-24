#!/bin/bash

# first, run once to compute config.txt instead of rendering
../blender-2.83.20-linux-x64/blender --background --python config_images.py

echo "trnsimple" > split.txt
for i in $(seq 0 99) # inclusive-inclusive
do
    echo "$i" > img2render.txt # pass image number to the script via file
    ../blender-2.83.20-linux-x64/blender --background --python render_image.py
    rm img2render.txt
done
rm split.txt

echo "tstsimple" > split.txt
for i in $(seq 0 99) # inclusive-inclusive
do
    echo "$i" > img2render.txt # pass image number to the script via file
    ../blender-2.83.20-linux-x64/blender --background --python render_image.py
    rm img2render.txt
done
rm split.txt