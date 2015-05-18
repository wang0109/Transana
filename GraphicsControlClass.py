#Copyright (C) 2003-2005  The Board of Regents of the University of Wisconsin System

#This program is free software; you can redistribute it and/or
#modify it under the terms of the GNU General Public License
#as published by the Free Software Foundation; either version 2
#of the License, or (at your option) any later version.

#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with this program; if not, write to the Free Software
#Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

# This code is taken from the wxPython Demo file "PrintFramework.py" and
# has been modified by David Woods

""" A class for implementing a scrollable Graphics Control.
    This control should expose it's Device Context for external
    manipulation (drawing) and so that it can be easily sent to
    a Printer.

    The following methods are currently implemented:
      __init__(parent,                   Parent Frame
               ID,                       ID
               pos=wxPoint(100, 100),    Position within Parent (Will be full frame if only control)
               size=(800, 600),          Size within Parent (Will be full frame if only control)
               canvassize=(999, 999),    Size of the underlying graphics canvas (Visual control will shrink to fit)
               drawEnabled=false,        Is free-hand drawing enabled?
               transanaMode=false)       Is this used in Transana?  (Cannot be used with drawEnabled, as both options specify how to process mouse events.)

      SetColour(colour)                  Sets Drawing Color (using wxNamedColours)
      SetFontColour(colour)              Sets Text Color (using wxNamedColours)
      SetThickness(thickness)            Sets Drawing Line Thickness
      SetFontSize(size)                  Sets Font Size
      AddLines(newlines)                 Adds lines to drawing.  Newlines are a list of 4-integer tuples, each specifying (startx, starty, endx, endy).
                                         Thus, [(300, 300, 300, 700), (300, 700, 700, 700), (700, 700, 700, 300), (700, 300, 300, 300)] draws a square.
      AddText(text, x, y)                Adds Text at position (x, y)
      AddTextCentered(text, x, y)        Adds Text centered on position (x, y)
      Clear()                            Clears the graphic
      GetMaxWidth(start=0)               Returns the width of the widest label in the list after start (which is used to skip titles)
      LoadFile(filename.bmp)             Loads a BITMAP image, which is resized to fit the control
      SaveAs                             Saves the Buffered Image as a JPEG graphic
      SetDimensions(x, y, width, height) Alters the dimensions of the Graphic Area, including resizing the underlying Bitmap if there is one.
    I anticipate adding more methods very soon to faciliate printing, to set text font properties, and to add more shape-drawing options.
    """

__author__ = 'David K. Woods <dwoods@wcer.wisc.edu>, Rajas Sambhare'

# import wxPython
import wx
# import Python's os module
import os

class GraphicsControl(wx.ScrolledWindow):
    """ Graphics Control Class implements a Graphic Control used for doing some
        low-level drawing in the Visualization Window and the Keyword Map """
    def __init__(self, parent, ID, pos=wx.Point(100, 100), size=(800, 600), canvassize=(999, 999), drawEnabled = False, transanaMode = False):
        self.parent = parent
        self.drawEnabled = drawEnabled
        self.transanaMode = transanaMode
        # The control should never be larger than the canvas, but should allow a margin (22, 22) for the scroll bars if needed.
        # With a small canvas, we allow 6 pixels for the frame.
        size = (min(size[0] + 22, canvassize[0] + 6), min(size[1] + 22, canvassize[1] + 6))
        # The main Graphics Canvas is built from a wxScrolledWindow
        gc = wx.ScrolledWindow.__init__(self, parent, ID, pos, size, wx.SUNKEN_BORDER)

        # Set the Background to White
        self.SetBackgroundColour(wx.WHITE)

        # We do not add ScrollBars in Transana Mode
        if transanaMode == False:
            # Add Scrollbars
            self.SetScrollbars(20, 20, int(round(canvassize[0]/20.0)), int(round(canvassize[1]/20.0)))

        # Set local variables
        self.canvassize = canvassize

        # Start with NO background graphic
        self.backgroundGraphicName = ''
        self.backgroundImage = None
        # Set default line color, pattern, and thickness
        self.thickness = 1
        self.linepattern = wx.SOLID
        self.SetColour("BLACK")
        # Set default text color, font size, font family, font style, and font weight
        self.textcolour = "BLACK"
        self.fontsize = 10
        self.fontfamily = wx.ROMAN
        self.fontstyle = wx.NORMAL
        self.fontweight = wx.NORMAL
        # Initialize "lines" to an empty list
        self.lines = []

        # Initialize  "text" to an empty list
        self.text = []
        # Initialize drawing position
        self.x = self.y = 0
        # Initialize Cursor Position, but be used to remove the cursor
        self.cursorPosition = None
        # Initialize startTime and endTime
        self.startTime = 0.0
        self.endTime = 0.0  # Set it to duration only if in transanaMode, see below
        self.isDragging = False
        self.reSetSelection = False
        self.lastRedTop = 0
        self.lastRedBottom = 0
        self.pixelList = []
        # Initialize the drawing buffer
        self.InitBuffer()

        # If free-hand drawing is enabled, intialize the drawing flag and cursor and define the related events
        if drawEnabled:
            self.drawing = False
            self.SetCursor(wx.StockCursor(wx.CURSOR_PENCIL))
            # Mouse Events used for free-hand drawing
            wx.EVT_LEFT_DOWN(self, self.OnLeftDown)
            wx.EVT_LEFT_UP(self, self.OnLeftUp)
            wx.EVT_MOTION(self, self.OnMotion)
        elif transanaMode:
            self.drawing = False
            self.SetCursor(wx.StockCursor(wx.CURSOR_CROSS))
            # Mouse Events for Transana's Click and Select behavior
            wx.EVT_LEFT_DOWN(self, self.TransanaOnLeftDown)
            wx.EVT_LEFT_UP(self, self.TransanaOnLeftUp)
            wx.EVT_MOTION(self, self.TransanaOnMotion)
            wx.EVT_RIGHT_UP(self, self.TransanaOnRightUp)
            self.endTime = self.parent.TimeCodeFromPctPos(1.0) #Timecode of 100% == Duration

        # Resize Event
        wx.EVT_SIZE(self, self.OnSize)
        
        # Idle event (draws when idle to prevent multiple redraws)
        wx.EVT_IDLE(self, self.OnIdle)

        # Refresh Event
        wx.EVT_PAINT(self, self.OnPaint)

        # Show the Graphic Control
        self.Show(True)

        # Return the Control
        return gc

    def getWidth(self):
        return self.canvassize[0]

    def getHeight(self):
        return self.canvassize[1]

    def Clear(self):
        """ Clear the Graphic Control """
        # Remove all lines
        self.lines = []
        # Clear the Cursor Position
        self.cursorPosition = None
        # Remove all text
        self.text = []
        # Remove background graphic
        self.backgroundGraphicName = ''
        self.backgroundImage = None
        # Signal the need to redraw the control
        self.reInitBuffer = True

    def ClearTransanaSelection(self):
        """ Clears the Waveform Selection (highlight) set up by Transana """
        # Remove all lines (the Selection and the Cursor)
        self.lines = []

        # self.SetColour("CYAN")
        # self.SetThickness(2)
        # self.AddLines([(0, 0, self.getWidth(), 0), (self.getWidth(), 0, self.getWidth(), self.getHeight()), (self.getWidth(), self.getHeight(), 0, self.getHeight()), (0, 0, 0, 0)])
        # print "CYAN"

        # Clear the Cursor Position
        self.cursorPosition = None

        self.startTime = 0.0
        self.endTime = 0.0

    def SetColour(self, colour):
        """ Set color and create the appropriate Pen """
        self.colour = colour
        self.pen = wx.Pen(wx.NamedColour(self.colour), self.thickness, self.linepattern)

    def SetFontColour(self, colour):
        """ Set text color """
        self.textcolour = colour

    def SetThickness(self, thickness):
        """ Set Line Thickness """
        self.thickness = thickness
        self.pen = wx.Pen(wx.NamedColour(self.colour), self.thickness, self.linepattern)

    def SetFontSize(self, size):
        """ Set Font Size """
        self.fontsize = size

    def AddLines(self, newlines):
        """ Adds new lines (send as a list) to the drawing """
        self.lines.append((self.colour, self.thickness, newlines))
        self.reInitBuffer = True

    def AddText(self, text, x, y):
        """ Adds new Text Objects to the drawing """
        self.text.append((text, x, y, self.textcolour, self.fontsize, self.fontfamily, 'LEFT'))
        self.reInitBuffer = True

    def AddTextCentered(self, text, x, y):
        """ Adds new Text Objects to the drawing, centered on the point submitted """
        self.text.append((text, x, y, self.textcolour, self.fontsize, self.fontfamily, 'CENTER'))
        self.reInitBuffer = True

    def AddTextRight(self, text, x, y):
        """ Adds new Text Objects to the drawing, right justified on the point submitted """
        self.text.append((text, x, y, self.textcolour, self.fontsize, self.fontfamily, 'RIGHT'))
        self.reInitBuffer = True

    def InitBuffer(self):
        """ Initialize the Bitmap used for buffering the display """

        # Initialize the Buffer to an empty Bitmap
        self.bmpBuffer = wx.EmptyBitmap(self.canvassize[0], self.canvassize[1])

        # If a Background Graphic is defined, load it as the base graphic.  Otherwise, create an empty bitmap.
        if self.backgroundGraphicName != '':
            # If the image is already loaded in memory, use that.  Otherwise, go to the disk.
            if self.backgroundImage != None:
                # TODO: Implement better rescaling. Rescale background image
                # Convert the wxImage to a wxBitmap
                tempBitmap = wx.BitmapFromImage(self.backgroundImage)
                # Set the active image (self.bmpBuffer) to the Bitmap
                self.bmpBuffer = tempBitmap
            else:
                self.LoadFile(self.backgroundGraphicName)
            # Create a Buffered Device Context using the initial bitmap
            dc = wx.BufferedDC(None, self.bmpBuffer)

        else:
            # Create a Buffered Device Context using the initial bitmap
            dc = wx.BufferedDC(None, self.bmpBuffer)

            # Set the Brush and Background colors to the Background Color
            dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
            # Clear the drawing
            dc.Clear()  

        # Set the Pen to the defined Color, thickness, and pattern
        self.pen = wx.Pen(wx.NamedColour(self.colour), self.thickness, self.linepattern)
        # Draw lines based on timecodes
        # You can choose two different methods. 
        #   a. DrawRect: Very responsive, covers selection with grey diagonal lines
        #   b. SetSelection: Much less responsive, highlights (paints in white areas actually).
        # Note that SetSelection will find and add lines to the self.lines structures and
        # DrawLines will do the actual painting. If SetSelection is not used, DrawLines will
        # only paint the GREY marker in response to a single left click.

        # self.SetSelection(dc)
        self.DrawRect(dc)
        # Draw any defined lines
        self.DrawLines(dc)
        # Signal that the control has been redrawn
        self.reInitBuffer = False

    def DrawRect(self, dc):
        """ Draw a rectangle surrounding the current selection. """
        if self.transanaMode:
            dc.BeginDrawing()
            dc.SetBrush(wx.Brush("GREY", wx.BDIAGONAL_HATCH))
            # Get start and end X coords from startTime and endTime
            startX = self.canvassize[0]*self.parent.PctPosFromTimeCode(self.startTime)
            endX = self.canvassize[0]*self.parent.PctPosFromTimeCode(self.endTime)
            # If startTime and endTime are the same, then startX = endX so we
            # end up drawing a zero width rectangle which works with wxPython
            dc.DrawRectangle(int(startX), 0, int(endX - startX), int(self.canvassize[1]))
            # Remember that erasing of this rectangle will be handled by InitBuffer
            dc.EndDrawing()
        
    def DrawLines(self, dc):
        """ Redraw all lines that have been recorded """
        # Let the Device Context know that we are beginning to draw
        dc.BeginDrawing()

        # For each line, determine the color, line thickness, and line list
        for colour, thickness, line in self.lines:
            # Create a Pen
            pen = wx.Pen(wx.NamedColour(colour), thickness, self.linepattern)
            # Set the Pen for the Device Context
            dc.SetPen(pen)
            # Draw the lines in the line list
            # dc.DrawLine(**dict(line)) #TODO: This would work if points were (x,y)
            for coords in line:
                # apply(dc.DrawLine, coords)
                dc.DrawLine(*coords)

        # For each text item, determine the string, position, color, size, family, and alignment
        for text, x, y, colour, size, family, alignment in self.text:
            # Create a Font
            font = wx.Font(size, family, self.fontstyle, self.fontweight)
            # Set the Font for the Device Context
            dc.SetFont(font)
            # Set the Text Color
            dc.SetTextForeground(wx.NamedColour(colour))
            # Determine the size the string will be when drawn
            (w, h) = dc.GetTextExtent(text)
            # Alter the position values based on alignment
            if alignment == 'CENTER':
                x = x - w / 2
            elif alignment == 'RIGHT':
                x = x - w + 1
            # Place the text on the Device Context
            dc.DrawText(text, int(x), int(y))
        # Let the Device Context know we are done drawing
        dc.EndDrawing()

    def SetSelection(self, dc):
        """ Add lines to the lines[] structure based on startTime, endTime, canvassize """
        # Add lines to create a new selection only if
        #   resetSelection is True which occurs after a resize or a new selection
        if self.transanaMode and self.reSetSelection:
            startX = int(self.canvassize[0]*self.parent.PctPosFromTimeCode(self.startTime))
            endX = int(self.canvassize[0]*self.parent.PctPosFromTimeCode(self.endTime))
            oldColour = self.colour
            self.colour = "LIGHT GREY"
            
            for x in range(min(startX, endX), max(startX, endX)):
                # Initialize variables to track where we need to draw
                top = 0
                bottom = 0
                # run through a single column in the graphic.  Find the top and bottom of the red bar,
                # and then draw lines above and below those points.  That will alter the background for
                # the chosen X position.
                for y in range(self.canvassize[1]):
                    # The first red pixel will be the top.  Then stop looking there.
                    if (top == 0) and (dc.GetPixel(int(x), int(y)) == wx.RED):
                        top = y
                    # The first non-red pixel (except the black center line) will be the bottom.
                    # Stop looking there, and stop looping because there's nothing else to look for.
                    if (top != 0) and not (dc.GetPixel(int(x), int(y)) in [wx.BLACK, wx.RED]):
                        bottom = y
                        break
                    # Add the lines to the abstract data structure so they will be included when the window is redrawn.
                self.AddLines([(int(x), 0, int(x), int(top)), (int(x), int(bottom), int(x), int(self.canvassize[1]))])
            # Draw black rectangle around the selection
            self.colour = "BLACK"
            self.AddLines([(int(startX),0,int(endX),0),(int(startX),int(self.canvassize[1]),int(endX),int(self.canvassize[1]))])
            self.AddLines([(int(startX),int(self.canvassize[1]-1),int(endX),int(self.canvassize[1]-1))]) # ,(startX,1,endX,1)
            self.AddLines([(int(startX),0,int(startX),int(self.canvassize[1])), (int(endX),0,int(endX),int(self.canvassize[1]))])
            self.colour = oldColour
            self.reSetSelection = False

    # if drawEnabled is true, the following events will cause lines to be drawn
    def OnLeftDown(self, event):
        self.SetFocus()
        self.drawing = True
        self.curLine = []
        self.x = event.GetX() + (self.GetViewStart()[0] * self.GetScrollPixelsPerUnit()[0])
        self.y = event.GetY() + (self.GetViewStart()[1] * self.GetScrollPixelsPerUnit()[1])
        self.CaptureMouse()

    def OnLeftUp(self, event):
        if self.HasCapture():
            self.drawing = False
            self.lines.append((self.colour, self.thickness, self.curLine))
            self.curLine = []
            self.ReleaseMouse()

    def OnMotion(self, event):
        if self.drawing and event.Dragging() and event.LeftIsDown():

            # Create a REAL DC for the Buffered DC to "blit" to
            cdc = wx.ClientDC(self)
            self.PrepareDC(cdc)
            dc = wx.BufferedDC(cdc, self.bmpBuffer)
            
            dc.BeginDrawing()
            dc.SetPen(self.pen)

            pos = (int(event.GetX() + (self.GetViewStart()[0] * self.GetScrollPixelsPerUnit()[0])),
                   int(event.GetY() + (self.GetViewStart()[1] * self.GetScrollPixelsPerUnit()[1])))

            coords = (int(self.x), int(self.y)) + pos
            self.curLine.append(coords)
            dc.DrawLine(int(self.x), int(self.y), int(pos[0]), int(pos[1]))
            self.x, self.y = pos
            dc.EndDrawing()

    # Transana requires some specific Mouse behaviors of this control, which are enabled only if
    # drawEnabled is false and transanaMode is true
    def TransanaOnLeftDown(self, event):
        """ Left Mouse Button pressed, transanaMode == true """
        self.lines = []              # Clear any existing Selection and Cursor
        self.cursorPosition = None   # That wiped out the cursor too, which is okay, but let's remember that.
        self.SetFocus()
        self.drawing = True
        self.x = event.GetX() + (self.GetViewStart()[0] * self.GetScrollPixelsPerUnit()[0])
        self.y = event.GetY() + (self.GetViewStart()[1] * self.GetScrollPixelsPerUnit()[1])
        self.CaptureMouse()
        # Return the position and event to the Parent control
        self.parent.OnLeftDown(self.x, self.y, float(self.x)/self.canvassize[0], float(self.y)/self.canvassize[1])
        self.lastX = self.x
        # Track the starting of selection and store it as a timecode
        self.startX = self.x
        self.startTime = self.parent.TimeCodeFromPctPos(float(self.startX)/self.canvassize[0])
        self.isDragging = True

    def TransanaOnLeftUp(self, event):
        """ Left Mouse Button released, transanaMode == true """
        if self.HasCapture():
            self.drawing = False
            self.x = event.GetX() + (self.GetViewStart()[0] * self.GetScrollPixelsPerUnit()[0])
            self.y = event.GetY() + (self.GetViewStart()[1] * self.GetScrollPixelsPerUnit()[1])
            self.ReleaseMouse()
            # If the release occurs off the canvas, reset the position to the canvas edge
            self.x = min(self.x, self.canvassize[0])
            self.x = max(self.x, 0)
            self.y = min(self.y, self.canvassize[1])
            self.y = max(self.y, 0)
            # Return the position and event to the Parent control
            self.parent.OnLeftUp(self.x, self.y, float(self.x)/self.canvassize[0], float(self.y)/self.canvassize[1])
            # Draw a grey marker at x if left click has been made
            if self.x == self.lastX:
                self.SetStartMarker(self.x)
            # We need to track the  position where we started this drag.  (see TransanaOnMotion below)
            self.lastX = None
            # Track the ending of a selection and store it as a timecode
            self.endX = self.x
            self.endTime = self.parent.TimeCodeFromPctPos(float(self.endX)/self.canvassize[0])
        if self.isDragging:
            self.reSetSelection = True
        self.isDragging = False
    
    def SetStartMarker(self, x):
        """ Add a grey line in lines[] at x """
        oldColour = self.colour
        self.colour = "GREY"
        self.AddLines([(int(x), 0, int(x), int(self.canvassize[1]))])
        self.colour = oldColour

    def TransanaOnMotion(self, event):
        self.x = event.GetX() + (self.GetViewStart()[0] * self.GetScrollPixelsPerUnit()[0])
        self.y = event.GetY() + (self.GetViewStart()[1] * self.GetScrollPixelsPerUnit()[1])
        self.parent.OnMouseOver(self.x, self.y, float(self.x)/self.canvassize[0], float(self.y)/self.canvassize[1])

        # When dragging in Transana Mode, we are making a selection in the Waveform Diagram.  
        if self.drawing and event.Dragging() and event.LeftIsDown():
            # Create a REAL DC for the Buffered DC to "blit" to
            cdc = wx.ClientDC(self)
            self.PrepareDC(cdc)
            dc = wx.BufferedDC(cdc, self.bmpBuffer)

            #Start drawing
            dc.BeginDrawing()
            
            # Unpaint box drawn during the previous TransanaOnMotion event
            #   Unpaint previously drawn top and bottom horizontal lines
            dc.SetPen(wx.Pen("WHITE", 2))
            dc.DrawLine(int(self.startX), 0, int(self.lastX), 0)
            dc.DrawLine(int(self.startX), int(self.canvassize[1]), int(self.lastX), int(self.canvassize[1]))
            #   Unpaint previously drawn vertical tracking line
            #   pixelList is [(colour, y)...], saved over from previous event
            for segment in self.pixelList:
                dc.SetPen(wx.Pen(segment[0],1))
                dc.DrawLine(int(self.lastX), int(segment[1]), int(self.lastX), int(self.canvassize[1]))
            
            # Save a new pixelList to be used in next event
            self.pixelList = []
            prevColour = wx.GREEN # Initialize to a color which will never appear
            for y in range(self.canvassize[1]):
                colour = dc.GetPixel(int(self.x), int(y))
                if colour != prevColour: # If color has changed, save color and position of change
                    self.pixelList.append((colour, y)) 
                    prevColour = colour # Update prevColoyr
            
            # Draw black rectangle
            #   Draw initial vertical line
            dc.SetPen(wx.Pen("BLACK", 1))
            dc.DrawLine(int(self.startX), 0, int(self.startX), int(self.canvassize[1]))
            #   Draw top and bottom horizontal lines
            dc.SetPen(wx.Pen("BLACK", 2))
            dc.DrawLine(int(self.startX), 0, int(self.x), 0)
            dc.DrawLine(int(self.startX), int(self.canvassize[1]), int(self.x), int(self.canvassize[1]))            
            #   Draw vertical tracking line
            dc.SetPen(wx.Pen("BLACK",1))
            dc.DrawLine(int(self.x), 0, int(self.x), int(self.canvassize[1]))
            
            # Remember the X position we last drew to.
            self.lastX = self.x

            # Stop drawing
            dc.EndDrawing()
        
    def TransanaOnRightUp(self, event):
        """ Right Mouse Button Released, transanaMode == true """
        self.x = event.GetX() + (self.GetViewStart()[0] * self.GetScrollPixelsPerUnit()[0])
        self.y = event.GetY() + (self.GetViewStart()[1] * self.GetScrollPixelsPerUnit()[1])
        # Return the position and event to the Parent control
        self.parent.OnRightUp(self.x, self.y)

    def OnSize(self, event):
        """" Resize event for the GraphicsControlClass Widget """
        # Clear the lines[] structure
        self.ClearTransanaSelection()
        if self.transanaMode:
            # Find x position and add grey marker to lines[]
            x = self.canvassize[0]*self.parent.PctPosFromTimeCode(self.startTime)
            self.SetStartMarker(x)
        # Signal that the control needs to be redrawn in idle time. InitBuffer will also 
        # recreate a new selection based on timecodes
        self.reInitBuffer = True

    def OnIdle(self, event):
        """ Use Idle Time to redraw the Control """
        # Check the flag to see if the control needs to be redrawn
        # We repaint only when not dragging, as during that times
        # other methods handle drawing for responsiveness
        if not(self.isDragging) and self.reInitBuffer:
            # Draw the image to the Control
            self.InitBuffer()
            # Refresh the image
            self.Refresh(False)

    def OnPaint(self, event):
        """ Repaint Event """
        # Simply push the buffered DC to the control's CD
        dc = wx.BufferedPaintDC(self, self.bmpBuffer)

    def GetMaxWidth(self, start=0):
        """ returns the width of the widest label in the text labels """
        max = 0
        tempbuffer = wx.EmptyBitmap(self.canvassize[0], self.canvassize[1])
        dc = wx.BufferedDC(None, tempbuffer)
        dc.Clear()
        for text, x, y, colour, size, family, alignment in self.text[start:]:
            font = wx.Font(size, family, self.fontstyle, self.fontweight)
            dc.SetFont(font)
            (w, h) = dc.GetTextExtent(text)
            if w > max:
                max = w
        return max

    def LoadFile(self, filename=None):
        if filename == None:
            # dlg = wx.FileDialog(self, "Load File", wildcard="BMP Files|*.bmp", style=wx.OPEN|wx.CHANGE_DIR)
            dlg = wx.FileDialog(self, "Load File", wildcard="PNG Files|*.png", style=wx.OPEN|wx.CHANGE_DIR)
            if dlg.ShowModal() == wx.ID_OK:
                filename = dlg.GetPath()
            dlg.Destroy()

        if filename != None:
            # Remember the graphic filename
            self.backgroundGraphicName = filename
            # Add Image Handler that allows BMP
            # wx.Image_AddHandler(wx.BMPHandler())

            # The Graphic Control must have a wxBitmap image, which is not resizable.  However, we want to resize the loaded bitmap to the
            # size of the Graphic Control.  To accomplish this, we load the image into a resizable wxImage, then convert that to a wxBitmap.
        
            # Create a wxImage
            self.backgroundImage = wx.EmptyImage(self.canvassize[0], self.canvassize[1])
            # Load the Bitmap into the temporary Image
            # self.backgroundImage.LoadFile(filename, wx.BITMAP_TYPE_BMP)
            self.backgroundImage.LoadFile(filename, wx.BITMAP_TYPE_PNG)
            
            # Resize the Bitmap to the size of the Graphic Control
            self.backgroundImage.Rescale(self.canvassize[0], self.canvassize[1])
            # Convert the wxImage to a wxBitmap
            tempBitmap = wx.BitmapFromImage(self.backgroundImage)
            # Set the active image (self.bmpBuffer) to the Bitmap
            self.bmpBuffer = tempBitmap
        
            self.Refresh(False)  # Required to get the image to show up!
        

    # Define the Method that Saves the image as a Graphic
    def SaveAs(self):
        dlg = wx.FileDialog(self, _("Save File"), wildcard=_("JPEG Files|*.jpg"), style=wx.SAVE|wx.OVERWRITE_PROMPT|wx.CHANGE_DIR)
        if dlg.ShowModal() == wx.ID_OK:
            # Add Image Handler that allows JPEG
            wx.Image_AddHandler(wx.JPEGHandler())
            # File Extension is not automatically appended on Mac.  Let's ensure it's there.
            filename = dlg.GetPath()
            (fn, ext) = os.path.splitext(filename)
            if ext == '':
                filename = filename + '.jpg'
            # Save the existing Bitmap in the graphic control
            self.bmpBuffer.SaveFile(filename, wx.BITMAP_TYPE_JPEG)
        dlg.Destroy()

    def SetDim(self, x, y, width, height):
        """ This method resizes the Graphic Area by resizing the canvas  """
        self.canvassize = (width, height)
        # The control should be 6 pixels larger than the canvas to allow for the border
        self.SetDimensions(x, y, width+6, height+6)
        # Resize the Background Image to the size of the Graphic Control
        if self.backgroundImage != None:
            # Rescale does not work properly.  The image does not "round-trip" well when enlarged and reduced by a large amount.
            # self.backgroundImage.Rescale(self.canvassize[0], self.canvassize[1])
            # Therefore, let's go with reloading the image entirely. 
            # To do this, set the Background Image to None, and it will be loaded when the buffer is redrawn, via OnIdle.
            self.backgroundImage = None
        self.reInitBuffer = True
        self.reSetSelection = True

    def DrawCursor(self, currentPosition):
        (width, height) = self.GetSizeTuple()
        y = int(currentPosition * self.canvassize[0] + 1)
        # If there is an existing cursor, eliminate it
        if self.cursorPosition != None:
            del(self.lines[self.cursorPosition])
        # Draw the new cursor
        self.AddLines([(int(y), 0, int(y), int(height-6))])
        # Remember the cursor position in the "lines" structure so that it can be removed
        self.cursorPosition = len(self.lines) - 1
 


# If this class is run independently (for testing), create an
# Application Frame and put in a GraphicsControl.
if __name__ == '__main__':

    class MyFrame(wx.Frame):
        def __init__(self, parent, ID, title, pos=wx.Point(100, 100), size=(800, 600)):
            wx.Frame.__init__(self, parent, ID, title, pos, size)
            self.SetBackgroundColour(wx.WHITE)

    ID_CLEAR        = 1001
    ID_DRAWSQUARE   = 1002
    ID_ADDTEXT      = 1003
    ID_DESTROY      = 1004

    class MyApp(wx.App):

        def OnInit(self):
            # Create the Main Application Frame
            frame = MyFrame(None, -1, "This is a Containing Frame")

            # Create a blank panel.  The GraphicsControl will take up the whole window if there is nothing else there!
            self.panel = wx.Panel(frame, -1, wx.Point(10, 50), (100, 300))
            wx.Button(self.panel, ID_CLEAR, "Clear", wx.Point(10,10))
            wx.EVT_BUTTON(self, ID_CLEAR, self.ClearGC)
            wx.Button(self.panel, ID_DRAWSQUARE, "Draw Shapes", wx.Point(10,40))
            wx.EVT_BUTTON(self, ID_DRAWSQUARE, self.DrawSquare)
            wx.Button(self.panel, ID_ADDTEXT, "Add Text", wx.Point(10,70))
            wx.EVT_BUTTON(self, ID_ADDTEXT, self.AddText)
            wx.Button(self.panel, ID_DESTROY, "Destroy", wx.Point(10,100))
            wx.EVT_BUTTON(self, ID_DESTROY, self.Goodbye)

            # Put a GraphicsControl on the Main Application Frame
            # pos and size appear to have no effect on the resultant window if it is the only control!
            self.GC = GraphicsControl(frame, -1, pos=wx.Point(130, 20), size=(640, 540), canvassize=(640,540), drawEnabled=True)
            frame.Show(True)
            self.SetTopWindow(frame)

            return True

        def ClearGC(self, event):
            self.GC.Clear()

        def DrawSquare(self, event):
            self.GC.SetColour("RED")
            self.GC.SetThickness(3)
            self.GC.AddLines([(300, 300, 300, 700), (300, 700, 700, 700), (700, 700, 700, 300), (700, 300, 300, 300)])
            self.GC.SetColour("BLUE")
            self.GC.SetThickness(2)
            self.GC.AddLines([(500, 400, 400, 600), (400, 600, 600, 600), (600, 600, 500, 400)])

        def AddText(self, event):
            self.GC.SetFontColour("PURPLE")
            self.GC.SetFontSize(18)
            self.GC.AddText('Hello, world!', 30, 30)
            self.GC.SetFontColour("GREEN")
            self.GC.SetFontSize(12)
            self.GC.AddText('Hello, world!', 730, 730)

        def Goodbye(self, event):
            self.GC.Destroy()

    app = MyApp(0)
    app.MainLoop()
