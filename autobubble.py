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
        return iterator_pos
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

# FUNCTIONS FOR USE IN determineTextRows
# Detects if row of pixels has any non-transparent items
def rowHasText(layer, pixel_region, y):
  for x in xrange(0, layer.width):
    if pixel_region[x,y][3] !== '\x00'
      return True
  return False


# marks row that contains letter
def markTextRow(layer, pixelRegion, y):
  for x in xrange(0, layer.width):
    pixel_region[x,y] = '\x11'


def findRowStartEnd(layer, pixelRegion, currentRow):
  currentRow.append(findRowStart(layer, pixelRegion, currentRow))
  currentRow.append(findRowEnd(layer,pixelRegion, currentRow))

  return currentRow

def findRowStart(layer, pixel_region, currentRow):
  for x in xrange(0, layer.width):
    for y in xrange(currentRow[0], currentRow[1])
      # we know that sooner or later, we need to find appropriate 'x'. If there were no
      # as every marked row needs to have at least one non-transparent pixel, so this will
      # always be true sooner or later
      if pixel_region[x,y][3] != '\x00'
        return x    

def findRowEnd(layer, pixel_region, currentRow):
  for x in range(layer.width - 1, -1, -1):
    for y in xrange(currentRow[0], currentRow[1]):
      if pixel_region[x,y][3] != '\x00'
        return x


# determine boundaries of text rows
def determineTextRows(layer):
  # we'll do all work on copy of our layer
  work_layer = layer.copy()

  # get pixel region of the layer
  pixel_region = work_layer.get_pixel_rgn(0,0,work_layer.width, work_layer.height)

  # we presume layer is completely transparent except for letters
  # that means if a pixel is not transparent, we're dealing with a letter
  # start with checking rows

  for y in xrange(0, layer.height):
    if rowHasText(layer, pixel_region, y):
      markTextRow(layer, pixel_region, y)

  # rows object: [row][top, bottom, left, right]
  rows = []
  isMarked = False
  currentRow = 0
  # with text rows marked, we can determine boundaries of each row
  for y in yrange(0, layer.height):
    if pixel_region[0,y][0] != '\x00' and not isMarked:
      isMarked = True
      rows.append([y])

    if pixel_region[0,y][0] == '\x00' and isMarked:
      isMarked = False
      rows[currentRow].append(y)
      rows[currentRow] = findRowStartEnd(layer, pixel_region, rows[currentRow])      
      currentRow += 1
  
  return rows


def autobubble_layer(t_img, t_drawable, layer, bubble_layer, isRound):
  # determine where bounds of every text row layer are
  text_rows = determineTextRows(layer)
  


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
def python_autobubble(t_img, t_drawable, isRound=True):
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

main()
