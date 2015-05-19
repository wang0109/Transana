# Copyright (C) 2003 - 2007 The Board of Regents of the University of Wisconsin System 
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of version 2 of the GNU General Public License as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#

"""This module implements the TranscriptEditor class as part of the Editors
component.  """

__author__ = 'Nathaniel Case, David Woods <dwoods@wcer.wisc.edu>, Jonathan Beavers <jonathan.beavers@gmail.com>'

DEBUG = False
if DEBUG:
    print "TranscriptEditor DEBUG is ON."
SHOWHIDDEN = False
if SHOWHIDDEN:
    print "TranscriptEditor SHOWHIDDEN is ON."

import wx
from RichTextEditCtrl import RichTextEditCtrl
import TransanaFontDialog
import Transcript
import DragAndDropObjects
import Dialogs
import Episode, Clip
import TransanaConstants
import TransanaGlobal
import Misc
import re
import cPickle
import pickle
import time
import types

# This character is interpreted as a timecode marker in transcripts
TIMECODE_CHAR = TransanaConstants.TIMECODE_CHAR

# Nate's original REGEXP, "\xA4<[^<]*>", was not working correctly.
# Given the string "this \xA4<1234> is a string > with many characters",
# Nate's REGEXP returned "\xA4<1234> is a string >"
# rather than the desired "\xA4<1234>".
# My REGEXP "\xA4<[\d]*>" appears to do that.
TIMECODE_REGEXP = "%s<[\d]*>" % TIMECODE_CHAR            # "\xA4<[^<]*>"

class TranscriptEditor(RichTextEditCtrl):
    """This class is a word processor for transcribing and editing.  It
    provides only the actual text editing control, without any external GUI
    components to aid editing (such as a toolbar)."""

    def __init__(self, parent, id=-1, stylechange_cb=None):
        """Initialize an TranscriptEditor object."""
        RichTextEditCtrl.__init__(self, parent)

        self.parent = parent
        self.StyleChanged = stylechange_cb

        # There are times related to right-click play control when we need to remember the cursor position.
        # Create a variable to store that information, initialized to 0
        self.cursorPosition = 0

        # These ASCII characters are treated as codes and hidden
        # self.HIDDEN_CHARS = [TIMECODE_CHAR,]      NOT USED??
        self.HIDDEN_REGEXPS = [re.compile(TIMECODE_REGEXP),]
        self.codes_vis = 0
        self.TranscriptObj = None
        self.timecodes = []
        self.current_timecode = -1
        self.set_read_only(1)
        
        # Remove Drag-and-Drop reference on the mac due to the Quicktime Drag-Drop bug
        if not '__WXMAC__' in wx.PlatformInfo:
            dt = TranscriptEditorDropTarget(self)
            self.SetDropTarget(dt)

            self.SetDragEvent(id, self.OnStartDrag)
            
        # We need to trap both the EVT_KEY_DOWN and the EVT_CHAR event.
        # EVT_KEY_DOWN processes NON-ASCII keys, such as cursor keys and Ctrl-key combinations.
        # All characters are reported as upper-case.
        wx.EVT_KEY_DOWN(self, self.OnKeyPress)
        # EVT_CHAR is used to detect normal typing.  Characters are case sensitive here.
        wx.EVT_CHAR(self, self.OnChar)
        # EVT_LEFT_UP is used to detect the left click positioning in the Transcript.
        wx.EVT_LEFT_UP(self, self.OnLeftUp)
        # This causes the Transana Transcript Window to override the default
        # RichTextEditCtrl right-click menu.  Transana needs the right-click
        # for play control rather than an editing menu.
        wx.EVT_RIGHT_UP(self, self.OnRightClick)

    # Public methods
    def load_transcript(self, transcript, dataType='rtf'):
        """ Load the given transcript object into the editor. Pass a RTF filename as a
        string or pass a Transcript object. The dataType parameter defaults to rtf, but if 
        you are loading a pickled transcript, be sure to use 'pickle'. Another thing that
	this method does is that if an RTF transcript has been loaded, it will automatically
	save the transcript using the pickle format.     
        """
	if DEBUG:
	    print "TranscriptEditor.load_transcript()"

	# benchmarking
	startTime = time.clock()

        # prepare the buffer for the incoming data.
        self.ClearDoc()
        self.set_read_only(0)

        # The Transcript should already have been saved or cleared by this point.
        # This code should never get activated. It's just here for safety's sake.
        if self.TranscriptObj:
            self.parent.ControlObject.SaveTranscript(1)
            # If you have the Transcript locked, then load something else without leaving
            # Edit Mode, you need to unlock the record!
            if self.TranscriptObj.isLocked:
                self.TranscriptObj.unlock_record()

        # Disable widget while loading transcript
        self.Enable(False)

        # dataType should only ever be "pickle", "text" or "rtf"
        if dataType == 'pickle':
            # if transcript.text is empty, we've created a new transcript.
            # thus, there is no data to unpickle, and so unless you really like
            # EOFError exceptions you should not attempt to unpickle.
            if transcript.text != '':
                try:
                    # extract pertinent info from the data.
                    (bufferContents, specs, attrs) = pickle.loads(transcript.text)

                    self.StyleClearAll()
                    self.style_specs = []
                    self.style_attrs = []
                    self.num_styles = 0
                    
                    # Make sure to reset the styles, and do it before the call to 
                    # AddStyledText(), as if the text references some unknown style,
                    # bad things will probably happen.
                    
                    for x in specs:
                        self.GetStyleAccessor(x)

                    self.STYLE_HIDDEN = self.GetStyleAccessor("hidden")
                    self.STYLE_TIMECODE = self.GetStyleAccessor("timecode")
                    self.StyleSetVisible(self.STYLE_HIDDEN, False)
                    self.StyleSetSpec(self.STYLE_TIMECODE, "size:%s,face:%s,fore:#FF0000,back:#ffffff" % (str(TransanaGlobal.configData.defaultFontSize), TransanaGlobal.configData.defaultFontFace))

                    # So the data has been pickled, and we are running on OSX. 
                    # Since the pickled data is *always* saved with the Windows 
                    # timecode characters, we must now search for and replace
                    # all Windows special characters with their OSX equivalents.
                    if 'wxMac' in wx.PlatformInfo:
# With wxPython 2.8.0.1, wxSTC's Unicode handling is improved. Thus, these values have to change.
#			sequenceList = {
#			    '\xc2\xa4':'\xc2\xa7', 
#			    '\xc2\xad':'\xe2\x89\xa0', 
#			    '\xc2\xaf':'\xc3\x98' 
#			}
			sequenceList = {
			    '\xc2\xad':'\xe2\x86\x91', 
			    '\xc2\xaf':'\xe2\x86\x93' 
			}
			todo = {}
			inSeq = False
			gatherStyle = False
			sequence = ''
			# All this little algorithm represents is a state machine
			# that collects the style data for a given symbol. It is
			# likely faster than simply using a regular expression,
			# so stop rolling your eyes!
			for char in bufferContents:
			    if char == '\xc2':
				inSeq = True
				gatherStyle = True
				sequence = char
			    elif inSeq and gatherStyle:
				styleChar = char
				gatherStyle = False
			    elif inSeq and not gatherStyle and char != styleChar:
				sequence = sequence + char
		
			    # now we've possibly gathered a valid sequence, so we'll
			    # need to check it against the list of known sequences.
			    if inSeq:
				try:
				    # it is rather important that this statement is the
				    # first that we attempt. If it fails, it will generate
				    # a KeyError exception and we'll fly off to the exception handling.
				    # If it succeeds, we need to turn off our simple-minded state
				    # machine. Oh, and it would be awesome to know what we should use
				    # to replace sequence.
				    replacement = sequenceList[sequence]
				    inSeq = False
				    # so now i want to recreate sequence and replacement
				    # using the style characters, and then add them to a dictionary
				    # and just do a few substitutions on bufferContents
				    replacement = styleChar.join([x for x in replacement]) + styleChar
				    sequence = styleChar.join([x for x in sequence]) + styleChar
				    todo[sequence] = replacement
				except KeyError:
				    pass
			# now that we have all the known variations of symbols and styles, go ahead
			# and replace them with the proper information.
			for k, v in todo.iteritems():
                            # The problem with Jonathan's logic above is that the style character PRECEEDS rather than 
                            # follows the text character, so the final style character may differ from the one recorded above.
                            # To fix that, let's strip the final style character from both strings.  DKW
			    bufferContents = bufferContents.replace(k[:-1], v[:-1])

		    # With platform specific issues taken care of, we can now simply
                    # reload the pickled data into the buffer, and everything is just
                    # peachy
		    self.AddStyledText(bufferContents)

                except ValueError:
                    if DEBUG:
                        print "TranscriptEditor.load_transcript() failed to load pickled data"
                        import traceback
                        traceback.print_exc(file=sys.stdout)
                    import sys
                    # Display the Exception Message, allow "continue" flag to remain true
                    errordlg = Dialogs.ErrorDialog(None, "%s : %s" % (sys.exc_info()[0],sys.exc_info()[1]))
                    errordlg.ShowModal()
                    errordlg.Destroy()
                    
	    
	    # if you don't take the following steps, TranscriptObj will not behave as expected for
	    # several methods that execute once a transcript has finished loading.
            self.TranscriptObj = transcript
            self.TranscriptObj.has_changed = 0

            if DEBUG:
                print "TranscriptEditor.load_transcript():  Styles..."
                for style in range(len(self.style_specs)):
                    print style, self.style_specs[style]

        # If we are dealing with a Plain Text document ...
        elif dataType == 'text':

#            for x in range(18):
#                print "%2d   %1s %3d %2x" % (x, transcript.text[x], ord(transcript.text[x]), ord(transcript.text[x]))
                
            # Get the text we need to import
            text = transcript.text[4:]
            
            # Let's scan the file for characters we need to handle.  Start at the beginning of the file.
            # NOTE:  This is a very preliminary implementation.  It only deals with English, and only with ASCII or UTF-8
            #        encoding of time codes (chr(164) or chr(194) + chr(164)).
            pos = 0
            # Keep working until we get to the end of the file.
            while pos < len(text):
                # if we have a non-English character, one the ASCII encoding can't handle ...
                if (ord(text[pos]) > 127):
                    # If we have a Time Code character (chr(164)) ...
                    if (ord(text[pos]) == 164):
                        # ... we can let this pass.  We know how to handle this.
                        pass
                    # In UTF-8 Encoding, the time code is a PAIR, chr(194) + chr(164).  If we see this ...
                    elif (ord(text[pos]) == 194) and (ord(text[pos + 1]) == 164):
                        # ... then let's drop the chr(194) part of things.  At the moment, we're just handling ASCII.
                        text = text[:pos] + text[pos + 1:]
                    # If it's any other non-ASCII character (> 127) ...
                    else:
                        # ... replace it with a question mark for the moment
                        text = text[:pos] + '?' + text[pos + 1:]
                # Increment the position indicator to move on to the next character.
                pos += 1

            # As long as there is text to process ...
            while len(text) > 0:
                # Look for Time Codes
                if text.find(chr(164)) > -1:
                    # Take the chunk of text before the next time code and isolate it
                    chunk = text[:text.find(chr(164))]
                    # remove that chuck of text from the rest of the text
                    # skip the time code character and the opening bracket ("<")
                    text = text[text.find(chr(164)) + 2:]
                    # Grab the text up to the closing bracket (">"), which will be the time code data.
                    timeval = text[:text.find('>')]
                    # Remove the time code data and the closing bracket from the remaining text
                    text = text[text.find('>')+1:]
                    # Add the text chunk to the Transcript
                    self.AddText(chunk)
                    # # Add the time code (with data) to the Transcript 
                    self.insert_timecode(int(timeval))
                # if there are no more time codes in the text ...
                else:
                    # ... add the rest of the text to the Transcript ...
                    self.AddText(text)
                    # ... and clear the text variable to signal that we're done.
                    text = ''

            # Set the Transcript to the Editor's TranscriptObj
            self.TranscriptObj = transcript
            # Indicate the Transcript hasn't been edited yet.
            self.TranscriptObj.has_changed = 0
	    # If we have an Episode Transcript in TXT Form, save it in FastSave format upon loading
	    # to convert it.  
            self.TranscriptObj.lock_record()
            self.save_transcript()
            self.TranscriptObj.unlock_record()
        else:
            # looks like this is an rtf file.
            # set up the progress bar
            self.ProgressDlg = wx.ProgressDialog(_("Loading Transcript"), \
                                                _("Reading document stream"), \
                                                maximum=100, \
                                                style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE)
            # was the given transcript object simply a filename?
            if isinstance(transcript, types.StringTypes):
                self.LoadDocument(transcript)
                self.TranscriptObj = None
            else:
                # Assume a Transcript object was passed 
                self.LoadRTFData(transcript.text)
                self.TranscriptObj = transcript
                self.TranscriptObj.has_changed = 0
        
            # Get rid of the progress bar.
	    self.ProgressDlg.Destroy()

	    # If we have an Episode Transcript in RTF Form, save it in FastSave format upon loading
	    # to convert it.  We don't convert Clip Transcripts, as that would break the Collection Summary Report.
	    if self.TranscriptObj.clip_num == 0:
                # this was added in to automatically convert an RTF document into
                # the fastsave format.
                self.TranscriptObj.lock_record()
                self.save_transcript()
                self.TranscriptObj.unlock_record()

        # Scan transcript for timecodes
        self.load_timecodes()

        # Re-enable widget
        self.Enable(True)
        self.set_read_only(1)
        
        self.GotoPos(0)

	# Clear the Undo Buffer, so you can't Undo past this point!  (BUG FIX!!)
        self.EmptyUndoBuffer()
      
	# Display Time Codes by default
	# show_codes() seems to triple the time it takes to complete
	# this method... (from ~0.5s to ~1.8s)
        self.show_codes()

        self.parent.toolbar.ToggleTool(self.parent.toolbar.CMD_SHOWHIDE_ID, True)
	# Set save point
        self.SetSavePoint()
	stopTime = time.clock()

    def load_timecodes(self):
        """Scan the document for timecodes and add to internal list."""
        txt = self.GetText()
        findstr = TIMECODE_CHAR + "<"
        i = txt.find(findstr, 0)
        while i >= 0:
            endi = txt.find(">", i)
            timestr = txt[i+2:endi]
            try:
                self.timecodes.append(int(timestr))
            except:
                pass
            i = txt.find(findstr, i+1)

    def save_transcript(self):
        """Save the transcript to the database."""
        # Let's try to remember the cursor position
        self.cursorPosition = (self.GetCurrentPos(), self.GetSelection())
        # We can't save with Time Codes showing!  Remember the initial status, and hide them
        # if they are showing.
        initCodesVis = self.codes_vis
        if initCodesVis:
            self.hide_codes()
        
        if self.TranscriptObj:
            self.TranscriptObj.has_changed = self.modified()
	    # If we have an Episode Transcript, save it in FastSave format.  
	    if self.TranscriptObj.clip_num == 0:
                # Grab the pickled data for the fast save.
                self.TranscriptObj.text = self.GetPickledBuffer()
            else:
                # We don't convert Clip Transcripts, as that would break the Collection Summary Report.  We
                # save Clip Transcripts in RTF format.
                self.TranscriptObj.text = self.GetRTFBuffer()
            # Now just write it to the db.
            self.TranscriptObj.db_save()
            # Tell wxSTC that we saved it so it can keep track of
            # modifications.
            self.SetSavePoint()

        # If time codes were showing, show them again.
        if initCodesVis:
            self.show_codes()
        
        # Let's try restoring the Cursor Position when all is said and done.
        self.RestoreCursor()

    def get_transcript(self):
        """Get in memory transcript object."""
        # Do we really want this?

    def get_transcript_doc_data(self):
        return self.GetRTFBuffer()

    def export_transcript(self, rtf_fname):
        """Export the transcript to an RTF file."""
        self.SaveRTFDocument(rtf_fname)
        
    def set_default_font(self, font):
        """Change the default font."""

    def set_font(self, font_face, font_size, font_fg=0x000000, font_bg=0xffffff):
        """Change the current font or the font for the selected text."""
        self.SetFont(font_face, font_size, font_fg, font_bg)
    
    def get_font(self):
        """Get the current font."""
        return self.GetFont()
    
    def set_bold(self, enable=-1):
        """Set bold state for current font or for the selected text.
        If enable is not specified as 0 or 1, then it will toggle the
        current bold state."""
        if self.get_read_only():
            return
        if enable == -1:
            enable = not self.GetBold()
        self.SetBold(enable)
    
    def get_bold(self):
        return self.GetBold()
    
    def set_italic(self, enable=-1):
        """Set italic state for current font or for the selected text."""
        if self.get_read_only():
            return
        if enable == -1:
            enable = not self.GetItalic()
        self.SetItalic(enable)

    def get_italic(self):
        return self.GetItalic()

    def set_underline(self, enable=-1):
        """Set underline state for current font or for the selected text."""
        if self.get_read_only():
            return
        if enable == -1:
            enable = not self.GetUnderline()
        self.SetUnderline(enable)

    def get_underline(self):
        return self.GetUnderline()
        
    def cut_selected_text(self):
        """Delete selected text and place in clipboard."""
    def copy_seleted_text(self):
        """Copy selected text to clipboard."""
    def paste_text(self):
        """Paste text from clipboard."""
    def select_all(self):
        """Select all document text."""
        
    def show_codes(self):
        """Make encoded text in document visible."""
        self.changeTimeCodeHiddenStatus(False)
        self.codes_vis = 1
        
    def hide_codes(self):
        """Make encoded text in document visible."""
        self.changeTimeCodeHiddenStatus(True)
        self.codes_vis = 0

    def codes_visible(self):
        """Return 1 if encoded text is visible."""
        return self.codes_vis

    def changeTimeCodeHiddenStatus(self, hiddenVal):
        """ Changes the Time Code marks (but not the time codes themselves) between visible and invisble styles. """
        # We don't want the screen to move, so let's remember the current position
        topLine = self.GetFirstVisibleLine()
        
        # Note whether the document has had a style change yet.
        initStyleChange = self.stylechange
        
        # Let's try to remember the cursor position
        self.cursorPosition = (self.GetCurrentPos(), self.GetSelection())
        
        # Move the cursor to the beginning of the document
        self.GotoPos(0)

        # Let's show all the hidden text of the time codes.  This doesn't work without it!
        if not self.codes_vis:
            wereHidden = True
            self.show_all_hidden()
        else:
            wereHidden = False
        # Let's find each time code mark and update it with the new style.  
        for loop in range(0, len(self.timecodes)):
            # Find the Timecode
            self.cursor_find('%s' % TIMECODE_CHAR)
            # Note the Cursor's Current Position
            curpos = self.GetCurrentPos()
            # Adjust cursor position for unicode characters so that the time code symbols are hidden correctly
            if ('unicode' in wx.PlatformInfo) and (curpos > 0):
                curpos -= 1
            # Start Styling from the Cursor Position
            self.StartStyling(curpos, 255)
            # If the TimeCodes should be hidden ...
            if hiddenVal:
                # ... set their style to STYLE_HIDDEN
                self.SetStyling(1, self.STYLE_HIDDEN)
            # If the TimeCodes should be displayed ...
            else:
                # ... set their style to STYLE_TIMECODE
                self.SetStyling(1, self.STYLE_TIMECODE)
            # We then need to move the cursor past the current TimeCode so the next one will be
            # found by the "cursor_find" call.
            self.SetCurrentPos(curpos + 1)

        # We better hide all the hidden text for the time codes again
        if wereHidden:
            self.hide_all_hidden()
        # now reset the position of the document
        self.ScrollToLine(topLine)
        # Okay, this might not work because of changes we've made to the transcript, but let's
        # try restoring the Cursor Position when all is said and done.
        self.RestoreCursor()
        try:
            self.Update()
        except wx._core.PyAssertionError, x:
            pass
        
        # This event should NOT cause the Style Change indicator to suggest the document has been changed.
        self.stylechange = initStyleChange

    def show_all_hidden(self):
        """Make encoded text in document visible."""
        self.StyleSetVisible(self.STYLE_HIDDEN, True)
        self.codes_vis = 1

    def hide_all_hidden(self):
        """Make encoded text in document visible."""
        if not SHOWHIDDEN:
            self.StyleSetVisible(self.STYLE_HIDDEN, False)
        self.codes_vis = 0

    def find_text(self, txt, direction, flags=0):
        """Find text in document."""
        # note the current text selection.  If the search fails, we'll restore this.
        curSel = self.GetSelection()
        # STC's SearchNext starts at the start of the current selection.  So if you do repeat searches, it will
        # just find the same text over and over again!
        # Here, we see if our selection equals our search text and we're looking forward, in which case we probably
        # just did a search and want to repeat it.
        if (self.GetSelectedText().upper() == txt.upper()) and (direction == 'next'):
            # Determine the current position ...
            pos = self.GetCurrentPos()
            # ... and move the cursor by one character.  Then we'll find the NEXT instance rather than the same one.
            self.GotoPos(pos + 1)
        # Mark the current position for the Search function
        self.SearchAnchor()
        # If we're searching forward ...
        if direction == 'next':
            # ... then search for the next instance (with flags if we want whole word,
            # case-sensitive, or regular expression searches.)
            newPos = self.SearchNext(flags, txt)
        # if we're searching backwards ...
        elif direction == 'back':
            # ... then search for the previous instance (with flags if we want whole word,
            # case-sensitive, or regular expression searches.)
            newPos = self.SearchPrev(flags, txt)
        # If we found something ...
        if (newPos > -1):
            # We need to determine the Document line from our search result (which is a position).  Then we need to
            # translate the document line into a visible line.  (Document lines don't take word wrap into account.)
            line = self.VisibleFromDocLine(self.LineFromPosition(newPos))
            # If the visible line is not currently shown on the screen ...
            if ( (line < self.GetFirstVisibleLine()) or (line > self.GetFirstVisibleLine() + self.LinesOnScreen()) ):
                # ... then scroll to that line so it will be shown.
                self.ScrollToLine(line)
        # If we didn't find a next/previous instance ...
        else:
            # then restore the original cursor selection.  This just looks better.
#            self.SetSelection(curSel[0], curSel[1])
            self.SetCurrentPos(curSel[0])
            self.SetAnchor(curSel[1])

    def insert_text(self, text):
        """Insert text at current cursor position."""
   
    def insert_timecode(self, time_ms=-1):
        """Insert a timecode in the current cursor position of the
        Transcript.  The parameter time_ms is optional and will default
        to the current Video Position if not used."""
        if self.get_read_only():
            # Don't do it in read-only mode
            return
        
        (prevTimeCode, nextTimeCode) = self.get_selected_time_range()
        
        if time_ms >= 0:
            timepos = time_ms
        else:
            timepos = self.parent.ControlObject.GetVideoPosition()

        # The second line here allows you to insert a timecode at 0.0 if there isn't already one there.
        if (len(self.timecodes) == 0) or (prevTimeCode < timepos) and ((timepos < nextTimeCode) or (nextTimeCode == -1)) \
           or ((timepos == 0) and (prevTimeCode == 0.0) and (self.timecodes[0] > 0)):
            if self.codes_vis:
                tempStyle = self.style
                self.style = self.STYLE_TIMECODE
                self.InsertStyledText("%s" % TIMECODE_CHAR, length=1)
                self.InsertHiddenText("<%d>" % timepos)
                self.style = tempStyle
            else:
                self.InsertHiddenText("%s<%d>" % (TIMECODE_CHAR, timepos))

            self.Refresh()
            # Update the 'timecodes' list, putting it in the right spot
            i = 0
            if len(self.timecodes) > 0:
                # the index variable (i) must be less than the number of elements in
                # self.timecodes to avoid an index error when inserting a selection timecode
                # at the end of the Transcript.
                while (i < len(self.timecodes) and (self.timecodes[i] < timepos)):
                    i = i + 1
            self.timecodes.insert(i, timepos)
        else:
            msg = _('Time Code Sequence error.\nYou are trying to insert a Time Code at %s\nbetween time codes at %s and %s.')
            if 'unicode' in wx.PlatformInfo:
                # Encode with UTF-8 rather than TransanaGlobal.encoding because this is a prompt, not DB Data.
                msg = unicode(msg, 'utf8')
            errordlg = Dialogs.ErrorDialog(self, msg % (Misc.time_in_ms_to_str(timepos), Misc.time_in_ms_to_str(prevTimeCode), Misc.time_in_ms_to_str(nextTimeCode)))
            errordlg.ShowModal()
            errordlg.Destroy()

    def insert_timed_pause(self, start_ms, end_ms):
        if self.get_read_only():
            # Don't do it in read-only mode
            return
        (prevTimeCode, nextTimeCode) = self.get_selected_time_range()
        # Issue 231 -- Selection Insert fails if it is after the last known time code.
        # If the last time code is undefined, use the media length for an Episode or the
        # Clip Stop Point for a Clip.
        if nextTimeCode == -1:
            if type(self.parent.ControlObject.currentObj) == type(Episode.Episode()):
                nextTimeCode = self.parent.ControlObject.currentObj.tape_length
            else:
                nextTimeCode = self.parent.ControlObject.currentObj.clip_stop
        
        if prevTimeCode > start_ms:
            msg = _('Time Code Sequence error.\nYou are trying to insert a Time Code at %s\nbetween time codes at %s and %s.')
            if 'unicode' in wx.PlatformInfo:
                # Encode with UTF-8 rather than TransanaGlobal.encoding because this is a prompt, not DB Data.
                msg = unicode(msg, 'utf8')
            errordlg = Dialogs.ErrorDialog(self, msg % (Misc.time_in_ms_to_str(start_ms), Misc.time_in_ms_to_str(prevTimeCode), Misc.time_in_ms_to_str(nextTimeCode)))
            errordlg.ShowModal()
            errordlg.Destroy()
        elif nextTimeCode < end_ms:
            msg = _('Time Code Sequence error.\nYou are trying to insert a Time Code at %s\nbetween time codes at %s and %s.')
            if 'unicode' in wx.PlatformInfo:
                # Encode with UTF-8 rather than TransanaGlobal.encoding because this is a prompt, not DB Data.
                msg = unicode(msg, 'utf8')
            errordlg = Dialogs.ErrorDialog(self, msg % (Misc.time_in_ms_to_str(end_ms), Misc.time_in_ms_to_str(prevTimeCode), Misc.time_in_ms_to_str(nextTimeCode)))
            errordlg.ShowModal()
            errordlg.Destroy()
        else:
            time_span_secs = (end_ms - start_ms) / 1000.0
            time_span_secs = round(time_span_secs, 1)
            self.insert_timecode(start_ms)
            timespan = "(%.1f)" % time_span_secs
            self.InsertText(self.GetCurrentPos(), timespan)
            self.GotoPos(self.GetCurrentPos() + len(timespan))
            self.insert_timecode(end_ms)


    def scroll_to_time(self, ms):
        """Scroll to the nearest timecode matching 'ms' that isn't
        greater than 'ms'.  Return TRUE if position in document is
        actually changed."""
        # Bump up the time a little bit to account for rounding errors,
        # since sometimes I've noticed the numbers that get passed here
        # are off by one.  Otherwise it gets stuck, for example, when
        # the next timecode is X and ms is X-1, and other code depends
        # on it actually updating (which happened with the CTRL-N
        # behavior to jump to the next segment)
        ms = ms + 2

        # If no timecodes exist, ignore this call
        if len(self.timecodes) == 0:
            return False
        
        # Find the timecode that's closest
        closest_time = self.timecodes[0]
        for timecode in self.timecodes:
            if (timecode <= ms) and (ms - timecode < ms - closest_time):
                closest_time = timecode
            #if abs(timecode - ms) < abs(closest_time - ms):
            #    closest_time = timecode
        
        # Check if ALL timecodes in document are higher than given time.
        # In this case, we scroll to 0
        if (closest_time > ms):
            closest_time = 0

        # Get start and end points of current selection
        (start, end) = self.GetSelection()

        # NOTE:  Removed because this was preventing the first segment of a transcript selection from being
        #        highlighted during transcript selection playback.
        
        self.current_timecode = closest_time

        # Update cursor position and select text up until the next timecode
        pos = self.GetCurrentPos()

        if DEBUG:
            print "TranscriptEditor.scroll_to_time():  Initial pos =", self.GetCurrentPos(), self.GetSelection()
            
        self.cursor_find("%s<%d>" % (TIMECODE_CHAR, closest_time))

        if DEBUG:
            print "TranscriptEditor.scroll_to_time():  after cursor_find =", self.GetCurrentPos(), self.GetSelection()
            
        self.select_find(TIMECODE_CHAR + "<")

        if DEBUG:
            print "TranscriptEditor.scroll_to_time():  after select_find =", self.GetCurrentPos(), self.GetSelection()
            
        if self.GetCurrentPos() != pos:
            return True  # return TRUE since position changed
        else:
            return False
        
    def cursor_find(self, text):
        """Move the cursor to the next occurrence of given text in the
        transcript (for word tracking)."""
        # We first try searching from the current cursor position
        # for efficiency reasons (most of the time you're jumping just
        # ahead of the current cursor position).
        pos = self.FindText(self.GetCurrentPos(), self.GetLength()-1, text)
        if pos >= 0:
            # If using Unicode, we need to move one position to the right.
            if 'unicode' in wx.PlatformInfo:
                pos += 1
            try:
                self.GotoPos(pos)
            except wx._core.PyAssertionError, x:
                pass
        else:
            # Try searching in reverse
            pos = self.FindText(self.GetCurrentPos(), 0, text)
            if pos >= 0:
                # If using Unicode, we need to move one position to the right.
                if 'unicode' in wx.PlatformInfo:
                    pos += 2
                self.GotoPos(pos)

    def select_find(self, text):
        """Select the text from the current cursor position to the next
        occurrence of given text (for word tracking)."""
        # In some cases, the text is a defined time code.  In others, it's a time indicator not in the timecode list.
        # We have to make sure it's something in the list.

        # First, not all "text" refers to time codes.  Some is actual text, including the time code symbol.
        # The try ... except structure catches this (as the text will not convert to an integer) and leaves the text unchanged.
        # If the text IS a time code, this code will locate the appropriate time code AFTER the number sent.  This is needed
        # when a selection is made in the Visualization Window which may not align with a know ending time code.
        try:
            timecodePos = 0
            while (timecodePos < len(self.timecodes)) and (int(self.timecodes[timecodePos]) < int(float(text))):
                timecodePos += 1
            if text != str(self.timecodes[timecodePos]):
                text = str(self.timecodes[timecodePos])
        except:
            pass
        
        # We need to make sure the cursor is not positioned between a time code symbol and the time code data, which unfortunately
        # can happen.
        self.CheckTimeCodesAtSelectionBoundaries()

        curpos = self.GetSelectionStart()  # self.GetCurrentPos()
        endpos = self.FindText(curpos + 1, self.GetLength()-1, text)

        # If not found, select until the end of the document
        if endpos ==  -1:
            endpos = self.GetLength()-1

        # When searching for time codes for positioning of the selection, we end up selecting
        # the time code symbol and "<" that starts the time code.  We don't want to do that.
        if 'unicode' in wx.PlatformInfo:
        
            if DEBUG:
                print "endpos-3 = %s, %s" % (endpos-3, self.GetCharAt(endpos-3))
                print "endpos-2 = %s, %s" % (endpos-2, self.GetCharAt(endpos-2))
                print "endpos-1 = %s, %s" % (endpos-1, self.GetCharAt(endpos-1))
                print "endpos = %s, %s" % (endpos, self.GetCharAt(endpos))
                print "endpos+1 = %s, %s" % (endpos+1, self.GetCharAt(endpos+1))
                print "endpos+2 = %s, %s" % (endpos+2, self.GetCharAt(endpos+2))
                print "endpos+3 = %s, %s" % (endpos+3, self.GetCharAt(endpos+3))
            
            # Becaues the time code symbols vary with platform, we need to build a list of the characters
            # in the timecode character manually
            tcList = []
            tcList.append(ord('<'))
            for ch in TIMECODE_CHAR:
                tcList.append(ord(ch))
            # The first part of the time code characters doesn't get included under Unicode.  Add it here.
            if 'unicode' in wx.PlatformInfo:
                tcList.append(194)

            if DEBUG:
                print "TranscriptEditor.select_find():  TimeCode List:", tcList
                
            # If any of these characters is just to the left of where the end position is, move the end position to the left by 1 position
            while (endpos > 1) and (self.GetCharAt(endpos-1) in tcList):
                endpos -= 1

                if DEBUG:
                    print "endpos -= 1"
                    
        else:
            while (endpos > 1) and (self.GetCharAt(endpos-1) in [ord('<'), ord(TIMECODE_CHAR)]):
                endpos -= 1

        if DEBUG:
            print "TranscriptEditor.select_find(): before...", self.GetCurrentPos(), self.GetSelection()
            print "TranscriptEditor.select_find(): setting selection to (%s, %s)" % (curpos, endpos)

        # NOTE:  Calling SetSelection only caused the loss of the highlight for Locate Clip in Episode.
        # Calling SetCurrentPos() and SetAnchor maintains the highlight correctly.
        self.SetCurrentPos(curpos)
        self.SetAnchor(endpos)

        if DEBUG:
            print "TranscriptEditor.select_find(): pos is now", self.GetCurrentPos(), self.GetSelection()
            
        # NOTE:  STC seems to make a distinction between VISIBLE lines and DOCUMENT lines.
        # we need Visible Lines for scrolling the current position to match the video.
        startline = self.VisibleFromDocLine(self.LineFromPosition(curpos))
        endline = self.VisibleFromDocLine(self.LineFromPosition(endpos))
        
        # Attempt to make the selection visible by scrolling to make
        # the end line visible, and then the start line visible.
        # (so in the worst case, the start is still always visible)
        # We make sure endline+1 is visible because with long lines
        # that span multiple visible lines, it will only ensure that
        # the beginning is visible.

        if DEBUG:
            print "TranscriptEditor.select_find():  scrolling info:"
            print "(%s < %s) or (%s > %s)" % (startline, self.GetFirstVisibleLine(), startline, self.GetFirstVisibleLine() + (self.LinesOnScreen() / 2))
        
        if (startline < self.GetFirstVisibleLine()) or (startline > self.GetFirstVisibleLine() + ((4 * self.LinesOnScreen()) / 5)):
            self.ScrollToLine(startline - 2)

            if DEBUG:
                print "ScrollToLine(%s)" % (startline - 2)
            
        if endline + 1 > self.GetFirstVisibleLine() + self.LinesOnScreen():
            self.ScrollToLine(endline - self.LinesOnScreen() + 2)

            if DEBUG:
                print "ScrollToLine(%s)" % (endline - self.LinesOnScreen() + 2)

        if DEBUG:
            print "TranscriptEditor.select_find():  Position Info:", \
                  self.LineFromPosition(curpos), self.LineFromPosition(endpos), \
                  startline, endline, self.GetFirstVisibleLine(), \
                  self.GetFirstVisibleLine() + self.LinesOnScreen()

    def spell_check(self):
        """Interactively spell-check document."""
    
    def undo(self):
        """Undo last operation(s)."""
        self.Undo()
        
    def redo(self):
        """Redo last undone operation(s)."""
        self.Redo()

    def modified(self):
        """Return TRUE if transcript was modified since last save.
        If no transcript is loaded, this will always return FALSE."""
        return self.TranscriptObj and self.GetModify()

    def set_read_only(self, state=1):
        """Enable or disable read-only mode, to prevent the transcript
        from being modified."""
        self.SetReadOnly(state)

    def get_read_only(self):
        return self.GetReadOnly()

    def find_timecode_before_cursor(self, pos):
        """Return the position of the first timecode before the given cursor position."""
        return self.FindText(pos, 0, "%s<" % TIMECODE_CHAR)
        
    def get_selected_time_range(self):
        """Get the time range of the currently selected text.  Return a tuple with the start and end times in milliseconds."""
        # Default start/end time is 0
        start_timecode = 0
        end_timecode = 0

        # Determine current selection indices
        selstart = self.GetSelectionStart()
        selend = self.GetSelectionEnd()
        if selstart > selend:
            # Need to swap start/end
            temp = selstart
            selstart = selend
            selend = temp
        # Setup for searching transcript for timecodes
        timestr = ''

        if 'unicode' in wx.PlatformInfo:
            findstr = TIMECODE_CHAR + "<".encode('utf8')
            offset = 3
        else:
            findstr = TIMECODE_CHAR + "<"
            offset = 2
        # Searches weren't working right if we clicked right before a TimeCode
        if selstart > 1:
            self.GotoPos(selstart - 1)
        # Set the wxSTC Search Anchor to the start of the selection
        self.SearchAnchor()
        pos = self.SearchPrev(0, findstr)
        if pos > -1:
            self.GotoPos(pos)
            self.SearchAnchor()
            endi = self.SearchNext(0, '>')
            self.SetSelection(pos + offset, endi)
#            self.SetCurrentPos(pos + offset)
#            self.SetAnchor(endi)
            timestr = self.GetSelectedText()
            try:
                start_timecode = int(timestr)
            except:
                pass

        timestr = ""
        # Set the wxSTC Search Anchor to the end of the selection
        self.GotoPos(selend)
        self.SearchAnchor()
        pos = self.SearchNext(0, findstr)
        if pos > -1:
            # Transana has been finding ">" symbols in the text that follow the cursor selection but preceed the next time code.
            # Let's set the SearchAnchor to the start of the time code so it'll find the end correctly.
            self.GotoPos(pos)
            self.SearchAnchor()
            # Now let's look for the next ">" character, which MUST be the end of the time code data.
            endi = self.SearchNext(0, '>')
            self.SetSelection(pos + offset, endi)
#            self.SetCurrentPos(pos + offset)
#            self.SetAnchor(endi)
            timestr = self.GetSelectedText()
            try:
                end_timecode = int(timestr)
            except:
                pass
        # If no later time code is found return -1 
        else:
            end_timecode = -1
        # Now we need to reset the selection to where it used to be.
        self.SetSelection(selstart, selend)
#        self.SetCurrentPos(selstart)
#        self.SetAnchor(selend)
        return (start_timecode, end_timecode)

    def ClearDoc(self):
        # I think we want to be in read-only always at the end of ClearDoc()
        if (self.TranscriptObj != None) and (self.TranscriptObj.isLocked):
            self.TranscriptObj.unlock_record()
        self.set_read_only(0)
        RichTextEditCtrl.ClearDoc(self)
        self.TimePosition = 0
        self.TranscriptObj = None
        self.timecodes = []
        self.current_timecode = -1
        self.set_read_only(1)
        self.codes_vis = 0

    def PrevTimeCode(self, tc=None):
        """Return the timecode immediately before the current one."""
        if tc == None:
            tc = self.current_timecode
        i = self.timecodes.index(tc) - 1
        while i >= 0:
            # Sometimes we might have multiple timecodes with the same value,
            # so we have to do this to ensure we really get a lower timecode
            if self.timecodes[i] < tc:
                return self.timecodes[i]
            i = i - 1
        return self.timecodes[i]

    def NextTimeCode(self, tc=None):
        """Return the timecode immediately after the current one."""
        if tc == None:
            tc = self.current_timecode
        i = self.timecodes.index(tc) + 1
        while i < len(self.timecodes):
            # Sometimes we might have multiple timecodes with the same value,
            # so we have to do this to ensure we really get a higher timecode
            if self.timecodes[i] > tc:
                return self.timecodes[i]
            i = i + 1
        return self.timecodes[i]

    def OnKeyPress(self, event):
        """ Called when a key is pressed down.  All characters are upper case.  """

        # Let's try to remember the cursor position.  (We've had problems wiht the cursor moving during transcription on the Mac.)
        self.cursorPosition = (self.GetCurrentPos(), self.GetSelection())

        # It might be necessary to block the "event.Skip()" call.  Assume for the moment that it is not.
        blockSkip = False
        if event.ControlDown():
            try:
                c = event.GetKeyCode()
                
                # NOTE:  NON-ASCII keys must be processed first, as the chr(c) call raises an exception!
                if c == wx.WXK_UP:
                    # Ctrl-Cursor-Up inserts the Up Arrow / Rising Intonation symbol
                    self.InsertRisingIntonation()
                    return
                elif c == wx.WXK_DOWN:
                    # Ctrl-Cursor-Down inserts the Down Arrow / Falling Intonation symbol
                    self.InsertFallingIntonation()
                    return
                elif chr(c) == "H":
                    # Ctrl-H inserts the High Dot / Inbreath symbol
                    self.InsertInBreath()
                    return
                elif chr(c) == "O":
                    # Ctrl-O inserts the Open Dot / Whispered Speech symbol
                    self.InsertWhisper()
                    return
                elif chr(c) == "B":
                    self.set_bold()
                    self.StyleChanged(self)
                elif chr(c) == "U":
                    self.set_underline()
                    self.StyleChanged(self)
                elif chr(c) == "I":
                    self.set_italic()
                    self.StyleChanged(self)
                elif chr(c) == "T":
                    # CTRL-T pressed
                    self.insert_timecode()
                    return
                elif chr(c) == "S":
                    if not self.parent.ControlObject.IsPlaying():
                        # Explicitly tell Transana to play to the end of the Episode/Clip
                        self.parent.ControlObject.SetVideoEndPoint(-1)
                    # CTRL-S: Play/Pause with auto-rewind
                    self.parent.ControlObject.PlayPause(1)
                    return
                elif chr(c) == "D":
                    if not self.parent.ControlObject.IsPlaying():
                        # Explicitly tell Transana to play to the end of the Episode/Clip
                        self.parent.ControlObject.SetVideoEndPoint(-1)
                    # CTRL-D: Play/Pause without rewinding
                    self.parent.ControlObject.PlayPause(0)
                    return
                elif chr(c) == "A":
                    # CTRL-A: Rewind the video by 10 seconds
                    vpos = self.parent.ControlObject.GetVideoPosition()
                    self.parent.ControlObject.SetVideoStartPoint(vpos-10000)
                    # Explicitly tell Transana to play to the end of the Episode/Clip
                    self.parent.ControlObject.SetVideoEndPoint(-1)
                    # Play should always be initiated on Ctrl-A
                    self.parent.ControlObject.Play(0)
                    return
                elif chr(c) == "F":
                    # CTRL-F: Advance video by 10 seconds
                    vpos = self.parent.ControlObject.GetVideoPosition()
                    self.parent.ControlObject.SetVideoStartPoint(vpos+10000)
                    # Explicitly tell Transana to play to the end of the Episode/Clip
                    self.parent.ControlObject.SetVideoEndPoint(-1)
                    # Play should always be initiated on Ctrl-F
                    self.parent.ControlObject.Play(0)
                    return
                elif chr(c) == "P":
                    # CTRL-P: Previous segment
                    start_timecode = self.PrevTimeCode()
                    self.parent.ControlObject.SetVideoStartPoint(start_timecode)
                    # Explicitly tell Transana to play to the end of the Episode/Clip
                    self.parent.ControlObject.SetVideoEndPoint(-1)
                    # Play should always be initiated on Ctrl-P
                    self.parent.ControlObject.Play(0)
                    return
                elif chr(c) == "N":
                    # CTRL-N: Next segment
                    start_timecode = self.NextTimeCode()
                    self.parent.ControlObject.SetVideoStartPoint(start_timecode)
                    # Explicitly tell Transana to play to the end of the Episode/Clip
                    self.parent.ControlObject.SetVideoEndPoint(-1)
                    # Play should always be initiated on Ctrl-P
                    self.parent.ControlObject.Play(0)
                    return
            except:
                pass    # Non-ASCII value key pressed
        else:
            # Because of time codes and hidden text, we need a bit of extra code here to make sure the cursor is not left in
            # the middle of hidden text and to prevent accidental deletion of hidden time codes.
            c = event.GetKeyCode()
            curpos = self.GetCurrentPos()
            cursel = self.GetSelection()

            # If the are moving to the LEFT with the cursor ...
            if (c == wx.WXK_LEFT):
                # ... and we come to a TIMECODE Character ...
                if (curpos > 0) and (chr(self.GetCharAt(curpos - 1)) == '>') and (self.GetStyleAt(curpos - 1) == self.STYLE_HIDDEN):
                    # ... then we need to find the start of the time code data, signalled by the TIMECODE character ...
                    while (self.GetCharAt(curpos - 1) != ord(TIMECODE_CHAR)):
                        curpos -= 1
                    # If Unicode, we need to move 2 more characters to the left.  This is because of the way the wxSTC
                    # handles the 2-byte timecode character.
                    if 'unicode' in wx.PlatformInfo:
                        curpos -= 1
                    # If Time Codes are not visible, we need one more character here.  It doesn't make sense
                    # to me, as we should be at the end of the time code data, but we DO need this.
                    if not(self.codes_vis):
                        curpos -= 1

                    # If you cursor over a time code while making a selection, the selection was getting lost with
                    # the original code.  Instead, determine if a selection is being made, and if so, make a new
                    # selection appropriately.
                    
                    # If these values differ, we're selecting rather than merely moving.
                    if cursel[0] == cursel[1]:
                        self.GotoPos(curpos)
                    else:
                        # The selection must be made in this order, or the cursor is moved to the END rather than being
                        # left at the beginning of the selection where it belongs!
#                        self.SetSelection(cursel[1], curpos)
                        self.SetCurrentPos(cursel[1])
                        self.SetAnchor(curpos)
            # If the are moving to the RIGHT with the cursor ...
            elif (c == wx.WXK_RIGHT):
                # ... and we come to a TIMECODE Character ...
                # The evaluation to determine we've come to a time code is a little weird under Unicode.
                if 'unicode' in wx.PlatformInfo:
                    if 'wxMac' in wx.PlatformInfo:
                        evaluation = (self.GetCharAt(curpos) == 194) and (self.GetCharAt(curpos + 1) == 167)
                    else:
                        evaluation = (self.GetCharAt(curpos) == 194) and (self.GetCharAt(curpos + 1) == 164)
                else:
                    evaluation = (self.GetCharAt(curpos) == ord(TIMECODE_CHAR))
                
                if evaluation:
                    # ... then we need to find the end of the time code data, signalled by the '>' character ...
                    while chr(self.GetCharAt(curpos)) != '>':
                        curpos += 1
                    # If Time Codes are not visible, we need one more character here.  It doesn't make sense
                    # to me, as we should be at the end of the time code data, but we DO need this.
                    if not(self.codes_vis):
                        curpos += 1

                    # If you cursor over a time code while making a selection, the selection was getting lost with
                    # the original code.  Instead, determine if a selection is being made, and if so, make a new
                    # selection appropriately.
                    
                    # If these values differ, we're selecting rather than merely moving.
                    if cursel[0] == cursel[1]:
                        # Position the cursor after the hidden timecode data
                        self.GotoPos(curpos)
                    else:
#                        self.SetSelection(cursel[0], curpos)
                        self.SetCurrentPos(cursel[0])
                        self.SetAnchor(curpos)
            # DELETE KEY pressed
            elif (c == wx.WXK_DELETE):
                # First, we need to determine if we are deleting a single character or a selection in the transcript.
                (selStart, selEnd) = self.GetSelection()
                # If selStart and selEnd are the same, we are deleting a character.
                if (selStart == selEnd):
                    # Are we in Edit Mode?  Are we trying to delete a Time Code?
                    if 'unicode' in wx.PlatformInfo:
                        if 'wxMac' in wx.PlatformInfo:
                            evaluation = (self.GetCharAt(curpos) == 194) and (self.GetCharAt(curpos + 1) == 167)
                        else:
                            evaluation = (self.GetCharAt(curpos) == 194) and (self.GetCharAt(curpos + 1) == 164)
                    else:
                        evaluation = (self.GetCharAt(curpos) == ord(TIMECODE_CHAR))
                    
                    if not(self.get_read_only()) and evaluation:
                        # If deleting a Time Code, first we determine the time code data for the current position
                        (prevTimeCode, nextTimeCode) = self.get_selected_time_range()
                        # Prompt the user about deleting the Time Code
                        msg = _('Do you want to delete the Time Code at %s?')
                        if 'unicode' in wx.PlatformInfo:
                            # Encode with UTF-8 rather than TransanaGlobal.encoding because this is a prompt, not DB Data.
                            msg = unicode(msg, 'utf8')
                        dlg = Dialogs.QuestionDialog(self, msg % Misc.time_in_ms_to_str(nextTimeCode))
                        # If the user really does want to delete the time code ...
                        if dlg.LocalShowModal() == wx.ID_YES:
                            # We need to remember the current state of self.codes_vis, whether time codes are visible or not.
                            # (This variable gets updated when we call show_all_hidden() and may no longer be accurate.)
                            codes_vis = self.codes_vis
                            # Let's show all the hidden text of the time codes.  This doesn't work without it!
                            self.show_all_hidden()

                            # curpos is the start of our time code, but we need to find the end.
                            # we'll start looking just to the right of the time code.
                            selEnd = curpos + 1
                            # We'll keep looking until we find the ">" character, which closes the time code data.
                            while chr(self.GetCharAt(selEnd)) != '>':
                                selEnd += 1
                            # Set the RichTextCtrl (wxSTC) selection to encompass the full time code
                            self.SetSelection(curpos, selEnd)
                            # Replace the Time Code with nothing to delete it.
                            self.ReplaceSelection('')
                            # We need to remove the time code from the self.timecodes List too.
                            # First we locate that entry ...
                            index = self.timecodes.index(nextTimeCode)
                            # ... then we remove it from the list.
                            self.timecodes = self.timecodes[:index] + self.timecodes[index+1:]
                            # Now we reset the Text Cursor
                            self.SetCurrentPos(curpos)
                            # We better hide all the hidden text for the time code data again                           
                            self.hide_all_hidden()
                            # and we need to reset self.codes_vis to its original state.  (This variable gets updated
                            # when we call hide_all_hidden() and may no longer be accurate.)
                            self.codes_vis = codes_vis

                        else:
                            # We need to block the Skip call so that the key event is not passed up to this control's parent for
                            # processing if the user decides not to delete the time code.
                            blockSkip = True
                        # Now we need to destroy the dialog box
                        dlg.Destroy()
                        
                # Otherwise, we're deleting a Selection
                else:
                    # First, let's set the wxSTC "Target" area to the selection
                    self.SetTargetStart(selStart)
                    self.SetTargetEnd(selEnd)
                    # Let's determine if there is a Time Code in the selection
                    timeCodeSearch = self.SearchInTarget(TIMECODE_CHAR)
                    # A value of -1 indicates no Time Code.  Otherwise there is one (or more).
                    if timeCodeSearch != -1:
                        # Prompt the user about deleting the Time Code
                        msg = _('Your current selection contains at least one Time Code.\nAre you sure you want to delete it?')
                        dlg = Dialogs.QuestionDialog(self, msg)
                        # If the user really does want to delete the time code ...
                        if dlg.LocalShowModal() == wx.ID_YES:
                            # We need to remember the current state of self.codes_vis, whether time codes are visible or not.
                            # (This variable gets updated when we call show_all_hidden() and may no longer be accurate.)
                            codes_vis = self.codes_vis
                            # Let's show all the hidden text of the time codes.  This doesn't work without it!
                            self.show_all_hidden()

                            # The SearchInTarget command appears to have changed our Traget Text, so let's set the wxSTC
                            # "Target" area to the selection again.
                            self.SetTargetStart(selStart)
                            self.SetTargetEnd(selEnd)
                            # Replace the Target Text with nothing to delete it.
                            self.ReplaceTarget('')
                            # We need to remove the time code from the self.timecodes List too.
                            # First we determine the time code data for the current position, which should
                            # give us the time code before the deleted segment and the time code after the
                            # deleted segment.
                            (prevTimeCode, nextTimeCode) = self.get_selected_time_range()
                            # First we locate the indexes for the previous and next time codes
                            startIndex = self.timecodes.index(prevTimeCode)
                            # We're getting an error here if we delete a section (including time codes) that goes
                            # past the last time code.  This should fix that.
                            if nextTimeCode in self.timecodes:
                                endIndex= self.timecodes.index(nextTimeCode)
                            else:
                                if (nextTimeCode == -1) or \
                                   (nextTimeCode >= self.timecodes[len(self.timecodes)-1]):
                                    endIndex = len(self.timecodes)
                                # If we get here, I don't know what's going wrong.  Let's just assume we've only got one time
                                # code highlighted.  This is probably a BAD assumption, but we shouldn't get here unless there's
                                # a rather serious problem anyway.
                                else:
                                    endIndex = startIndex + 1
                            # ... then we remove items from the list that fall between them.
                            self.timecodes = self.timecodes[:startIndex + 1] + self.timecodes[endIndex:]
                            # Now we reset the Text Cursor
                            self.SetCurrentPos(selStart)
                            # We better hide all the hidden text for the time code data again                           
                            self.hide_all_hidden()
                            # and we need to reset self.codes_vis to its original state.  (This variable gets updated
                            # when we call hide_all_hidden() and may no longer be accurate.)
                            self.codes_vis = codes_vis

                        # We need to block the Skip call so that the key event is not passed up to this control's parent for
                        # processing.  The delete is handled locally or is declined by the user.
                        blockSkip = True
                        
                        # Now we need to destroy the dialog box
                        dlg.Destroy()

            # BACKSPACE KEY pressed
            elif (c == wx.WXK_BACK):
                # First, we need to determine if we are backspacing over a single character or a selection in the transcript.
                (selStart, selEnd) = self.GetSelection()
                # If selStart and selEnd are the same, we are backspacing over a character.
                if (selStart == selEnd):
                    # If we're in Edit Mode and the cursor is not at 0 (where you can't backspace) and
                    # you are backspacing over a hidden '>' character, indicating the end of Time Code data ...
                    if not(self.get_read_only()) and (curpos > 0) and \
                       (chr(self.GetCharAt(curpos - 1)) == '>') and (self.GetStyleAt(curpos - 1) == self.STYLE_HIDDEN):

                        # Under some odd set of circumstances, the characters "BS" appear in the transcript upon backspacing!
                        # We can't detect the BS here.  Therefore, we have to let it appear, and then remove it later.
                        # If deleting a Time Code, first we determine the time code data for the current position
                        (prevTimeCode, nextTimeCode) = self.get_selected_time_range()
                        # Prompt the user about deleting the Time Code
                        msg = _('Do you want to delete the Time Code at %s?')
                        if 'unicode' in wx.PlatformInfo:
                            # Encode with UTF-8 rather than TransanaGlobal.encoding because this is a prompt, not DB Data.
                            msg = unicode(msg, 'utf8')
                        dlg = Dialogs.QuestionDialog(self, msg % Misc.time_in_ms_to_str(prevTimeCode))
                        # If the user really does want to delete the time code ...
                        if dlg.LocalShowModal() == wx.ID_YES:
                            # We need to remember the current state of self.codes_vis, whether time codes are visible or not.
                            # (This variable gets updated when we call show_all_hidden() and may no longer be accurate.)
                            codes_vis = self.codes_vis
                            # Let's show all the hidden text of the time codes.  This doesn't work without it!
                            self.show_all_hidden()

                            # curpos is the end of our time code, but we need to find the start.
                            # we'll start looking where we are.
                            selStart = curpos
                            selEnd = curpos 
                            # keep moving to the left until we find the Time Code character
                            while self.GetCharAt(selStart) != ord(TIMECODE_CHAR):
                                selStart -= 1
                            # We need to adjust by 1 more character under Unicode because of the way wxSTC handles the 2-byte time code
                            if 'unicode' in wx.PlatformInfo:
                                selStart -= 1
                            # Set the RichTextCtrl (wxSTC) selection to encompass the full time code
                            self.SetSelection(selStart, selEnd)
                            # Replace the Time Code with nothing to delete it.
                            self.ReplaceSelection('')
                            # We need to remove the time code from the self.timecodes List too.
                            # First we locate that entry ...
                            index = self.timecodes.index(prevTimeCode)
                            # ... then we remove it from the list.
                            self.timecodes = self.timecodes[:index] + self.timecodes[index+1:]
                            # We better hide all the hidden text for the time codes again
                            self.hide_all_hidden()
                            # and we need to reset self.codes_vis to its original state.  (This variable gets updated
                            # when we call hide_all_hidden() and may no longer be accurate.)
                            self.codes_vis = codes_vis

                        # Okay, this is weird.  I suspect a bug in wx.STC.
                        # If you insert a Time Code, then Backspace over it, the letters "BS" get added to the Transcript.  This is
                        # obviously not acceptable.  I've added some code here to try to detect and prevent this from showing up.
                        # I'd rather this code appeared above the MessageDialog, but it can't because it won't detect the Backspace
                        # character yet up there.  Bummer.

                        BSCurpos = self.GetCurrentPos()
                        # This detects the BS when the user elects NOT to remove the Time Code
                        if self.GetCharAt(BSCurpos-1) == 8:
                            self.SetSelection(BSCurpos-1, BSCurpos)
                            self.ReplaceSelection('')
                        # This detects the BS when the user elects to remove the Time Code
                        elif self.GetCharAt(BSCurpos) == 8:
                            self.SetSelection(BSCurpos, BSCurpos+1)
                            self.ReplaceSelection('')

                        # We need to block the Skip call so that the key event is not passed up to this control's parent for
                        # processing.  We do this regardless of the user response in the dialog, as the deletion is handled locally.
                        blockSkip = True
                            
                        dlg.Destroy()
                        
                # Otherwise, we're backspacing over a Selection
                else:
                    # First, let's set the wxSTC "Target" area to the selection
                    self.SetTargetStart(selStart)
                    self.SetTargetEnd(selEnd)
                    # Let's determine if there is a Time Code in the selection
                    timeCodeSearch = self.SearchInTarget(TIMECODE_CHAR)
                    # A value of -1 indicates no Time Code.  Otherwise there is one (or more).
                    if timeCodeSearch != -1:
                        # Prompt the user about deleting the Time Code
                        msg = _('Your current selection contains at least one Time Code.\nAre you sure you want to delete it?')
                        dlg = Dialogs.QuestionDialog(self, msg)
                        # If the user really does want to delete the time code ...
                        if dlg.LocalShowModal() == wx.ID_YES:
                            # We need to remember the current state of self.codes_vis, whether time codes are visible or not.
                            # (This variable gets updated when we call show_all_hidden() and may no longer be accurate.)
                            codes_vis = self.codes_vis
                            # Let's show all the hidden text of the time codes.  This doesn't work without it!
                            self.show_all_hidden()

                            # The SearchInTarget command appears to have changed our Traget Text, so let's set the wxSTC
                            # "Target" area to the selection again.
                            self.SetTargetStart(selStart)
                            self.SetTargetEnd(selEnd)
                            # Replace the Target Text with nothing to delete it.
                            self.ReplaceTarget('')
                            # We need to remove the time code from the self.timecodes List too.
                            # First we determine the time code data for the current position, which should
                            # give us the time code before the deleted segment and the time code after the
                            # deleted segment.
                            (prevTimeCode, nextTimeCode) = self.get_selected_time_range()
                            # First we locate the indexes for the previous and next time codes
                            startIndex = self.timecodes.index(prevTimeCode)
                            endIndex= self.timecodes.index(nextTimeCode)
                            # ... then we remove items from the list that fall between them.
                            self.timecodes = self.timecodes[:startIndex + 1] + self.timecodes[endIndex:]
                            # Now we reset the Text Cursor
                            self.SetCurrentPos(selStart)
                            # We better hide all the hidden text for the time code data again                           
                            self.hide_all_hidden()
                            # and we need to reset self.codes_vis to its original state.  (This variable gets updated
                            # when we call hide_all_hidden() and may no longer be accurate.)
                            self.codes_vis = codes_vis

                        # We need to block the Skip call so that the key event is not passed up to this control's parent for
                        # processing.  We do this regardless of the user response in the dialog, as the deletion is handled locally.
                        blockSkip = True
                        
                        # Now we need to destroy the dialog box
                        dlg.Destroy()

            elif c == wx.WXK_F12:
                # F12 is Quick Save
                self.save_transcript()
                blockSkip = True

        if not(blockSkip):
            event.Skip()
            
    def OnChar(self, event):
        """Called when a character key is pressed.  Works with case-sensitive characters.  """
        # It might be necessary to block the "event.Skip()" call.  Assume for the moment that it is not.
        blockSkip = False
        # We only need to deal with characters here.
        try:
            ch = chr(event.GetKeyCode())
            # First, we need to determine if we are deleting a single character or a selection in the transcript.
            (selStart, selEnd) = self.GetSelection()
            # If selStart and selEnd are different, we have a selection.  We also need to be in Edit mode.
            if not(self.get_read_only()) and (selStart != selEnd):
                # First, let's set the wxSTC "Target" area to the selection
                self.SetTargetStart(selStart)
                self.SetTargetEnd(selEnd)
                # Let's determine if there is a Time Code in the selection
                timeCodeSearch = self.SearchInTarget(TIMECODE_CHAR)
                # A value of -1 indicates no Time Code.  Otherwise there is one (or more).
                if timeCodeSearch != -1:
                    # Prompt the user about deleting the Time Code
                    msg = _('Your current selection contains at least one Time Code.\nAre you sure you want to delete it?')
                    dlg = Dialogs.QuestionDialog(self, msg)
                    # If the user really does want to delete the time code ...
                    if dlg.LocalShowModal() == wx.ID_YES:
                        self.SetTargetStart(selStart)
                        self.SetTargetEnd(selEnd)
                        # Replace the Target Text with nothing to delete it.
                        self.ReplaceTarget(ch)
                        self.GotoPos(selStart + 1)
                    blockSkip = True
        except:
            pass

        if not(blockSkip):
            event.Skip()

    def CheckTimeCodesAtSelectionBoundaries(self):
        """ Check the start and end of a selection and make sure neither is in the middle of a time code """
        # We need to make sure the cursor is not positioned between a time code symbol and the time code data, which unfortunately
        # can happen.  Preventing this is the sole function of this section of this method.

        # NOTE:  This sort of code seems to appear in at least 3 spots.
        #          1.  TranscriptEditor.OnLeftUp
        #          2.  TranscriptEditor.OnStartDrag
        #          3.  RichTextEditCtrl.__ProcessDocAsRTF
        #        I just added the third, as the first two weren't adequate under Unicode
        #   *** Better look at select_find() too!!
        #        DKW, 5/8/2006.  I'm going with the theory that I don't need to evaluate in RichTextEditCtrl any more,
        #                        since I think I just corrected the Unicode problem here.

        # First, see if we have a click Position or a click-drag Selection.
        if (self.GetSelectionStart() != self.GetSelectionEnd()):
            
            # We have a click-drag Selection.  We need to check the start and the end points.
            selStart = self.GetSelectionStart()
            selEnd = self.GetSelectionEnd()

            # Let's see if any change is made.
            selChanged = False
            # Let's see if the start of the selection falls between a Time Code and its data.
            # We can also check to see if the first character is a time code, in which case it should be excluded too!
            if 'unicode' in wx.PlatformInfo:
                if 'wxMac' in wx.PlatformInfo:
                    evaluation = (self.GetCharAt(selStart - 1) == 194) and (self.GetCharAt(selStart) == 167)
                    evaluation2 = (self.GetCharAt(selStart - 2) == 194) and (self.GetCharAt(selStart - 1) == 167)
                    evaluation = evaluation or evaluation2
                else:
                    evaluation = (self.GetCharAt(selStart - 1) == 194) and (self.GetCharAt(selStart) == 164)
                    evaluation2 = (self.GetCharAt(selStart - 2) == 194) and (self.GetCharAt(selStart - 1) == 164)
                    evaluation = evaluation or evaluation2
                        
            else:
                evaluation = (self.GetCharAt(selStart - 1) == ord(TIMECODE_CHAR)) and (chr(self.GetCharAt(selStart)) == '<')
                
            if (selStart > 0) and evaluation:
                # If so, we have a change
                selChanged = True
                # Let's find the position of the end of the Time Code
                while chr(self.GetCharAt(selStart - 1)) != '>':
                    selStart += 1

            # Let's see if the end of the selection falls between a Time Code and its data
            if 'unicode' in wx.PlatformInfo:
                if 'wxMac' in wx.PlatformInfo:
                    evaluation = (self.GetCharAt(selEnd - 1) == 194) and (self.GetCharAt(selEnd) == 167)
                    evaluation2 = (self.GetCharAt(selEnd) == 194) and (self.GetCharAt(selEnd + 1) == 167)
                    evaluation3 = (self.GetCharAt(selEnd - 2) == 194) and (self.GetCharAt(selEnd - 1) == 167)
                    evaluation = evaluation or evaluation2 or evaluation3
                else:
                    evaluation = (self.GetCharAt(selEnd - 1) == 194) and (self.GetCharAt(selEnd) == 164)
                    evaluation2 = (self.GetCharAt(selEnd) == 194) and (self.GetCharAt(selEnd + 1) == 164)
                    evaluation3 = (self.GetCharAt(selEnd - 2) == 194) and (self.GetCharAt(selEnd - 1) == 164)
                    evaluation = evaluation or evaluation2 or evaluation3
            else:
                evaluation = (self.GetCharAt(selEnd - 1) == ord(TIMECODE_CHAR)) and (chr(self.GetCharAt(selEnd)) == '<')

            if (selEnd > 0) and ((evaluation) or ((chr(self.GetCharAt(selEnd - 1)) == '>') and (self.STYLE_HIDDEN == self.GetStyleAt(selEnd - 1)))):
                # If so, we have a change
                selChanged = True
                # Let's find the position before the Time Code
                if 'unicode' in wx.PlatformInfo:
                    endChar = 194
                else:
                    endChar = ord(TIMECODE_CHAR)
                while self.GetCharAt(selEnd) != endChar:
                    selEnd -= 1

                    if DEBUG:
                        print "TranscriptEditor.CheckTimeCodesAtSelectionBoundaries end shift ... "

        else:
            selChanged = False
            # We have a click Position.  We just need to check the current position.
            curPos = self.GetCurrentPos()
            # Let's see if we are between a Time code and its Data
            if 'unicode' in wx.PlatformInfo:

                if DEBUG:
                    print "TranscriptEditor.CheckTimeCodesAtSelectionBoundaries():"
                    print curPos, (curPos > 0)
                    print self.GetCharAt(curPos - 1), (self.GetCharAt(curPos - 1) == 194)
                    print self.GetCharAt(curPos), (self.GetCharAt(curPos) == 164)
                    print chr(self.GetCharAt(curPos + 1)), (chr(self.GetCharAt(curPos + 1)) == '<')

                if 'wxMac' in wx.PlatformInfo:
                    evaluation = (self.GetCharAt(curPos - 1) == 194) and (self.GetCharAt(curPos) == 167)
                    evaluation2 = (self.GetCharAt(curPos - 2) == 194) and (self.GetCharAt(curPos - 1) == 167)
                    evaluation = evaluation or evaluation2
                else:
                    evaluation = (self.GetCharAt(curPos - 1) == 194) and (self.GetCharAt(curPos) == 164)
                    evaluation2 = (self.GetCharAt(curPos - 2) == 194) and (self.GetCharAt(curPos - 1) == 164)
                    evaluation = evaluation or evaluation2

            else:
                evaluation = (curPos > 0) and (self.GetCharAt(curPos - 1) == ord(TIMECODE_CHAR)) and (chr(self.GetCharAt(curPos)) == '<') 

            if evaluation:
                # Let's find the position of the end of the Time Code
                while chr(self.GetCharAt(curPos - 1)) != '>':
                    curPos += 1

                self.GotoPos(curPos)

                self.SetAnchor(curPos)
                self.SetCurrentPos(curPos)

        if selChanged:
            self.SetSelection(selStart, selEnd)
#            self.SetCurrentPos(selStart)
#            self.SetAnchor(selEnd)

    def OnStartDrag(self, event, copyToClipboard=False):
        """Called on the initiation of a Drag within the Transcript."""
        if not self.TranscriptObj:
            # No transcript loaded, abort
            return

        # We need to make sure the cursor is not positioned between a time code symbol and the time code data, which unfortunately
        # can happen.  Preventing this is the sole function of this section of this method.
        self.CheckTimeCodesAtSelectionBoundaries()

        # Let's get the time code boundaries.  This will return a start_time of 0 if there's not initial time code,
        # and an end_time of -1 if there's no ending time code.
        (start_time, end_time) = self.get_selected_time_range()

        # We may need to make some minor adjustments to the clips start and stop times.  First, let's
        # see if we're in an Episode Transcript or a Clip Transcript.
        if self.TranscriptObj.clip_num != 0:
            # We're in an Clip Transcript.  If we don't have a starting time code ...
            if start_time == 0:
                # ... we need to use the CLIP's start as the sub-clip's start time, not the start of the video (0:00:00.0)!
                start_time = self.parent.ControlObject.GetVideoStartPoint()
        # If we don't have an end Time Code ...
        if end_time == -1:
            # We need the VideoEndPoint.  This is accurate for either Episode Transcripts or Clip Transcripts.
            end_time = self.parent.ControlObject.GetVideoEndPoint()

        # Let's get the selected Transcript text in RTF format
        rtfText = self.GetRTFBuffer(select_only=1)

        if DEBUG:
            print "TranscriptEditor.OnStartDrag():  rtfText ="
            for x in rtfText:
                if ord(x) < 127:
                    print x,
                else:
                    print " ",
                print ord(x)
            print
            
        # Create a ClipDragDropData object with all the data we need to create a Clip
        data = DragAndDropObjects.ClipDragDropData(self.TranscriptObj.number, self.TranscriptObj.episode_num, \
                start_time, end_time, rtfText)

        # let's convert that object into a portable string using cPickle. (cPickle is faster than Pickle.)
        pdata = cPickle.dumps(data, 1)
        # Create a CustomDataObject with the format of the ClipDragDropData Object
        cdo = wx.CustomDataObject(wx.CustomDataFormat("ClipDragDropData"))
        # Put the pickled data object in the wxCustomDataObject
        cdo.SetData(pdata)

        # If we are supposed to copy the data to the Clip Board ...
        if copyToClipboard:
            # ... then copy the data to the clipboard!
            wx.TheClipboard.SetData(cdo)
        else:
            # Put the data in the DropSource object
            tds = TranscriptDropSource(self.parent)
            tds.SetData(cdo)

            # Initiate the drag operation.
            # NOTE:  Trying to use a value of wx.Drag_CopyOnly to resolve a Mac bug (which it didn't) caused
            #        Windows to stop allowing Clip Creation!
            dragResult = tds.DoDragDrop(wx.Drag_AllowMove)

            # This is a HORRIBLE, EVIL HACK and I hang my head in shame.  I've also spent two days on this one and have not been able to 
            # find any other way to handle it.
            # On the Mac, if you are in Edit Mode and create a Clip, the text in your Transcript gets cut.  There doesn't seem to be anything
            # you can do to prevent it.  Telling the STC it can CopyOnly has no effect.  Changing the dragResult to any legal value
            # at any point in the process has no effect.  Trying to invoke the STC Event using event.Skip() has no effect.
            # The only thing I've found to do is to detect the circumstances, and tell the RichTextEditCtrl to undo the removal of the text.
            # As mentioned above, I hang my head in shame.  Hopefully the next wxPython (this is 2.5.3.1) will fix this.
            if ("__WXMAC__" in wx.PlatformInfo) and (not self.get_read_only()):
                wx.CallAfter(self.undo)

        # Reset the cursor following the Drag/Drop event
        self.parent.SetCursor(wx.StockCursor(wx.CURSOR_ARROW))

    def PositionAfter(self):

        if DEBUG:
            print "PositionAfter", self.pos

        self.ScrollToLine(self.FVL)
        self.GotoPos(self.pos)

    def SetSelectionAfter(self):

        if DEBUG:
            print "SetSelectionAfter", self.selection

#        self.SetSelection(self.selection[0], self.selection[1])
        self.SetCurrentPos(self.selection[0])
        self.SetAnchor(self.selection[1])

    def OnLeftUp(self, event):
        """ Left Mouse Button Up event """
        # We need to make sure the cursor is not positioned between a time code symbol and the time code data, which unfortunately
        # can happen.
        self.CheckTimeCodesAtSelectionBoundaries()

        # Save the original Cursor Position / Selection so it can be restored later.  Otherwise, we occasionally can't
        # make a new selection.
        self.cursorPosition = (self.GetCurrentPos(), self.GetSelection())
        # Note the current Position of if PositionAfter needs to be called
        self.pos = self.GetCurrentPos()
        # Set the selection in case SetSelectionAfter gets called later
        self.selection = self.GetSelection()
        # Remember the first visible line
        self.FVL = self.GetFirstVisibleLine()
        # Get the Start and End times from the time codes on either side of the cursor
        (segmentStartTime, segmentEndTime) = self.get_selected_time_range()
        # The code that is now indented was causing an error if you tried to edit the Transcript from the
        # Clip Properties form, as the parent didn't have a ControlObject property.
        # Therefore, let's test that we're coming from the Transcript Window before we do this test.
        if type(self.parent).__name__ == '_TranscriptDialog':

            # If we have a Clip loaded, the StartTime should be the beginning of the Clip, not 0!
            if type(self.parent.ControlObject.currentObj).__name__ == 'Clip' and (segmentStartTime == 0):
                segmentStartTime = self.parent.ControlObject.currentObj.clip_start

            # If we're in read_only mode and the video is not currently playing, position video immediately with left-click.
            # If we are not in read_only mode, we need to delay the selection until right-click.
            if self.get_read_only() and not self.parent.ControlObject.IsPlaying():
                # First, clear the current selection in the visualization window, if there is one.
                self.parent.ControlObject.ClearVisualizationSelection()
                # Set the start and end points to match the current segment
                self.parent.ControlObject.SetVideoSelection(segmentStartTime, segmentEndTime)

        # If we do not already have a cursor position saved, save it
        if self.cursorPosition == 0:
            self.cursorPosition = (self.GetCurrentPos(), self.GetSelection())
        else:
            if self.cursorPosition[1][0] == self.cursorPosition[1][1]:
                wx.CallAfter(self.PositionAfter)
            else:
                self.ScrollToLine(self.FVL)
                wx.CallAfter(self.SetSelectionAfter)

                
        # Okay, now let the RichTextEditCtrl have the LeftUp event
        event.Skip()

    def OnRightClick(self, event):
        """ Right-clicking should handle Video Play Control rather than providing the
            traditional right-click editing control menu """
        # If we do not already have a cursor position saved, save it
        self.cursorPosition = (self.GetCurrentPos(), self.GetSelection())

        # Get the Start and End times from the time codes on either side of the cursor
        (segmentStartTime, segmentEndTime) = self.get_selected_time_range()
        # The code that is now indented was causing an error if you tried to edit the Transcript from the
        # Clip Properties form, as the parent didn't have a ControlObject property.
        # Therefore, let's test that we're coming from the Transcript Window before we do this test.
        if type(self.parent).__name__ == '_TranscriptDialog':

            # If we have a Clip loaded, the StartTime should be the beginning of the Clip, not 0!
            if type(self.parent.ControlObject.currentObj).__name__ == 'Clip' and (segmentStartTime == 0):
                segmentStartTime = self.parent.ControlObject.currentObj.clip_start

            # If we're not in read_only mode and the video is not currently playing ...
            if not self.get_read_only() and not self.parent.ControlObject.IsPlaying():
                # First, clear the current selection in the visualization window, if there is one.
                self.parent.ControlObject.ClearVisualizationSelection()
                # Set the start and end points to match the current segment
                self.parent.ControlObject.SetVideoSelection(segmentStartTime, segmentEndTime)

        
        # FOR NON-MAC PLATFORMS
        # Ctrl-Right-Click should play from current position to the end of the video for non-Mac machines!
        if (not '__WXMAC__' in wx.PlatformInfo) and event.ControlDown():
            # Setting End Time to 0 instructs the video player to play to the end of the video!
            segmentEndTime = 0

        # FOR MAC PLATFORM
        # The Mac with a one-button mouse requires the Ctrl-key to emulate a right-click, so we
        # have to add the Meta (Open Apple) key to the mix here.
        # Meta-Right-Click should play from current position to the end of the video on Mac!
        if ('__WXMAC__' in wx.PlatformInfo) and event.MetaDown():
            # Setting End Time to 0 instructs the video player to play to the end of the video!
            segmentEndTime = 0

        # If the video is not currently playing ...
        if not self.parent.ControlObject.IsPlaying():
            # First, clear the current selection in the visualization window, if there is one.
            self.parent.ControlObject.ClearVisualizationSelection()
            # Set the start and end points to match the current segment
            self.parent.ControlObject.SetVideoSelection(segmentStartTime, segmentEndTime)

            self.scroll_to_time(segmentStartTime)

        if DEBUG:
            print "TranscriptEditor.OnRightClick():  Start = %s, Stop = %s" % (segmentStartTime, segmentEndTime)
            
        # Play or Pause the video, depending on its current state
        self.parent.ControlObject.PlayStop()
            
    def RestoreCursor(self):
        """ Restore the Cursor position following right-click play control operation """
        # If we have a stored Cursor Position ...
        if (self.cursorPosition != 0):
            # Reset the Cursor Position
            self.SetCurrentPos(self.cursorPosition[0])
            # And reset the Selection, if there was one.
#            self.SetSelection(self.cursorPosition[1][0], self.cursorPosition[1][1])
            self.SetCurrentPos(self.cursorPosition[1][0])
            self.SetAnchor(self.cursorPosition[1][1])

            #  Only scroll if we're not in Edit Mode.
            if self.get_read_only():
                # now scroll so that the selection start is shown.
                self.ScrollToLine(max(self.VisibleFromDocLine(self.LineFromPosition(self.cursorPosition[1][0])), 0))
            # Once the cursor position has been reset, we need to clear out the Cursor Position Data
            self.cursorPosition = 0

    def AdjustIndexes(self, adjustmentAmount):
        """ Adjust Transcript Time Codes by the specified amount """
        # Let's try to remember the cursor position
        self.cursorPosition = (self.GetCurrentPos(), self.GetSelection())
        
        # Move the cursor to the beginning of the document
        self.GotoPos(0)

        # Let's remember the self.codes_vis setting, as show_all_hidden() changes it.
        codes_vis = self.codes_vis
        # Let's show all the hidden text of the time codes.  This doesn't work without it!
        self.show_all_hidden()

        # Let's find each time code mark and update it.  This will be easier if we use the
        # POSITION rather than the VALUE of the "timecodes" list, as we need to change that
        # list as we go too!
        for loop in range(0, len(self.timecodes)):
            # Find the time code
            self.cursor_find("%s<%d>" % (TIMECODE_CHAR, self.timecodes[loop]))
            # Remember the starting position
            start = self.GetCurrentPos()
            # Now remove characters from the front until we get to the "<", chr(60)
            while (self.GetCharAt(start - 1) != 60):
                start += 1
            # We need to determine the end position the hard way.  select_find() was giving the wrong
            # answer because of the CheckTimeCodesAtSelectionBoundaries() call.
            # So start at the beginning of the time code ...
            end = start
            # ... and keep moving until we find the first ">" character, which closes the time code.
            while self.GetCharAt(end) != ord('>'):
                end += 1

            # Now select the smaller selection, which should just be the Time Code Data
            self.SetSelection(start, end)
            # Finally, replace the old time code data with the new time code data.
            # First delete the old data
            self.ReplaceSelection("")
            # Then insert the new data as hidden text (which is why we can't just plug it in above.)
            self.InsertHiddenText("%d" % (self.timecodes[loop] + int(adjustmentAmount* 1000)))
            # Adjust the local list of Transcript time codes too!
            self.timecodes[loop] = self.timecodes[loop] + int(adjustmentAmount * 1000)
       

        # We better hide all the hidden text for the time codes again
        self.hide_all_hidden()
        # We also need to reset self.codes_vis, which was incorrectly changed by hide_all_hidden()
        self.codes_vis = codes_vis
            
        # Okay, this might not work because of changes we've made to the transcript, but let's
        # try restoring the Cursor Position when all is said and done.
        self.RestoreCursor()
        self.Update()

    def CallFontDialog(self):
        """ Trigger the TransanaFontDialog, either updating the font settings for the selected text or
            changing the the font settingss for the current cursor position. """
        # Let's try to remember the cursor position
        self.cursorPosition = (self.GetCurrentPos(), self.GetSelection())
        # Get current Font information from the Editor
        editorFont = self.get_font()

        # If we don't have a text selection, we can just get the wxFontData and go.
        if self.GetSelection()[0] == self.GetSelection()[1]:
            # Create and populate a wxFont object
            font = wx.Font(editorFont[1], wx.FONTFAMILY_DEFAULT, wx.NORMAL, wx.NORMAL, faceName=editorFont[0])
            # font.SetFaceName(editorFont[0])
            #font.SetPointSize(editorFont[1])
            if self.get_bold():
                font.SetWeight(wx.BOLD)
            if self.get_italic():
                font.SetStyle(wx.ITALIC)
            if self.get_underline():
                font.SetUnderlined(True)

            # Create and populate a wxFontData object
            fontData = wx.FontData()
            fontData.EnableEffects(True)
            fontData.SetInitialFont(font)

            # There is a bug in wxPython.  wx.ColourRGB() transposes Red and Blue.  This hack fixes it!
            color = wx.ColourRGB(editorFont[2])
            rgbValue = (color.Red() << 16) | (color.Green() << 8) | color.Blue()
            fontData.SetColour(wx.ColourRGB(rgbValue))
            
        # If we DO have a selection, we need to check, for mixed font specs in the selection
        else:
            # Set the Wait cursor (This doesn't appear to show up.)
            self.SetCursor(wx.StockCursor(wx.CURSOR_WAIT))
            
            # First, get the initial values for the Font Dialog.  This will match the
            # formatting of the LAST character in the selection.
            fontData = TransanaFontDialog.TransanaFontDef()
            fontData.fontFace = editorFont[0]
            fontData.fontSize = editorFont[1]
            if self.get_bold():
                fontData.fontWeight = TransanaFontDialog.tfd_BOLD
            else:
                fontData.fontWeight = TransanaFontDialog.tfd_OFF
            if self.get_italic():
                fontData.fontStyle = TransanaFontDialog.tfd_ITALIC
            else:
                fontData.fontStyle = TransanaFontDialog.tfd_OFF
            if self.get_underline():
                fontData.fontUnderline = TransanaFontDialog.tfd_UNDERLINE
            else:
                fontData.fontUnderline = TransanaFontDialog.tfd_OFF
            # There is a bug in wxPython.  wx.ColourRGB() transposes Red and Blue.  This hack fixes it!
            color = wx.ColourRGB(editorFont[2])
            rgbValue = (color.Red() << 16) | (color.Green() << 8) | color.Blue()
            fontData.fontColorDef = wx.ColourRGB(rgbValue)

            # Now we need to iterate through the selection and look for any characters with different font values.
            for selPos in range(self.GetSelection()[0], self.GetSelection()[1]):
                # We don't touch the settings for TimeCodes or Hidden TimeCode Data, so these characters can be ignored.                
                if not (self.GetStyleAt(selPos) in [self.STYLE_TIMECODE, self.STYLE_HIDDEN]):
                    # Get the Font Attributes of the current Character
                    attrs = self.style_attrs[self.GetStyleAt(selPos)]

                    # Now look for specs that are different, and flag the TransanaFontDef object if one is found.
                    # If the the Symbol Font is used, we ignore this.  (We don't want to change the Font Face of Special Characters.)
                    if (fontData.fontFace != None) and (attrs.font_face != 'Symbol') and (attrs.font_face != fontData.fontFace):
                        del(fontData.fontFace)

                    if (fontData.fontSize != None) and (attrs.font_size != fontData.fontSize):
                        del(fontData.fontSize)

                    if (fontData.fontWeight != TransanaFontDialog.tfd_AMBIGUOUS) and \
                       ((attrs.bold == True) and (fontData.fontWeight == TransanaFontDialog.tfd_OFF)) or \
                       ((attrs.bold == False) and (fontData.fontWeight == TransanaFontDialog.tfd_BOLD)):
                        fontData.fontWeight = TransanaFontDialog.tfd_AMBIGUOUS

                    if (fontData.fontStyle != TransanaFontDialog.tfd_AMBIGUOUS) and \
                       ((attrs.italic == True) and (fontData.fontStyle == TransanaFontDialog.tfd_OFF)) or \
                       ((attrs.italic == False) and (fontData.fontStyle == TransanaFontDialog.tfd_ITALIC)):
                        fontData.fontStyle = TransanaFontDialog.tfd_AMBIGUOUS

                    if (fontData.fontUnderline != TransanaFontDialog.tfd_AMBIGUOUS) and \
                       ((attrs.underline == True) and (fontData.fontUnderline == TransanaFontDialog.tfd_OFF)) or \
                       ((attrs.underline == False) and (fontData.fontUnderline == TransanaFontDialog.tfd_UNDERLINE)):
                        fontData.fontUnderline = TransanaFontDialog.tfd_AMBIGUOUS

                    color = wx.ColourRGB(attrs.font_fg)
                    rgbValue = (color.Red() << 16) | (color.Green() << 8) | color.Blue()
                    if (fontData.fontColorDef != None) and (fontData.fontColorDef != wx.ColourRGB(rgbValue)):
                        del(fontData.fontColorDef)
            # Set the cursor back to normal
            self.SetCursor(wx.StockCursor(wx.CURSOR_ARROW))

        # Create the TransanaFontDialog.
        # Note:  We used to use the wx.FontDialog, but this proved inadequate for a number of reasons.
        #        It offered very few font choices on the Mac, and it couldn't handle font ambiguity.
        fontDialog = TransanaFontDialog.TransanaFontDialog(self, fontData)
        # Display the FontDialog and get the user feedback
        if fontDialog.ShowModal() == wx.ID_OK:
            # If we don't have a text selection, we can just update the current font settings.
            if self.GetSelection()[0] == self.GetSelection()[1]:
                # OLD MODEL -- All characters formatted with all attributes -- no ambiguity allowed.
                # This still applies if there is no selection!
                # Get the wxFontData from the Font Dialog
                newFontData = fontDialog.GetFontData()
                # Extract the Font and Font Color from the FontData
                newFont = newFontData.GetChosenFont()
                newColor = newFontData.GetColour()
                # Set the appropriate Font Attributes.  (Remember, there can be no font ambiguity if there's no selection.)
                if newFont.GetWeight() == wx.BOLD:
                    self.set_bold(True)
                else:
                    self.set_bold(False)
                if newFont.GetStyle() == wx.NORMAL:
                    self.set_italic(False)
                else:
                    self.set_italic(True)
                if newFont.GetUnderlined():
                    self.set_underline(True)
                else:
                    self.set_underline(False)
                # Build a RGB value from newColor.  For some reason the
                # GetRGB() method was returning values in BGR format instead of
                # RGB. -- Nate
                rgbValue = (newColor.Red() << 16) | (newColor.Green() << 8) | newColor.Blue()
                self.set_font(newFont.GetFaceName(), newFont.GetPointSize(), rgbValue, 0xffffff)

            else:
                # Set the Wait cursor
                self.SetCursor(wx.StockCursor(wx.CURSOR_WAIT))
                # NEW MODEL -- Only update those attributes not flagged as ambiguous.  This is necessary
                # when processing a selection
                # Get the TransanaFontDef data from the Font Dialog.
                newFontData = fontDialog.GetFontDef()
                
                # print
                # print "newFontData =", newFontData

                # Now we need to iterate through the selection and update the font information.
                # It doesn't work to try to apply formatting to the whole block, as ambiguous attributes
                # lose their values.
                for selPos in range(self.GetSelection()[0], self.GetSelection()[1]):
                    # We don't want to update the formatting of Time Codes or of hidden Time Code Data.  
                    if not (self.GetStyleAt(selPos) in [self.STYLE_TIMECODE, self.STYLE_HIDDEN]):
                        # Select the character we want to work on from the larger selection
                        self.SetSelection(selPos, selPos + 1)
                        # Get the previous font attributes for this character
                        attrs = self.style_attrs[self.GetStyleAt(selPos)]

                        # Now alter those characteristics that are not ambiguous in the newFontData.
                        # Where the specification is ambiguous, use the old value from attrs.
                        
                        # We don't want to change the font of special symbols!  Therefore, we don't change
                        # the font name for anything in Symbol font.
                        if (newFontData.fontFace != None) and \
                           (attrs.font_face != 'Symbol'):
                            fontFace = newFontData.fontFace
                        else:
                            fontFace = attrs.font_face
                        
                        # print chr(self.GetCharAt(selPos)), "fontFace = ", fontFace
                        
                        if newFontData.fontSize != None:
                            fontSize = newFontData.fontSize
                        else:
                            fontSize = attrs.font_size

                        if newFontData.fontWeight == TransanaFontDialog.tfd_BOLD:
                            self.set_bold(True)
                        elif newFontData.fontWeight == TransanaFontDialog.tfd_OFF:
                            self.set_bold(False)
                        else:
                            # if fontWeight is ambiguous, use the old value
                            if attrs.bold:
                                self.set_bold(True)
                            else:
                                self.set_bold(False)

                        if newFontData.fontStyle == TransanaFontDialog.tfd_OFF:
                            self.set_italic(False)
                        elif newFontData.fontStyle == TransanaFontDialog.tfd_ITALIC:
                            self.set_italic(True)
                        else:
                            # if fontStyle is ambiguous, use the old value
                            if attrs.italic:
                                self.set_italic(True)
                            else:
                                self.set_italic(False)

                        if newFontData.fontUnderline == TransanaFontDialog.tfd_UNDERLINE:
                            self.set_underline(True)
                        elif newFontData.fontUnderline == TransanaFontDialog.tfd_OFF:
                            self.set_underline(False)
                        else:
                            # if fontUnderline is ambiguous, use the old value
                            if attrs.underline:
                                self.set_underline(True)
                            else:
                                self.set_underline(False)

                        if newFontData.fontColorDef != None:
                            color = newFontData.fontColorDef
                            rgbValue = (color.Red() << 16) | (color.Green() << 8) | color.Blue()
                        else:
                            # There is a bug in wxPython.  wx.ColourRGB() transposes Red and Blue.  This hack fixes it!
                            color = wx.ColourRGB(attrs.font_fg)
                            rgbValue = (color.Blue() << 16) | (color.Green() << 8) | color.Red()
                        # Now apply the font settings for the current character
                        self.set_font(fontFace, fontSize, rgbValue, 0xffffff)
                # Set the cursor back to normal
                self.SetCursor(wx.StockCursor(wx.CURSOR_ARROW))

        # Destroy the Font Dialog Box, now that we're done with it.
        fontDialog.Destroy()
        # Let's try restoring the Cursor Position when all is said and done.
        self.RestoreCursor()
        # We've probably taken the focus from the editor.  Let's return it.
        self.SetFocus()
    
# Events    
    def EVT_DOC_CHANGED(self, win, id, func):
        """Set function to be called when document is modified."""


class TranscriptEditorDropTarget(wx.PyDropTarget):
    
    def __init__(self, editor):
        wx.PyDropTarget.__init__(self)
        self.editor = editor

        # specify the type of data we will accept
        # DataTreeDragData is the format used by the tree control,
        # which is a cPickle.dumps() of DataTreeDragDropData()

        self.df = wx.CustomDataFormat("DataTreeDragData")
        self.data = wx.CustomDataObject(self.df)
        self.SetDataObject(self.data)

    # some virtual methods that track the progress of the drag
    def OnEnter(self, x, y, dragResult):
        return dragResult

    def OnLeave(self):
        pass

    def OnDrop(self, x, y):
        # Drop location isn't important for this target, proceed.
        return True

    def OnDragOver(self, x, y, d):
        #self.log.WriteText("OnDragOver: %d, %d, %d\n" % (x, y, d))

        # The value returned here tells the source what kind of visual
        # feedback to give.  For example, if wxDragCopy is returned then
        # only the copy cursor will be shown, even if the source allows
        # moves.  You can use the passed in (x,y) to determine what kind
        # of feedback to give.  In this case we return the suggested value
        # which is based on whether the Ctrl key is pressed.
        return d

    # Called when OnDrop returns True.  We need to get the data and
    # do something with it.
    def OnData(self, x, y, d):
        # copy the data from the drag source to our data object
        if (self.editor.TranscriptObj != None) and self.GetData():

            # Extract actual data passed by DataTreeDropSource
            sourceData = cPickle.loads(self.data.GetData())

            # If a Keyword Node is dropped ...
            if sourceData.nodetype == 'KeywordNode':

                # See if we're creating a QuickClip
                if ('wxMSW' not in wx.PlatformInfo) or TransanaGlobal.configData.quickClipMode:
                    (startTime, endTime) = self.editor.get_selected_time_range()
                    # Determine whether we're creating a Clip from an Episode Transcript
                    if self.editor.TranscriptObj.clip_num == 0:
                        transcriptNum = self.editor.TranscriptObj.number
                        episodeNum = self.editor.TranscriptObj.episode_num
                        if endTime <= 0:
                            endTime = self.editor.parent.ControlObject.currentObj.tape_length
                    else:
                        tempClip = Clip.Clip(self.editor.TranscriptObj.clip_num)
                        transcriptNum = tempClip.transcript_num
                        episodeNum = tempClip.episode_num
                        if startTime == 0:
                            startTime = tempClip.clip_start
                        if endTime <= 0:
                            endTime = tempClip.clip_stop
                    # If the text selection is blank, we need to send a blank rather than RTF for nothing
                    (startPos, endPos) = self.editor.GetSelection()
                    if startPos == endPos:
                        text = ''
                    else:
                        text = self.editor.GetRTFBuffer(select_only=1)

                    clipData = DragAndDropObjects.ClipDragDropData(transcriptNum, episodeNum, startTime, endTime, text)
                    # I'm sure this is horrible form, but I don't know how else to do this from here!
                    dbTree = self.editor.parent.ControlObject.DataWindow.DBTab.tree
                    # Create the Quick Clip
                    DragAndDropObjects.CreateQuickClip(clipData, sourceData.parent, sourceData.text, dbTree)
                else:
                
                    # Now you can do sourceData.recNum, sourceData.text,
                    # sourceData.nodetype should be 'KeywordNode'
                    # Determine where the Transcript was loaded from
                    if self.editor.TranscriptObj:
                        if self.editor.TranscriptObj.clip_num != 0:
                            targetType = 'Clip'
                            targetRecNum = self.editor.TranscriptObj.clip_num
                            clipObj = Clip.Clip(targetRecNum)
                            targetName = clipObj.id
                        else:
                            targetType = 'Episode'
                            targetRecNum = self.editor.TranscriptObj.episode_num
                            epObj = Episode.Episode(targetRecNum)
                            targetName = epObj.id
                        DragAndDropObjects.DropKeyword(self.editor, sourceData, \
                            targetType, targetName, targetRecNum, 0)
                    else:
                        # No transcript Object loaded, do nothing
                        pass

#            We could create a regular clip here if a Collection were dropped!  (Maybe later.)                    
#            else:
#                print "something other than a Keyword node was dropped"
                
        return d  # what is returned signals the source what to do
                  # with the original data (move, copy, etc.)  In this
                  # case we just return the suggested value given to us.


# To create Clips, you need to populate and send a ClipDragDropData object.
class TranscriptDropSource(wx.DropSource):
    """This is a custom DropSource object to drag text from the Transcript
    onto the Data Tree tab."""

    def __init__(self, parent):
        wx.DropSource.__init__(self, parent)
        self.parent = parent

    def SetData(self, obj):
        wx.DropSource.SetData(self, obj)
        self.data = cPickle.loads(obj.GetData())

    def InDatabase(self, windowx, windowy):
       """Determine if the given X/Y position is within the Database Window."""
       (transLeft, transTop, transWidth, transHeight) = self.parent.ControlObject.GetDatabaseDims()
       transRight = transLeft + transWidth
       transBot = transTop + transHeight
       return (windowx >= transLeft and windowx <= transRight and windowy >= transTop and windowy <= transBot)

    def GiveFeedback(self, effect):
        # This method does not provide the x, y coordinates of the mouse within the control, so we
        # have to figure that out the hard way. (Contrast with DropTarget's OnDrop and OnDragOver methods)
        # Get the Mouse Position on the Screen
        (windowx, windowy) = wx.GetMousePosition()

        # Determine if we are over the Database Tree Tab
        if self.InDatabase(windowx, windowy):
            # We need the Database Tree to scroll up or down if we reach the top or bottom of the Tree Control.
            # I KNOW this is poor form, but can't figure out a better way to do it.
            (x, y) = self.parent.ControlObject.DataWindow.DBTab.tree.ScreenToClientXY(windowx, windowy)
            (w, h) = self.parent.ControlObject.DataWindow.DBTab.tree.GetClientSizeTuple()
            # If we are dragging at the top of the window, scroll down
            if y < 8:
                # The wxWindow.ScrollLines() method is only implemented on Windows.  We must use something different on the Mac.
                if "wxMSW" in wx.PlatformInfo:
                   self.parent.ControlObject.DataWindow.DBTab.tree.ScrollLines(-2)
                else:
                   # Suggested by Robin Dunn
                   first = self.parent.ControlObject.DataWindow.DBTab.tree.GetFirstVisibleItem()
                   prev = self.parent.ControlObject.DataWindow.DBTab.tree.GetPrevSibling(first)
                   if prev:
                      # drill down to find last expanded child
                      while self.parent.ControlObject.DataWindow.DBTab.tree.IsExpanded(prev):
                         prev = self.parent.ControlObject.DataWindow.DBTab.tree.GetLastChild(prev)
                   else:
                      # if no previous sub then try the parent
                      prev = self.parent.ControlObject.DataWindow.DBTab.tree.GetItemParent(first)

                   if prev:
                      self.parent.ControlObject.DataWindow.DBTab.tree.ScrollTo(prev)
                   else:
                      self.parent.ControlObject.DataWindow.DBTab.tree.EnsureVisible(first)
            # If we are dragging at the bottom of the window, scroll up
            elif y > h - 8:
                # The wxWindow.ScrollLines() method is only implemented on Windows.  We must use something different on the Mac.
                if "wxMSW" in wx.PlatformInfo:
                   self.parent.ControlObject.DataWindow.DBTab.tree.ScrollLines(2)
                else:
                   # Suggested by Robin Dunn
                   # first find last visible item by starting with the first
                   next = None
                   last = None
                   item = self.parent.ControlObject.DataWindow.DBTab.tree.GetFirstVisibleItem()
                   while item:
                      if not self.parent.ControlObject.DataWindow.DBTab.tree.IsVisible(item): break
                      last = item
                      item = self.parent.ControlObject.DataWindow.DBTab.tree.GetNextVisible(item)

                   # figure out what the next visible item should be,
                   # either the first child, the next sibling, or the
                   # parent's sibling
                   if last:
                       if self.parent.ControlObject.DataWindow.DBTab.tree.IsExpanded(last):
                          next = self.parent.ControlObject.DataWindow.DBTab.tree.GetFirstChild(last)[0]
                       else:
                          next = self.parent.ControlObject.DataWindow.DBTab.tree.GetNextSibling(last)
                          if not next:
                             prnt = self.parent.ControlObject.DataWindow.DBTab.tree.GetItemParent(last)
                             if prnt:
                                next = self.parent.ControlObject.DataWindow.DBTab.tree.GetNextSibling(prnt)

                   if next:
                      self.parent.ControlObject.DataWindow.DBTab.tree.ScrollTo(next)
                   elif last:
                      self.parent.ControlObject.DataWindow.DBTab.tree.EnsureVisible(last)

            # Regular Clips are dropped on Collections or Clips.  Quick Clips are dropped on Keywords.
            if (self.parent.ControlObject.GetDatabaseTreeTabObjectNodeType() == 'CollectionNode') or \
               (self.parent.ControlObject.GetDatabaseTreeTabObjectNodeType() == 'ClipNode') or \
               (self.parent.ControlObject.GetDatabaseTreeTabObjectNodeType() == 'KeywordNode'):
                # Make sure the cursor reflects an acceptable drop.  (This resets it if it was previously changed
                # to indicate a bad drop.)
                self.parent.ControlObject.SetDatabaseTreeTabCursor(wx.CURSOR_ARROW)
                # FALSE indicates that feedback is NOT being overridden, and thus that the drop is GOOD!
                return False
            else:
                # Set the cursor to give visual feedback that the drop will fail.
                self.parent.ControlObject.SetDatabaseTreeTabCursor(wx.CURSOR_NO_ENTRY)
                # Setting the Effect to wxDragNone has absolutely no effect on the drop, if I understand this correctly.
                effect = wx.DragNone
                # returning TRUE indicates that the default feedback IS being overridden, thus that the drop is BAD!
                return True
        else:
            # Set the cursor to give visual feedback that the drop will fail.
            # NOTE:  We do NOT want to enable text drag within the Transcript.  This would cause problems with keeping the
            #        timecodes ordered correctly.
            self.parent.SetCursor(wx.StockCursor(wx.CURSOR_NO_ENTRY))
            # Setting the Effect to wxDragNone has absolutely no effect on the drop, if I understand this correctly.
            effect = wx.DragNone
            # returning TRUE indicates that the default feedback IS being overridden, thus that the drop is BAD!
            return True
