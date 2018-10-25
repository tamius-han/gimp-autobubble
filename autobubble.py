#!/usr/bin/env python

# docs: https://www.gimp.org/docs/python/index.html
# 
# cheat sheet for gimp for when manually doing stuff in console:
#     active image:      gimp.image_list()[0]
#     active layer:      <image>.active_layer()
#
# execfile('projects/gimp-autobubble/autobubble.py')

import math
import copy
from gimpfu import *

# I tried looking for proper solution that gets position of a given layer
# in the layer stack. Google didn't yield anything useful, and text outliner
# plugin confirmed inexistance of an object property that would just give me
# the position of the layer. Ok then, let's roll our own.
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
  if edge1 > edge2 - minStepSize and edge1 < edge2 + minStepSize:
    if edge1 > edge2:
      return 1
    else: 
      return -1
  
  return 0

def correctRows(rows, minStepSize):
  if len(rows) < 2:
    return rows #there's nothing to do if we only have one row
  
  # correct jags in the left edge
  for i in xrange(0, len(rows) - 2):
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
  for i in xrange(0, len(rows) - 2):
    jag = findJag(rows[i][3], rows[i+1][3], minStepSize)
    if jag == 1:
      rows[i+1][3] = rows[i][3]
    if jag == -1:
      rows[i][3] = rows[i+1][3]
      if i > 0:
        for j in range(i - 1, -1, -1):
          rows[j][3] = rows[i][3]
  
  return rows

def drawRectangularBubble(image, rows, layer, bubble_layer, xpad, ypad):
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
    select_x = offset_x + rows[i][2] - xpad
    select_y = offset_y + rows[i][0] - ypad
    select_w = rows[i][3] - rows[i][2] + (2*xpad)
    select_h = rows[i][1] - rows[i][0] + (2*ypad)

    # image, operation (0 - add), x, y, w, h)
    pdb.gimp_image_select_rectangle(image, 0, select_x, select_y, select_w, select_h)
    # drawable/layer, fill mode (1 - bg), x, y (anywhere goes cos selection)
    # ensure current row is connected with row on top (unless the gap between two rows is
    # bigger than our treshold)
    if i > 0 and rows[i][0] - rows[i-1][1] < connect_rows_treshold:
      select_x = max(rows[i][2], rows[i-1][2])
      select_w = min(rows[i][3], rows[i-1][3]) - select_x + (2*xpad)
      select_x += offset_x - xpad

      pdb.gimp_image_select_rectangle(image, 0, select_x, rows[i-1][1], select_w, rows[i][0])
    
    pdb.gimp_edit_bucket_fill_full(bubble_layer, 1, 28, 100, 0, 0, 1, 0, 1, 1)

  # end

def getSolutionVectorSpace(points):
  matrix = [
    [points[0][0] ** 2, points[0][1] ** 2, points[0][0], points[0][1], 1],
    [points[1][0] ** 2, points[1][1] ** 2, points[1][0], points[1][1], 1],
    [points[2][0] ** 2, points[2][1] ** 2, points[2][0], points[2][1], 1],
    [points[3][0] ** 2, points[3][1] ** 2, points[3][0], points[3][1], 1]
  ]
  # dont do this
  rows = 4
  cols = 5

  row = 0; col = 0

  while row < rows and col < cols:
    maxElement = abs(matrix[row][col])
    maxRow = row

    # find the pivot in the first column, swap rows if neccessary
    for j in xrange(row+1, rows):
      if abs(matrix[j][col]) > maxElement:
        maxElement = abs(matrix[j][col])
        maxRow = j
    
    # if there's no pivot, skip this column
    if matrix[maxRow][col] == 0:
      col += 1
      continue

    # swap rows if neccessary
    if maxRow != row:
      for i in xrange(col, cols):
        tmp = matrix[row][i]
        matrix[row][i] = matrix[maxRow][i]
        matrix[maxRow][i] = tmp
    
    # for all rows under pivot, do this
    for i in xrange(row + 1, rows):
      factor = matrix[i][col] / matrix[row][col]
      matrix[i][col] = 0              # fill column below pivot with zeroes
      for j in xrange(col + 1, cols): # for all elements in current row
        matrix[i][j] = matrix[i][j] - matrix[row][j] * factor
    
    row += 1
    col += 1
      
  return matrix




def calculateEllipseBounds(opposing_x, opposing_y, width, height, aspectRatio, arDelta = None):
  # width, height - max width and max height of the text

  # width = 0
  # height = 0
  new_w = 0
  new_h = 0

  # start calculating ellipses for every point we deemed worthy
  for i in xrange(0, len(opposing_x)):
    # first, squash the ellipse into a circle
    # here's a fun fact: we don't need to pair correct coordinates
    # from opposing side, as long as we get axes and pairings right

    half_i = i // 2
    t = math.atan2(opposing_y[half_i][0], (opposing_x[i][0] * aspectRatio))

    new_w = abs((opposing_x[i][0] * aspectRatio / math.cos(t)) * 2)
    new_h = abs((opposing_y[half_i][0] / math.sin(t)) * 2)
  
    # not quite correct, but we'll just assume that both width and 
    # height increase at the asme time so ok I guess
    if new_w > width:
      width = new_w
    if new_h > height:
      height = new_h
    

    # repeat for the second opposing point in the pair
    t = math.atan2(opposing_y[half_i][1], (opposing_x[i][1] * aspectRatio))

    new_w = abs( (opposing_x[i][1] / math.cos(t)) * 2) * aspectRatio
    new_h = abs( (opposing_y[half_i][1] / math.sin(t)) * 2)

    # not quite correct, but we'll just assume that both width and 
    # height increase at the asme time so ok I guess
    if new_w > width:
      width = new_w
    if new_h > height:
      height = new_h
  
  return [width, height]

def getEllipseDimensions(rows):
  # consider making this an argument:
  iterations = 10

  # uh oh
  #
  # returns [x,y,width,height]
  #
  # Ideally, we'd draw an ellipse such that all the points would be:
  #      * inside the ellipse
  #      * as close as possible to the edge of the ellipse.
  #
  # That's a bit hard, though, so we'll have to do with an approximation:
  #      * calculate the "center" of the ellipse (average 
  #        middle point of all diagonals)
  #      * determine which point is the furthest from the
  #        middle point
  #      * draw ellipse through that point
  #  
  # Quick reminder. Rows coords are like this: top, bottom, left, right 
  #
  # NOTE: gimp-image-select-ellipse takes arguments (x,y,width,height) AS
  #       A FLOAT, which means we don't have to round stuff.
  #       source: procedure browser in gimp (see: help menu)

  rowCount = len(rows)

  opposing_x = []
  opposing_y = []
  center_x = []
  center_y = []

  if rowCount > 1:    # having one row is a bit of a special case
    for i in xrange(0, rowCount // 2):
      for j in range(rowCount - 1, (rowCount // 2), -1):
        # we need both to account for left/right skew, e.g if
        # rows are aligned like this:
        #    
        #      [xxxx row 1 xxxx]
        #    [...               ...]
        #        [xxxx row 2 xxxx]
        #
        opposing_x.append([float(rows[i][2]), float(rows[j][3])])
        center_x.append(float(rows[i][2] + rows[j][3]) / 2)
        opposing_x.append([float(rows[i][3]), float(rows[j][2])])
        center_x.append(float(rows[i][3] + rows[j][2]) / 2)
        
        # there's no vertical skew like that
        opposing_y.append([float(rows[i][0]), float(rows[j][1])])
        center_y.append(float(rows[i][0] + rows[j][1]) / 2)

  if rowCount % 2 == 1:     # btw this catches cases where len = 1
    i = rowCount // 2       # this also works both for middle line and cases 
                            # where len = 1
    
    # since we're adding middle last, this won't have a negative effect
    # later on where we rely on 'y' arrays having half the elements of 'x' 
    # arrays
    opposing_x.append([float(rows[i][2]), float(rows[i][3])])
    center_x.append(float(rows[i][0] + rows[i][1]) / 2)
    opposing_x.append([float(rows[i][2]), float(rows[i][3])])
    center_x.append(float(rows[i][0] + rows[i][1]) / 2)

    opposing_y.append([float(rows[i][0]), float(rows[i][1])])
    center_y.append(float(rows[i][0] + rows[i][1]) / 2)


  avg_x = sum(center_x) / float(len(center_x))
  avg_y = sum(center_y) / float(len(center_y))

  # middle point of the ellipse is now at avg_x, avg_y (relative to text layer)
  #
  # https://www.mathopenref.com/coordparamellipse.html
  #
  # Equations for ellipse (NOTE: assumes ellipse is centered at 0,0)
  # 
  #       x = a * cos(t)
  #       y = b * sin(t)
  #
  # x,y - coordinates of any point on the ellipse (known)
  # a,b - radii/axes (we'd like to know)
  # t   - some super secret parameter (angle from origin to
  #       the point on ellipse, if ellipse was squished to 
  #       a regular circle)
  #
  # Let's make our work easier and pretend we started drawing at 0,0 instead
  # of wherever the center of the ellipse is. Subtract center from coords:
  
  minx = 0
  maxx = 0
  miny = 0
  maxy = 0

  print ("START: opposing x:")
  print (opposing_x)
  print ("START: opposing y:")
  print (opposing_y)

  for i in xrange(0, len(opposing_x)):
    opposing_x[i][0] -= avg_x
    opposing_x[i][1] -= avg_x

    if opposing_x[i][0] < minx:
      minx = opposing_x[i][0]
    if opposing_x[i][0] > maxx:
      maxx = opposing_x[i][0]
    if opposing_x[i][1] < minx:
      minx = opposing_x[i][1]
    if opposing_x[i][1] > maxx:
      maxx = opposing_x[i][1]

  for i in xrange(0, len(opposing_y)):
    opposing_y[i][0] -= avg_y
    opposing_y[i][1] -= avg_y

    if opposing_y[i][0] < miny:
      miny = opposing_y[i][0]
    if opposing_y[i][0] > maxy:
      maxy = opposing_y[i][0]
    if opposing_y[i][1] < miny:
      miny = opposing_y[i][1]
    if opposing_x[i][1] > maxy:
      maxy = opposing_y[i][1]

  print ("-------------------------------")
  print ("POST: opposing x:")
  print (opposing_x)
  print ("POST: opposing y:")
  print (opposing_y)
  print ("POST: avg center")
  print ([avg_x, avg_y])

  # calculate some basic width and height
  innerWidth = maxx - minx
  innerHeight = maxy - miny
  
  xSquashRatio = innerHeight / innerWidth

  print ("--- x: min/max, y: min/max, width/height")
  print ([minx, maxx, miny, maxy, innerWidth, innerHeight])
  print("squash ratio: {}".format(xSquashRatio) )

  text_w = innerWidth
  text_h = innerHeight

  [innerWidth, innerHeight] = calculateEllipseBounds(opposing_x, opposing_y, text_w, text_h, xSquashRatio)
  
  # tighten ellipse a little bit, using brute force
  #
  # since we're only interested in size differences rather than exact
  # area size, we can ignore the PI and everything. 
  bestArea = innerWidth * innerHeight

  # TODO: optimize for cases where xSquashRatio comes out to be 1
  # shouldn't happen too often, though, so performing twice as much 
  # work once in a blue moon isn't that bad
  new_h = innerHeight
  new_w = innerWidth
  arlt = xSquashRatio * 0.5
  argt = xSquashRatio * 2
  newBestArea = bestArea
  
  if xSquashRatio <= 1:
    for i in xrange(1, iterations):
      [new_w, new_h] = calculateEllipseBounds(opposing_x, opposing_y, text_w, text_h, arlt)
      newBestArea = new_h * new_w
      if newBestArea < bestArea:
        innerHeight = new_h
        innerWidth = new_w
        bestArea = newBestArea
        arlt += xSquashRatio * (2 ** -i)
      else:
        arlt -= xSquashRatio * (2 ** -i)
    
  if xSquashRatio >= 1:
    for i in xrange(1, iterations):
      [new_w, new_h] = calculateEllipseBounds(opposing_x, opposing_y, text_w, text_h, argt)
      newBestArea = new_h * new_w
      if newBestArea < bestArea:
        innerHeight = new_h
        innerWidth = new_wsig
        bestArea = newBestArea
        argt -= xSquashRatio * (2 ** -i)
      else:
        argt += xSquashRatio * (2 ** -i)


  print ("final x/y offsets & width/height")
  print ( [avg_x, avg_y, innerWidth, innerHeight] )

  return [avg_x, avg_y, innerWidth, innerHeight]


def drawEllipseBubble(image, rows, layer, bubble_layer, xpad, ypad):
  # making things more readable

  offset_x = layer.offsets[0]
  offset_y = layer.offsets[1]

  # oh boi. Let's start by putting the function that calculated ellipse dimensions
  # into its own function in a bid to clean things up a bit
  #
  # returns [center_x, center_y, width, height] (note: center points are relative to
  # the layer)
  #
  #
  dims = getEllipseDimensions(rows)
  
  toolOffset_x = dims[2] // 2
  toolOffset_y = dims[3] // 2

  # correct coordinates and grow the ellipse  
  select_x = dims[0] - toolOffset_x - xpad + offset_x
  select_y = dims[1] - toolOffset_y - ypad + offset_y

  select_w = dims[2] + 2 * xpad
  select_h = dims[3] + 2 * ypad


  # image, operation (0 - add), x, y, w, h)
  pdb.gimp_image_select_ellipse(image, 0, select_x, select_y, select_w, select_h)
  # pdb.gimp_drawable_edit_bucket_fill(bubble_layer, 1, 1, 1)
  pdb.gimp_edit_bucket_fill_full(bubble_layer, 1, 28, 100, 0, 0, 1, 0, 1, 1)


 
def autobubble_layer(t_img, t_drawable, layer, bubble_layer, isRound, minStepSize, pad):
  # args:
  #     t_img
  #     t_drawable
  #     layer        - layer with text
  #     bubble_layer - layer on which to draw speech bubble
  #     isRound      - is buble an ellipse (True) or a rectangle (False)?
  #     minStepSize  - on rectangular bubbles, avoid "steps" that are shorter
  #                    than this many pixels long

  # determine where bounds of every text row layer are
  text_rows = determineTextRows(layer)

  # if the bubble isn't round (i.e. we're drawing a rectangle), we try to 
  # prevent some jaggedness. 
  if not isRound:
    text_rows = correctRows(text_rows, minStepSize)
    drawRectangularBubble(t_img, text_rows, layer, bubble_layer, 3, 3)



def autobubble_group(t_img, t_drawable, bubble_layer, isRound): 
  # get children of currently active layer
  # returns [group layer id, [array with sublayer ids]]
  # if we do dis, we only get array with sublayer ids
  sublayers = pdb.gimp_item_get_children(t_img.active_layer)[1]

  for layer_id in sublayers:
    layer = gimp.Item.from_id(layer_id)
    if type(layer) is gimp.GroupLayer:       # btw yes, we DO do recursion
      autobubble_group(t_img, t_drawable, bubble_layer, isRound)
    else:
      autobubble_layer(t_img, t_drawable, layer, bubble_layer, isRound)
    


# main function
def python_autobubble(t_img, t_drawable, isRound=True):
  # save background
  bg_save = gimp.get_background()

  # Bubbles will be drawn on their separate layer, which will be placed under
  # current layer
  bubble_layer = add_layer_below_currently_selected(t_img)

  # If activeLayer is a layer group, we run this script recursively for all
  # all layers in a group. 
  if type(t_img.active_layer) is gimp.GroupLayer:
    autobubble_group(t_img, t_drawable, bubble_layer, isRound)
  else:
    autobubble_layer(t_img, t_drawable, t_img.active_layer, bubble_layer, isRound)

  # at last, restore background
  gimp.set_background(bg_save)


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
