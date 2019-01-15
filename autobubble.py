#!/usr/bin/env python

# docs: https://www.gimp.org/docs/python/index.html
# 
# cheat sheet for gimp for when manually doing stuff in console:
#     active image:      gimp.image_list()[0]
#     active layer:      <image>.active_layer()
#
# execfile('projects/gimp-autobubble/autobubble.py')
#
# debug cheat
"""
-- start --
execfile('projects/gimp-autobubble/autobubble.py')
image = gimp.image_list()[0]
"""

import math
import copy
import itertools
from gimpfu import *

# I tried looking for proper solution that gets position of a given layer
# in the layer stack. Google didn't yield anything useful, and text outliner
# plugin confirmed inexistance of an object property that would just give me
# the position of the layer. Ok then, let's roll our own.
#
#
#  L A Y E R   M A N A G E M E N T
#
# todo: spin layer stuff into a separate file, because autobubble also uses 
# this very same code. This means this and autobubble script may share certain
# bugs as well

# get the type we want for our layer
def get_layer_type(image):
  if image.base_type is RGB:
    return RGBA_IMAGE
  return GRAYA_IMAGE

# finds layer position in a layer group
def get_layer_stack_position(layer, group):
  iterator_pos = 0

  if type(group) is tuple:
    for layer_id in group:
      if gimp.Item.from_id(layer_id) == layer:
        return iterator_pos
      iterator_pos = iterator_pos + 1
  else:
    for l in group:
      if l == layer:
        return iterator_pos
      iterator_pos = iterator_pos + 1

  return 0  # for some reason we didn't find proper position of layer in the stack     

# add a new layer under given layer
def add_layer_below(image, layer, preserveCmd=False, argumentPass="()=>skip", tag=''):
  stack_pos = 0
  
  if layer.parent:
    # parent is a group layer (= we're inside a group layer)
    # this returns a tuple: (parent id, (<child ids>)). We want child ids.
    sublayers = pdb.gimp_item_get_children(layer.parent)[1]
    stack_pos = get_layer_stack_position(layer, sublayers)
  else:
    # parent is not a group layer (e.g. selected layer is on top level)
    stack_pos = get_layer_stack_position(layer, image.layers)
  
  if preserveCmd:
    new_name = layer.name
  else:
    new_name = layer.name.split('()=>')[0]

  layer_out = gimp.Layer(image, "autobubble{}::{}{}".format(tag, new_name, argumentPass), image.width, image.height, get_layer_type(image), 100, NORMAL_MODE)
  
  # if img.active_layer.parent doesn't exist, it adds layer to top group. Otherwise 
  # the layer will be added into current layer group
  pdb.gimp_image_insert_layer(image, layer_out, layer.parent, stack_pos + 1)

  return layer_out

# adds layer at the bottom of a given group
def add_layer_group_bottom(image, layer):
  stack_pos = 0
  
  if type(layer) is gimp.GroupLayer:
    # we want to give outline to a layer group. We add new layer at 
    # at the bottom of the current group, so moving the group moves
    # both group's original contents as well as the outline
    stack_pos = len(pdb.gimp_item_get_children(layer)[1]) - 1

  else:
    # not a layer group, business as usual:
    return add_layer_below(image, layer)
  
  layer_out = gimp.Layer(image, "outline::{}".format(layer.name), image.width, image.height, get_layer_type(image), 100, NORMAL_MODE)
  # if img.active_layer.parent doesn't exist, it adds layer to top group. Otherwise 
  # the layer will be added into current layer group
  pdb.gimp_image_insert_layer(image, layer_out, layer, stack_pos + 1)

  return layer_out


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

#
#
#  A U T O - A R G U M E N T     P A R S E R
#
# yes, we'll parse arguments from layers. 

def parse_args_from_layer_name(name):
  firstCommand = name.split('>>')[0]
  if firstCommand.find('()=>skip') != -1:
    return [['skip']]
  if firstCommand.find('()=>end') != -1:
    return [['end']]
  
  # argline is:
  # .split('>>')[0] -- everything before the first >> (if any)
  #    .split('()=>autobubble') -- that's after first ()=>autobubble
  #       .split('()=>)           -- and before the command that follows (if any)
  argLine = firstCommand.split('()=>autobubble')[1].split('()=>')[0]
  argsIn = argLine.split(' ')

  argsOut = []

  for arg in argsIn:
    argsOut.append(arg.split('='))

  # >> can be stacked, but you can't use it in two command blocks
  argPassAll = "()=>autobubble".join(name.split('>>'))
  argPassCount = len(argPassAll)

  if argPassCount > 1:
    argPass = '>>'.join(argPassAll[1:])
    argsOut.append(['pass', argPass])

  return argsOut


#
#
#  C O L O R    S T A C K
#

__saved_colors_bg = []
__saved_colors_fg = []
def color_push_bg(color):
  __saved_colors_bg.append(color)

def color_pop_bg():
  return __saved_colors_bg.pop()

def color_push_fg(color):
  __saved_colors_fg.append(color)

def color_pop_fg():
  return __saved_colors_fg.pop()

def set_bg_stack(newColor):
  color_push_bg(gimp.get_background())
  gimp.set_background(newColor)

def restore_bg_stack():
  gimp.set_background(color_pop_bg())

def set_fg_stack(newColor):
  color_push_fg(gimp.get_foreground())
  gimp.set_foreground(newColor)

def restore_fg_stack():
  gimp.set_foreground(color_pop_fg())

#
#
# misc helper functions:
#
def paint_selection_bg(layer):
  pdb.gimp_edit_bucket_fill_full(layer, BUCKET_FILL_BG, LAYER_MODE_NORMAL, 100, 0, 0, 1, 0, 1, 1)

def paint_selection_fg(layer):
  pdb.gimp_edit_bucket_fill_full(layer, BUCKET_FILL_FG, LAYER_MODE_NORMAL, 100, 0, 0, 1, 0, 1, 1)

def clear_selection(image):
  pdb.gimp_image_select_rectangle(image, CHANNEL_OP_SUBTRACT, 0, 0, image.width,image.height)

def grow_selection(image, thickness):
  # Grow the selection
	pdb.gimp_selection_grow(image, thickness)

def feather_selection(image, feather):
  pdb.gimp_selection_feather(image, feather)

# FUNCTIONS FOR USE IN determineTextRows
# Detects if row of pixels has any non-transparent items
def rowHasText(layer, pixel_region, y):
  for x in xrange(0, layer.width):
    if pixel_region[x,y][3] != '\x00':
      return True
  return False

def findRowStartEnd(layer, pixelRegion, currentRow):
  currentRow.append(findRowStart(layer, pixelRegion, currentRow))
  currentRow.append(findRowEnd(layer,pixelRegion, currentRow))

  return currentRow

def findRowStart(layer, pixel_region, currentRow):
  for x in xrange(0, layer.width):
    for y in xrange(currentRow[0], currentRow[1]):
      # we know that sooner or later, we need to find appropriate 'x'. If there were no
      # as every marked row needs to have at least one non-transparent pixel, so this will
      # always be true sooner or later
      if pixel_region[x,y][3] != '\x00':
        return x

def findRowEnd(layer, pixel_region, currentRow):
  for x in range(layer.width - 1, -1, -1):
    for y in xrange(currentRow[0], currentRow[1]):
      if pixel_region[x,y][3] != '\x00':
        return x + 1


# determine boundaries of text rows
def determineTextRows(layer):
  # we'll do all work on copy of our layer
  work_layer = layer.copy()
  #
  # get pixel region of the layer
  pixel_region = work_layer.get_pixel_rgn(0,0,work_layer.width, work_layer.height)
  #
  # we presume layer is completely transparent except for letters
  # that means if a pixel is not transparent, we're dealing with a letter
  # we mark rows with text one way, rows without the other.
  #
  # rows without text have red component of the first pixel set to 0x00
  # rows with text have red component of the first pixel set to something else
  for y in xrange(0, layer.height):
    if rowHasText(layer, pixel_region, y):
      pixel_region[0,y] = '\x11' + pixel_region[0,y][1:]
    else:
      pixel_region[0,y] = '\x00' + pixel_region[0,y][1:]
  #
  # rows object: [row][top, bottom, left, right]
  rows = []
  isMarked = False
  currentRow = 0
  #
  # with text rows marked, we can determine boundaries of each row
  for y in xrange(0, layer.height):
    if pixel_region[0,y][0] != '\x00' and not isMarked:
      isMarked = True
      rows.append([y])
      #
    if pixel_region[0,y][0] == '\x00' and isMarked:
      isMarked = False
      rows[currentRow].append(y - 1)
      rows[currentRow] = findRowStartEnd(layer, pixel_region, rows[currentRow])      
      currentRow += 1
  #
  return rows

def findJag(edge1, edge2, minStepSize):
  #  |<edge1
  #   |<edge2    - returns 1
  #
  #   |<edge1
  #  |<edge2     - returns -1
  if abs(edge1 - edge2) < minStepSize:
    if edge1 > edge2:
      # print("jag = 1")
      return 1
    else: 
      return -1
  
  # print("jag is bigger than min step size")
  return 0

def correctRows(rows, minStepSize):
  if len(rows) < 2:
    return rows #there's nothing to do if we only have one row
  
  # correct jags in the left edge
  for i in xrange(0, len(rows) - 1):
    jag = findJag(rows[i][2], rows[i+1][2], minStepSize)
    if jag == -1:
      rows[i+1][2] = rows[i][2]
    if jag == 1:
      # in this case, we correct back, naively. We don't check whether re-adjustment
      # would cause the jag to grow to acceptable size. I don't think the complicated
      # nature of the work would make that worth it, but I'll accept a PR
      rows[i][2] = rows[i+1][2]
      if i > 0:
        for j in range(i - 1, -1, -1):
          rows[j][2] = rows[i][2]
  
  # now correct the other edge, but mind that meanings of findJag() have flipped
  for i in xrange(0, len(rows) - 1):
    # print('..')
    jag = findJag(rows[i][3], rows[i+1][3], minStepSize)
    if jag == 1:
      rows[i+1][3] = rows[i][3]
    if jag == -1:
      rows[i][3] = rows[i+1][3]
      if i > 0:
        for j in range(i - 1, -1, -1):
          rows[j][3] = rows[i][3]
  
  return rows

def selectRectangle(image, layer, rows, xpad, ypad):
  # let's get offsets into more human-readable form
  offset_x = layer.offsets[0]
  offset_y = layer.offsets[1]

  # let's do some pre-processing
  connect_rows_treshold = 0
  for row in rows:
    connect_rows_treshold += row[1] - row[0]

  # if the difference between row[n][1] and row[n+1][0] is more than this,
  # treat the rows as two separate bubbles
  connect_rows_treshold /= (len(rows) * 2)

  # now we can start drawing rectangles
  for i in xrange(0, len(rows)):
    select_x = rows[i][2] - xpad + offset_x
    select_y = rows[i][0] - ypad + offset_y
    select_w = rows[i][3] - rows[i][2] + (2*xpad)
    select_h = rows[i][1] - rows[i][0] + (2*ypad)

    # image, operation (0 - add), x, y, w, h)
    pdb.gimp_image_select_rectangle(image, CHANNEL_OP_ADD, select_x, select_y, select_w, select_h)

    # ensure current row is connected with row on top (unless the gap between two rows is
    # bigger than our treshold)
    if i > 0 and rows[i][0] - rows[i-1][1] < connect_rows_treshold:
      select_x =            max(rows[i][2], rows[i-1][2]) 
      select_y =            rows[i-1][1] 
      select_w = 2 * xpad + min(rows[i][3], rows[i-1][3]) - select_x
      select_h = 2 * ypad + rows[i][0] - select_y

      # there's a reason this isn't included above
      select_x += offset_x - xpad
      select_y += offset_y - ypad

      # image, operation (0 - add), x, y, w, h)
      pdb.gimp_image_select_rectangle(image, CHANNEL_OP_ADD, select_x, select_y, select_w, select_h)
  # end

def sortPointsByComponent(points, component):
  # this is criminally bad, but we don't care because it's only 4 points
  # you can karmawhore this on /r/badcode, I don't care
  sortedPoints = []

  for p in points:
    if len(sortedPoints) == 0:
      sortedPoints.append(p)
      continue

    append = True
    for i in range(0, len(sortedPoints)):
      if sortedPoints[i][component] > p[component]:
        sortedPoints.insert(i, p)
        append = False
        break

    if append:
      sortedPoints.append(p)
  
  return sortedPoints

def getEllipseCenterForPoints(points):
  # find center
  middle_x = (points[0][0] + points[1][0] + points[2][0] + points[3][0]) / 4
  middle_y = (points[0][1] + points[1][1] + points[2][1] + points[3][1]) / 4
  
  # find opposing vertices
  leftFirst = sortPointsByComponent(points, 0)
  #     * one of the first left points must be nw, the other sw
  #     * note that this only works because leftmost two points
  #       cant share 'y' coordinate due to how we calculate edge points
  leftFirst
  if leftFirst[0][1] > leftFirst[1][1]:
    nw = leftFirst[0]
    sw = leftFirst[1]
  else:
    nw = leftFirst[1]
    sw = leftFirst[0]
  
  if leftFirst[2][1] > leftFirst[3][1]:
    ne = leftFirst[2]
    se = leftFirst[3]
  else:
    ne = leftFirst[3]
    se = leftFirst[2]
  
  # don't even get a center if either of the slopes is vertical
  if nw[0] == se[0] or ne[0] == sw[0]:
    return [-1, -1]

  # find where they intersect
  nwse_slope = (se[1] - nw[1]) / (se[0] - nw[0])
  swne_slope = (ne[1] - sw[1]) / (ne[0] - sw[0])
  
  nwse_extra = se[1] - nwse_slope * se[0]
  swne_extra = ne[1] - swne_slope * ne[0]
  
  x = (swne_extra - nwse_extra) / (nwse_slope - swne_slope)
  y = (nwse_slope * x) + nwse_extra
  
  # mirror that over the center point from earlier
  mx = middle_x + (middle_x - x)
  my = middle_y + (middle_y - y)
  
  # return value
  return [mx, my]

def bruteforceEllipseBounds(all_points, combination, mx, my):
  maxx = combination[0][0]; maxy = combination[0][1]; minx = combination[0][0]; miny = combination[0][1]

  iterations = 50
  stepRelative = 0.75
  stepRelative_arStage_outer = 0.99
  stepRelative_arStage_inner = 0.98

  for p in combination:
    if p[0] > maxx:
      maxx = p[0]
    if p[0] < minx:
      minx = p[0]
    if p[1] > maxy:
      maxy = p[1]
    if p[1] < miny:
      miny = p[1]

  ew = maxx - minx  # this is our initial radius, twice as long as width/height
  eh = maxy - miny  # this also radius, but for other axis

  stepx = ew * stepRelative
  stepy = eh * stepRelative

  # step 1: find ellipse with same aspect ratio as text
  while iterations > 0:
    iterations -= 1

    inEllipse = True
    for point in all_points:
      res = (((point[0] - mx) ** 2) / (ew ** 2)) + (((point[1] - my) ** 2) / (eh ** 2))
      if res > 1:
        inEllipse = False
        break


    if inEllipse:
      ew -= stepx
      eh -= stepy
    else:
      ew += stepx
      eh += stepy

    stepx *= stepRelative
    stepy *= stepRelative

  # step 2: try to find a better radius by shrinking shorter radius 
  # and stretching longer radius. The following values are maximum 
  # possible values - if we find a solution that has greater area than
  # the best current solution, we return best width and height without
  # searching further as we aren't going to find a better solution
  iterations = 40
  innerSteps = 20

  bestArea = ew * eh
  bestw = ew
  besth = eh

  # print("----- bruteforce -----")
  # print("inital area:")
  # print([bestArea, [mx, my], [bestw, besth]])

  # true if ellipse is wider than taller, false otherwise
  isLandscape = ew >= eh

  stepx = ew * stepRelative_arStage_outer
  stepy = eh * stepRelative_arStage_outer

  if isLandscape:
    stepInner = ew * stepRelative_arStage_inner
  else:
    stepInner = eh * stepRelative_arStage_inner
  
  for i in range(0, iterations):
    # reduce shorter radius
    if isLandscape:
      eh -= stepy
    else:
      ew -= stepx

    h = eh
    w = ew

    hasBeenInEllipse = False

    for j in range(0, innerSteps):
      # test if all points are in ellipse
      inEllipse = True
      for point in all_points:
        res = (((point[0] - mx) ** 2) / (w ** 2)) + (((point[1] - my) ** 2) / (h ** 2))
        if res > 1:
          inEllipse = False
          break
      
      # expand the ellipse in the other dimension from where we narrowed it
      if isLandscape:
        w += stepInner
      else:
        h += stepInner
      
      if inEllipse:
        hasBeenInEllipse = True
        nbb = w * h
        if nbb < bestArea:
          bestArea = nbb
          bestw = w
          besth = h
          # print("bruteforce: found new solution (area, mx, my, rx, ry")
          # print([bestArea, [mx, my], [bestw, besth]])
        else:
          break   # we won't find a better solution this iteration
    
    if not hasBeenInEllipse:
      break       # if this iteation has never been in an ellipse, subsequent
                  # iterations won't be either
  
  # return best radius:
  return [bestw, besth]


def calculateEllipseBounds_bruteforce(points):
  bestArea = -1
  bestBounds = [0, 0, 0, 0]

  for combination in itertools.combinations(points, 4):
    # print("")
    # print("")
    # print("<starting new loop>")

    [mx, my] = getEllipseCenterForPoints(combination)

    # let's see if getEllipseCenterForPoints told us to not bother with
    # this set of points. We'd just waste time
    if mx == -1:
      continue

    [rx, ry] = bruteforceEllipseBounds(points, combination, mx, my)

    # did we already find an ellipse? If no, this is the best candidate
    # so far and we'll mark it down later.
    # if yes, we check if the new ellipse is smaller than the old one
    if bestArea > 0:
      nbb = rx * ry
      if nbb < bestArea:
        # print("[[[ N E W   B E S T   S O L U T I O N]]]")
        # print ("mx, my, rx, ry")
        # print (bestBounds)
        bestArea = nbb
        bestBounds = [mx, my, rx*2, ry*2]
    else:
      bestArea = rx * ry
      bestBounds = [mx, my, rx*2, ry*2]
      # print("BEST AREA:")
      # print([bestArea, [mx, my], [rx, ry]])
      
    
  # print ("::")
  # print ("mx, my, rx, ry")
  # print (bestBounds)

  return bestBounds

def getEllipseDimensions(rows, xpad, ypad):
  # uh oh
  #
  # returns [x,y,width,height]
  #
  # Ideally, we'd draw an ellipse such that all the points would be:
  #      * inside the ellipse
  #      * as close as possible to the edge of the ellipse.
  #
  # That's a bit hard, though, so we'll have to do with an approximation.
  # see: https://math.stackexchange.com/a/207837
  # and even this is cancer so ...
  #  
  # Quick reminder. Rows coords are like this: top, bottom, left, right 
  #
  # NOTE: gimp-image-select-ellipse takes arguments (x,y,width,height) AS
  #       A FLOAT, which means we don't have to round stuff.
  #       source: procedure browser in gimp (see: help menu)

  rowCount = len(rows)

  edgePoints = []

  # determine edge points and offset a tiny bit to ensure a solution exists
  # when calculating ellipse dimensions
  for i in xrange(0, -(-rowCount // 2)):
    # Instead of having one point per corner, we add extra points which take
    # vertical and horizontal offset into account (a,b instead of x)
    #       a    
    #     b x-----
    #       | text corner
    #

    edgePoints.append([float(rows[i][2]), float(rows[i][0])])
    edgePoints.append([float(rows[i][3]), float(rows[i][0])])

  for i in xrange(rowCount // 2, rowCount):
    # offset x, left then right
    edgePoints.append([float(rows[i][2]), float(rows[i][1])])
    edgePoints.append([float(rows[i][3]), float(rows[i][1])])

  return calculateEllipseBounds_bruteforce(edgePoints)
  
def selectEllipse(image, layer, rows, xpad, ypad):
  # making things more readable

  offset_x = layer.offsets[0]
  offset_y = layer.offsets[1]

  # oh boi. Let's start by putting the function that calculated ellipse dimensions
  # into its own function in a bid to clean things up a bit
  #
  # returns [center_x, center_y, width, height] (note: center points are relative to
  # the layer)
  
  dims = getEllipseDimensions(rows, xpad, ypad)
  
  toolOffset_x = dims[2] // 2
  toolOffset_y = dims[3] // 2

  # correct coordinates and grow the ellipse  
  select_x = dims[0] - toolOffset_x - xpad + offset_x
  select_y = dims[1] - toolOffset_y - ypad + offset_y

  select_w = dims[2] + 2 * xpad
  select_h = dims[3] + 2 * ypad


  # image, operation (0 - add), x, y, w, h)
  pdb.gimp_image_select_ellipse(image, CHANNEL_OP_ADD, select_x, select_y, select_w, select_h)

def mkbubble (image, layer, isRound, minStepSize, xpad, ypad):
  # NOTE: image parameter is needed by select functions later down the line.
  # NOTE: this creates selection (and adds it to existing one). It doesn't
  # actually fill the bubble, so I suppose the name is a bit misleading

  # TODO: check for empty/non-text layers. If layer is devoid of text, do not
  # select it. 100% transparent layers can hang the program and garbage input
  # _will_ produce garbage result. Pro tip: non-text input is garbage input.

  textRows = determineTextRows(layer)

  if isRound:
    selectEllipse(image, layer, textRows, xpad, ypad)
  else:
    textRows = correctRows(textRows, minStepSize)
    selectRectangle(image, layer, textRows, xpad, ypad)

def mkoutline (image, thickness, feather):
  if thickness > 0:
    grow_selection(image, thickness)
  if feather > 0:
    feather_selection(image, feather)

def autobubble_group( image, layer_group, auto = True, isRound = True, minStepSize = 25, xpad = 7, ypad = 3, separate_groups = True, separate_layers = False, merge_source = False, outline = False, outline_thickness = 3, outline_feather = 0, merge_outline = False ):
  # TODO: optionally set parameters from layer full name
  # NOTE: parameter from layer full name override function call
  
  # get children of currently active layer group
  # returns [group layer id, [array with sublayer ids]]
  # if we do dis, we only get array with sublayer ids
  sublayers = pdb.gimp_item_get_children(layer_group)[1]
  
  fgcolor = ''
  bgcolor = ''
  texts_processed = 0

  skip = False
  argPass = '()=>skip'
  preserveCmd = False

  if auto:
    try:
      arguments = parse_args_from_layer_name(layer_group.name)
      for arg in arguments:
        if arg[0] == 'end':
          return
        if arg[0] == 'skip':
          skip = True
        if arg[0] == 'ellipse':
          isRound = True
        elif arg[0] == 'rectangle':
          isRound = False
        elif arg[0] == 'min_step':
          minStepSize = int(arg[1])
        elif arg[0] == 'xpad':
          xpad = int(arg[1])
        elif arg[0] == 'ypad':
          ypad = int(arg[1])
        elif arg[0] == 'separate_groups':
          separate_groups = True
          separate_layers = False
        elif arg[0] == 'separate_layers':
          separate_groups = False
          separate_layers = True
        elif arg[0] == 'merge_source':
          merge_source = True
        elif arg[0] == 'no_merge_source':
          merge_source = False
        elif arg[0] == 'outline':
          outline = True,
          tmpo = arg[1].split(',')
          outline_thickness = tmpo[0]
          if len(tmpo) > 1:
            outline_feather = tmpo[1]
        elif arg[0] == 'merge_outline':
          merge_outline = True
        elif arg[0] == 'no_merge_outline':
          merge_outline = False
        elif arg[0] == 'no_auto':
          auto = False
        elif arg[0] == 'color':
          fgcolor = arg[1]
        elif arg[0] == 'outline_color':
          bgcolor = arg[1]
        elif arg[0] == 'pass':
          argPass = arg[1]
        elif arg[0] == 'preserve_cmd':
          preserveCmd = True

    except:
      print("No arguments for this layer group, recursing only on children layer groups")
      for layerId in sublayers:
        layer = gimp.Item.from_id(layerId)
        
        # we ignore hidden layers
        if not layer.visible:
          continue
        
        # autobubble layer groups
        if type(layer) is gimp.GroupLayer:
          autobubble_group(image, layer, auto, isRound, minStepSize, xpad, ypad, separate_groups, separate_layers, merge_source, outline, outline_thickness, outline_feather, merge_outline)
      return


  if fgcolor:
    set_fg_stack(fgcolor)

  if bgcolor:
    set_bg_stack(bgcolor)

  if separate_groups:
    group_layers = []

    for layerId in sublayers:
      layer = gimp.Item.from_id(layerId)

      # we ignore hidden layers
      if not layer.visible:
        continue
      
      # we hide layer gropups and put them on a "handle me later pls" list
      if type(layer) is gimp.GroupLayer:
        group_layers.append(layer)
      else:
        pl = layer.parasite_list()
        if pl and pl[0] == 'gimp-text-layer':
          # process all non-group layers
          # print("started processing layer " + layer.name)
          mkbubble(image, layer, isRound, minStepSize, xpad, ypad)
          # print(layer.name + " processed")
          texts_processed += 1

    if texts_processed > 0 and (not skip):
      # we've created bubbles for all layers (excluding groups). Now fill the bubble
      group_bubble_layer = add_layer_below(image, layer_group, preserveCmd, argPass)
      paint_selection_fg(group_bubble_layer)

      # if bubbles have an outline
      if outline:
        group_bubble_outline_layer = add_layer_below(image, group_bubble_layer, preserveCmd, argPass, '-outline')
        mkoutline(image, outline_thickness, outline_feather)
        paint_selection_bg(group_bubble_outline_layer)

        if merge_outline:
          name = group_bubble_layer.name
          mergedLayer = pdb.gimp_image_merge_down(image, group_bubble_layer, EXPAND_AS_NECESSARY)
          mergedLayer.name = name
      
    clear_selection(image)

    # now it's recursion o'clock:
    # (and yes, we do recursion)
    for layer in group_layers:
      if layer.visible:
        # print("started processing group " + layer.name)
        autobubble_group(image, layer, auto, isRound, minStepSize, xpad, ypad, separate_groups, separate_layers, merge_source, outline, outline_thickness, outline_feather, merge_outline)
        # print("group" + layer.name + "finished processing")

  else:
    # making bubbles on one layer group total has lots of things in common
    # with creating bubbles on separate layers for every speech bubble
    for layerId in sublayers:
      layer = gimp.Item.from_id(layerId)
      
      # we ignore hidden layers
      if not layer.visible:
        continue
      
      # we hide layer gropups and put them on a "handle me later pls" list
      if type(layer) is gimp.GroupLayer:
        # group_layers.append(layer)
        autobubble_group(image, layer, isRound, minStepSize, xpad, ypad, separate_groups, separate_layers, merge_source, outline, outline_thickness, outline_feather, merge_outline)
        continue
      elif not skip: 
        # process all non-group layers
        mkbubble(image, layer, isRound, minStepSize, xpad, ypad)

        # if we separate layers, we do that here. Otherwise, we do that after
        # calling this function.
        if separate_layers:
          bubble_layer = add_layer_below(image, layer, preserveCmd, argPass)
          paint_selection_fg(bubble_layer)

          # if bubbles have an outline
          if outline:
            bubble_outline_layer = add_layer_below(image, bubble_layer, preserveCmd, argPass, '-outline')
            mkoutline(image, outline_thickness, outline_feather)
            paint_selection_bg(bubble_outline_layer)

            if merge_outline:
              name = group_bubble_layer.name
              mergedLayer = pdb.gimp_image_merge_down(image, group_bubble_layer, EXPAND_AS_NECESSARY)
              mergedLayer.name = name
          
          # merge source is a valid strat here
          if merge_source:
            name = layer.name         # save name of original layer
            merged_layer = pdb.gimp_image_merge_down(image, layer, EXPAND_AS_NECESSARY)
            merged_layer.name = name  # restore name of original layer

          clear_selection(image)

  if fgcolor:
    restore_fg_stack()

  if bgcolor:
    restore_bg_stack()  


# main function
def python_autobubble(image, layer, auto = True, isRound = True, minStepSize = 25, xpad = 7, ypad = 3, separate_groups = True, separate_layers = False, merge_source = False, outline = False, outline_thickness = 3, outline_feather = 0, merge_outline = False ):
  # save background
  bg_save = gimp.get_background()
  fg_save = gimp.get_foreground()

  clear_selection(image)

  isGroupLayer = type(layer) is gimp.GroupLayer
  # treat group layers differently
  if isGroupLayer:
    autobubble_group(image, layer, auto, isRound, minStepSize, xpad, ypad, separate_groups, separate_layers, merge_source, outline, outline_thickness, outline_feather, merge_outline)
  else:
    mkbubble(image, layer, isRound, minStepSize, xpad, ypad)

  # remember the 'we do that after calling the function' bit from earlier?
  # this is where it gets done
  if not (separate_groups or separate_layers):
    bubble_layer = add_layer_below(image, layer)
    paint_selection_fg(bubble_layer)

    # if bubbles have an outline
    if outline:
      bubble_outline_layer = add_layer_below(image, layer)
      mkoutline(image, outline_thickness, outline_feather)
      paint_selection_bg(bubble_outline_layer)

      if merge_outline:
        name = bubble_layer.name
        mergedLayer = pdb.gimp_image_merge_down(image, bubble_layer, EXPAND_AS_NECESSARY)
        mergedLayer.name = name
    
    # merge source is a valid strat here
    if merge_source:
      name = layer.name         # save name of original layer
      merged_layer = pdb.gimp_image_merge_down(image, layer, EXPAND_AS_NECESSARY)
      merged_layer.name = name  # restore name of original layer

  # clear selection because we're nice
  clear_selection(image)

  # at last, restore background
  gimp.set_background(bg_save)
  gimp.set_foreground(fg_save)

def python_test(image, isRound, minStepSize, xpad, ypad, isOutline):
  python_autobubble(image, image.active_layer, isRound, minStepSize, xpad, ypad, True, False, False, isOutline, 3, 0, True)

def python_test_auto():
  img = gimp.image_list()[0]
  python_autobubble(img, img.active_layer, True)


# register plugin.
# register(
#   "python_fu_autobubble",                                   # name
#   "Automatically draw speech bubbles around text layers.",  # plugin tl;dr
#   "Automatically draw speech bubbles around text layers.",  # "help"
#   "Tamius Han",                                             # Author
#   "Tamius Han",                                             # Copyright
#   "2018-2019",                                              # Date
#   "<Image>/Filters/Render/_Auto-bubble",                    # Menu path
#   "*",                                                      # Image type
#   [                                                         # params

#   ],
#   [],                                                       # results
#   python_autobubble                                         # script function
# )

# main()
