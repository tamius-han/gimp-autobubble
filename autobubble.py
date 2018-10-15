#!/usr/bin/env python

# docs: https://www.gimp.org/docs/python/index.html

import math
from gimpfu import *

# I tried looking for proper solution that gets position of a given layer
# in the layer stack. Google didn't yield anything useful, and text outliner
# plugin confirmed inexistance of an object property that would just give me
# the position of the layer. Ok then, let's roll our own.
def get_layer_stack_position(layer, group):
  iterator_pos = 0;

  if type(group) is tuple:
    for layer_id in group:
      if gimp.Item.from_id(layer_id)) == layer:
        return iterator_pos
      iterator_pos = iterator_pos + 1
  else:
    for l in group:
      if l == layer:
        return iterator_pos;
      iterator_pos = iterator_pos + 1

  return 0; # for some reason we didn't find proper position of layer in the stack  

def add_layer_below_currently_selected(img):
  stack_pos = 0

  if img.active_layer.parent:
    # parent is a group layer
    sublayers = pdb.gimp_item_get_children(img.active_layer)[1]
    stack_pos = get_layer_stack_position(img.active_layer, sublayers)
  else:
    # parent is not a group layer (e.g. selected layer is on top level)
    stack_pos = get_layer_stack_position(img.active_layer, img.layers)
  
  bubble_layer = gimp.Layer(t_img, "auto-bubble", t_img.width, t_img.height, RGBA_IMAGE, 100, NORMAL_MODE)
  
  # if img.active_layer.parent doesn't exist, it adds layer to top group. Otherwise 
  # the layer will be added into current layer group
  pdb.gimp_image_insert_layer(img, bubble_layer, img.active_layer.parent, stack_pos + 1)

  return bubble_layer


def autobubble_layer(t_img, t_drawable, layer, bubble_layer, isRound):
  


def autobubble_group(t_img, t_drawable, bubble_layer, isRound): 
  # get children of currently active layer
  # returns [group layer id, [array with sublayer ids]]
  # if we do dis, we only get array with sublayer ids
  sublayers = pdb.gimp_item_get_children(t_img.active_layer)[1]

  for layer_id in sublayers:
    layer = gimp.Item.from_id(layer_id)
    if type(layer) is gimp.GroupLayer:       # btw yes, we DO do recursion
      autobubble_group(t_img, t_drawable, bubble_layer, isRound)
    else
      autobubble_layer(t_img, t_drawable, layer, bubble_layer, isRound)
    


# main function
def python_autobubble(t_img, t_drawable, isRound=true):
  # Bubbles will be drawn on their separate layer, which will be placed under
  # current layer
  bubble_layer = add_layer_below_currently_selected(t_img)

  # If activeLayer is a layer group, we run this script recursively for all
  # all layers in a group. 
  if type(t_img.active_layer) is gimp.GroupLayer:
    autobubble_group(t_img, t_drawable, bubble_layer, isRound)
  else
    autobubble_layer(t_img, t_drawable, t_img.active_layer, bubble_layer, isRound)


# register plugin.
register(
  "python_fu_autobubble",                                   # name
  "Automatically draw speech bubbles around text layers.",  # plugin tl;dr
  "Automatically draw speech bubbles around text layers.",  # "help"
  "Tamius Han",                                             # Author
  "Tamius Han",                                             # Copyright
  "2018-2019",                                              # Date
  "<Image>/Filters/Render/_Auto-bubble",                    # Menu path
  "*",                                                      # Image type
  [                                                         # params

  ],
  [],                                                       # results
  python_autobubble                                         # script function
)

main();
