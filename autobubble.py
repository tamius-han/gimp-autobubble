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
bubble_layer = image.active_layer

# ellipse
layer = image.active_layer
rows = determineTextRows(layer)
drawEllipseBubble(image, rows, layer, bubble_layer, 0, 0)


# rectangle
layer = image.active_layer
rows = determineTextRows(layer)
rows = correctRows(rows, 20)
drawRectangularBubble(image, rows, layer, bubble_layer, 0, 0)

-- reload --
execfile('projects/gimp-autobubble/autobubble.py')
"""

import math
import copy
import itertools
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
    select_x = rows[i][2] - xpad + offset_x
    select_y = rows[i][0] - ypad + offset_y
    select_w = rows[i][3] - rows[i][2] + (2*xpad)
    select_h = rows[i][1] - rows[i][0] + (2*ypad)

    # image, operation (0 - add), x, y, w, h)
    pdb.gimp_image_select_rectangle(image, 0, select_x, select_y, select_w, select_h)

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
      pdb.gimp_image_select_rectangle(image, 0, select_x, select_y, select_w, select_h)

  # fill all at once
  # drawable/layer, fill mode (1 - bg), x, y (anywhere goes cos selection)
  pdb.gimp_edit_bucket_fill_full(bubble_layer, BUCKET_FILL_BG, LAYER_MODE_NORMAL, 100, 0, 0, 1, 0, 1, 1)

  # end

def getSolutionVectorSpaceInverted(points):
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
    
    # pivot needs to be equal to 1, so divide the entire row with the pivot
    # pivot = matrix[row][col]
    # for i in xrange(0, cols):
    #   matrix[row][i] /= pivot

    # for all rows, do this. Skip rows with comparatively small pivots,
    # they're 0 for all practical intents and purposes
    for i in xrange(0, rows):
      if i == row:
        continue
      factor = matrix[i][col] / matrix[row][col]
      for j in xrange(0, cols): # for all elements in current row
        matrix[i][j] = round(matrix[i][j] - matrix[row][j] * factor, 5)
    if abs(matrix[row][col]) < 0.25:
      matrix[row][col] = 0.0      # since they're practically 0 ...
       
    
    row += 1
    col += 1
  
  # invert pls
  # for r in xrange(0, rows):
  #   for c in xrange(0, cols):
  #     matrix[r][c] = round(matrix[r][c], 4)
      
  #     if matrix[r][c] != 0:
  #       matrix[r][c] = round( (1.0 / matrix[r][c]), 4)

  return matrix

def bruteforceEllipseBounds(points, pset, mx, my):
  maxx = points[0][0]; maxy = points[0][1], minx = points[0][0], miny = points[0][1]

  iterations = 20
  stepRelative = 0.75
  stepRelative_arStage_outer = 0.99
  stepRelative_arStage_inner = 0.98

  for p in range(1, len(points)):
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
    for point in pset:
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
  # possible values — if we find a solution that has greater area than
  # the best current solution, we return best width and height without
  # searching further as we aren't going to find a better solution
  iterations = 20
  innerSteps = 10

  bestArea = ew * eh
  bestw = ew
  besth = eh

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
      for point in pset:
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
        else:
          break   # we won't find a better solution this iteration
    
    if not hasBeenInEllipse:
      break       # if this iteation has never been in an ellipse, subsequent
                  # iterations won't be either
  
  # return best radius:
  return [bestw, besth]

def calculateEllipseBounds(points):
  bestArea = -1
  bestBounds = [0, 0, -1, -1]

  for combination in itertools.combinations(points, 4):
    print("")
    print("")
    print("<starting new loop>")
    matrix = getSolutionVectorSpaceInverted(combination)
    # for i in xrange(3, 4): 
    #   for j in xrange(0, 4):  # let's not round the last column
    #     matrix[i][j] = round(matrix[i][j], 0)


    print ("-----------------")
    print ("new matrix with solution:")
    for row in matrix:
      print (row)


    # we're using abcd (and mx, my, s, rx, and ry) because mathexchange answer this
    # algorithm is based on used these letters. Using same letters makes following 
    # this answer truly that much easier
    #    src: https://math.stackexchange.com/a/207837
    # 
    # we can spot whether our group of points has a solution just by looking at the 
    # matrix. If we get something like this, we can calculate everything:
    #   
    #     w:   [ 1 0 0 0 a ]
    #     x:   [ 0 1 0 0 b ]
    #     y:   [ 0 0 1 0 c ]
    #     z:   [ 0 0 0 1 d ]
    #
    # If a, b, c, or d are 0, we're dealing with an invalid point combination (no 
    # ellipse to be had here), so we'll just skip it. If all four are non-zero value,
    # we'll do this:
    #
    #     w:   [ 1/a 0  0  0  a/a ]
    #     x:   [  0 1/b 0  0  b/b ]
    #     y:   [  0  0 1/c 0  c/c ]
    #     z:   [  0  0  0 1/d d/d ]
    #
    # Now, 'a', 'b', 'c' and 'd' are all expressed as multiple (or fraction) of 'e'
    # 
    # Of course, a question quickly arises. What is e? I don't know, but in practice
    # having 'e' set to -1 seems to work so far. 

    # We can probably catch valid cases with first 4 comparrisons, but we'll add the
    # rest just to be sure. We can also try to minimize conditions a bit (as first and
    # second row must also be valid in some other scenarios)
    a = 0.0; b = 0.0; c = 0.0; d = 0.0; e = 0.0; mx = 0.0; my = 0.0; s = 0.0
    if matrix[0][1] == 0 and matrix[0][4] != 0 and matrix[1][1] != 0.0 and matrix[1][4] != 0.0:
       
      if matrix[2][2] != 0.0 and matrix[2][4] != 0.0 and matrix[3][3] != 0.0 and matrix[3][4] != 0.0:
        print("Calculating ellipse is possible!")
        a = (matrix[0][4]/matrix[0][0])
        b = (matrix[1][4]/matrix[1][1])
        c = (matrix[2][4]/matrix[2][2])
        d = (matrix[3][4]/matrix[3][3])
        e = -1.0

        # that's the center of the ellipse
        mx = - c / (2 * a)
        my = - d / (2 * b)

      # If we get something like this, we can only calculate 1 coordinate of the center. 
      #   
      #     w:   [ 1 0 0 0 a ]
      #     x:   [ 0 1 0 0 b ]
      #     y:   [ 0 0 ? ? c ]
      #     z:   [ 0 0 0 0 ? ]
      #
      # In cases like this, we'll calculate the other coordinate by intersecting the line 
      # we get with the longest diagonal we can find. 
      # (NOTE: this can probably be optimized)
      elif matrix[2][2] != 0 and matrix[2][4] != 0:
        print("Calculating middle vertical point using alternative method")
        a = (matrix[0][4]/matrix[0][0])
        c = (matrix[2][4]/matrix[2][2])
        e = -1.0

        mx = - c / (2 * a)

        # time to calculate my using a different approach
        # split points into two groups: those left and those right of mx
        left = []; right = []
        for point in combination: 
          if point[0] - mx < 0:
            left.append(point)
          else:
            right.append(point)
        
        

        print("mx: {}".format(mx))
        print("halves:")
        print([left, right])

        # i dont know how that happened, but it did at least once.
        if len(left) == 0 or len(right) == 0:
          print("uwu oopsie whoopsie. We've just had a fucky wucky. All points are on the same side of mx for some reason. Skipping this set.")
          continue


        # calculate the longest distance from any point in left set to any point in right set
        fromLeft = left[0]; fromRight = right[0]
        bestDistance = ((fromLeft[0] - fromRight[0]) ** 2 ) + ((fromLeft[1] - fromRight[1]) ** 2)


        for pl in left:
          bestVertDiff = 0.0
          for pr in right:
            vdiff = abs(pl[1] - pr[1])
            if vdiff < bestVertDiff:
              continue
            
            bestVertDiff = vdiff
            distance = ((pl[0] - pr[0]) ** 2) + ((pl[1] - pr[1]) ** 2)
            if distance > bestDistance:
              bestDistance = distance
              fromLeft = pl
              fromRight = pr
        
        # see where the line between fromLeft and fromRight intersects mx
        top = min(fromRight[1], fromLeft[1])
        bottom = max(fromRight[1], fromLeft[1])

        textHeight = top - bottom
        textWidth = fromRight[0] - fromLeft[0]

        slopeDirection = 1
        if top == fromRight[1]:
          slopeDirection = -1

        # slope = diffY / diffX
        slope = textHeight / textWidth
        dx = (mx - fromLeft[0]) / textWidth
        dy = dx * slope

        if slopeDirection == 1:
          my = top + dy
        else:
          my = bottom - dy
        
        # right, we got the other center. This means we can calculate 'd' by turning our previous
        # equation around a bit:
        # my = - d / (2 * b), and b is ... matrix[1][3]d + matrix[1][4]e
        d = - (matrix[1][4] * e * my) / (matrix[1][3] * mx + 1)
        b = d * matrix[1][3] + matrix[1][4] * e




    # else:
    #   if matrix[0][4] == 0 or matrix[1][4] == 0 or matrix[2][4] == 0 or matrix[3][4] == 0:
    #     print("one of the values is null")
    #     continue

    # now we can extract variables much the same way we did before:
    
    # c = - matrix[0][0] / matrix[0][2]
    # d = - matrix[1][1] / matrix[1][3]
    

    # If we get something like this (where 'x' is non-zero number, and 1 is
    # a pivot (but not neccesarily actually equals 1)):
    #
    #        [ 1 0 x 0 0 ]
    #        [ 0 1 0 x 0 ]
    #        [ 0 0 0 0 1 ]
    #        [ 0 0 0 0 0 ]
    #
    # In case like this, we can only determine the center.
    centerOnly = matrix[0][0] != 0 and matrix[0][1] == 0 and matrix[0][2] != 0 and matrix[0][3] == 0 and matrix[0][4] == 0 \
                 and matrix[1][1] != 0 and matrix[1][2] == 0 and matrix[1][3] != 0 or matrix[1][4] == 0 \
                 and matrix[2][2] == 0 and matrix[2][3] == 0 and matrix[2][4] != 0

    if centerOnly:
      # get center

      mx = 1 / (2 * (matrix[0][0] / matrix[0][2]))
      my = 1 / (2 * (matrix[1][1] / matrix[1][3]))

      # bruteforce the rest
      [rx, ry] = bruteforceEllipseBounds(points, pset, mx, my)

      # did we already find an ellipse? If no, this is the best candidate
      # so far and we'll mark it down later.
      # if yes, we check if the new ellipse is smaller than the old one
      if bestArea > 0:
        nbb = rx * ry
        if nbb < bestArea:
          print("[[[ N E W   B E S T   S O L U T I O N]]]")
          print ("mx, my, rx, ry")
          print (bestBounds)
          bestArea = nbb
          bestBounds = [mx, my, rx*2, ry*2]
      else:
        bestArea = rx * ry
        bestBounds = [mx, my, rx*2, ry*2]

      # we don't do the rest of the things in this case, becasue 
      # we've achieved them differently
      continue

    # we know we're looking at ellipse if:
    #   * a and b have the same sign (both negative or both positive)
    #   * neither a nor b is zero
    # we skip those vectors
    if a * b <= 0:
      print("sign mismatch")
      print("a: {}, b: {}".format(a,b))
      continue


    # let's round the stuff a bit
    # a = round(a, 4)
    # b = round(b, 4)
    c = round(c, 4)
    d = round(d, 4)
    # s stands for ... something? idk
    s = (c ** 2) / (4 * a) + (d ** 2) / (4 * b) - e
   
    print("a, b, c, d, e, s:")
    print([a,b,c,d,e, s])

    if s * a <= 0 or s * b <= 0:
      print("sign mismatch (s, a, b need to have matching signs). Skipping point combination.")
      continue

    # so all the points are inside the ellipse. Let's find radius.
    rx = (s / a) ** 0.5
    ry = (s / b) ** 0.5

    # check if all points are inside or, at worst, on the ellipse
    inEllipse = True
    for p in points:
      res = (a/s) * ((p[0] - mx) ** 2) + (b/s) * ((p[1] - my) ** 2)

      print ("[RES] : point/m")
      print ([res, [(p[0], mx),(p[1], my)]])
      # if this happens, the point is outside the ellipse. Stop searching
      if res > 1:
        inEllipse = False
        break

    if not inEllipse:
      continue

    

    # did we already find an ellipse? If no, this is the best candidate
    # so far and we'll mark it down later.
    # if yes, we check if the new ellipse is smaller than the old one
    if bestArea > 0:
      nbb = rx * ry
      if nbb < bestArea:
        print("[[[ N E W   B E S T   S O L U T I O N]]]")
        print ("mx, my, rx, ry")
        print (bestBounds)
        bestArea = nbb
        bestBounds = [mx, my, rx*2, ry*2]
    else:
      bestArea = rx * ry
      bestBounds = [mx, my, rx*2, ry*2]

    
    print ("::")
    print ("mx, my, rx, ry")
    print (bestBounds)

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

    edgePoints.append([float(rows[i][2]) -0.5, float(rows[i][0]) - 0.5])
    edgePoints.append([float(rows[i][3]) -0.5, float(rows[i][0])])

  for i in xrange(rowCount // 2, rowCount):
    # offset x, left then right
    edgePoints.append([float(rows[i][2]), float(rows[i][1]) - 0.5])
    edgePoints.append([float(rows[i][3]), float(rows[i][1])])

  return calculateEllipseBounds(edgePoints)
  
def drawEllipseBubble(image, rows, layer, bubble_layer, xpad, ypad):
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
  pdb.gimp_image_select_ellipse(image, 0, select_x, select_y, select_w, select_h)
  # pdb.gimp_drawable_edit_bucket_fill(bubble_layer, 1, 1, 1)
  pdb.gimp_edit_bucket_fill_full(bubble_layer, BUCKET_FILL_BG, LAYER_MODE_NORMAL, 100, 0, 0, 1, 0, 1, 1)


 
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
