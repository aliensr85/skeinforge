"""
Oozebane is a script to turn off the extruder before the end of a thread and turn it on before the beginning.

The default 'Activate Oozebane' checkbox is on.  When it is on, the functions described below will work, when it is off, the functions
will not be called.

The important value for the oozebane preferences is "Early Shutdown Distance Over Extrusion Width (ratio)" which is the ratio of the
distance before the end of the thread that the extruder will be turned off over the extrusion width, the default is 2.0.  A higher ratio
means the extruder will turn off sooner and the end of the line will be thinner.

When oozebane turns the extruder off, it slows the feedrate down in steps so in theory the thread will remain at roughly the same
thickness until the end.  The "Turn Off Steps" preference is the number of steps, the more steps the smaller the size of the step that
the feedrate will be decreased and the larger the size of the resulting gcode file, the default is 5.

Oozebane also turns the extruder on just before the start of a thread.  The "Early Startup Maximum Distance Over Extrusion Width"
preference is the ratio of the maximum distance before the thread starts that the extruder will be turned off over the extrusion width,
the default is 2.0.  The longer the extruder has been off, the sooner the extruder will turn back on, the ratio is one minus one over e
to the power of the distance the extruder has been off over the "Early Startup Distance Constant Over Extrusion Width".

After oozebane turns the extruder on, it slows the feedrate down where the thread starts.  Then it speeds it up in steps so in theory
the thread will remain at roughly the same thickness from the beginning.

To run oozebane, in a shell which oozebane is in type:
> python oozebane.py

The following examples oozebane the files Hollow Square.gcode & Hollow Square.gts.  The examples are run in a terminal in the
folder which contains Hollow Square.gcode, Hollow Square.gts and oozebane.py.  The oozebane function will oozebane if the
'Activate Oozebane' checkbox is on.  The functions writeOutput and getOozebaneChainGcode check to see if the text has been
oozebaned, if not they call the getNozzleWipeChainGcode in nozzle_wipe.py to nozzle wipe the text; once they have the nozzle
wiped text, then they oozebane.


> python oozebane.py
This brings up the dialog, after clicking 'Oozebane', the following is printed:
File Hollow Square.gts is being chain oozebaned.
The oozebaned file is saved as Hollow Square_oozebane.gcode


> python oozebane.py Hollow Square.gts
File Hollow Square.gts is being chain oozebaned.
The oozebaned file is saved as Hollow Square_oozebane.gcode


> python
Python 2.5.1 (r251:54863, Sep 22 2007, 01:43:31)
[GCC 4.2.1 (SUSE Linux)] on linux2
Type "help", "copyright", "credits" or "license" for more information.
>>> import oozebane
>>> oozebane.main()
This brings up the oozebane dialog.


>>> oozebane.writeOutput()
File Hollow Square.gts is being chain oozebaned.
The oozebaned file is saved as Hollow Square_oozebane.gcode


>>> oozebane.getOozebaneGcode("
( GCode generated by May 8, 2008 slice.py )
( Extruder Initialization )
..
many lines of gcode
..
")


>>> oozebane.getOozebaneChainGcode("
( GCode generated by May 8, 2008 slice.py )
( Extruder Initialization )
..
many lines of gcode
..
")

"""

from __future__ import absolute_import
#Init has to be imported first because it has code to workaround the python bug where relative imports don't work if the module is imported as a main module.
import __init__

from skeinforge_tools.skeinforge_utilities import euclidean
from skeinforge_tools.skeinforge_utilities import gcodec
from skeinforge_tools.skeinforge_utilities import preferences
from skeinforge_tools import analyze
from skeinforge_tools import import_translator
from skeinforge_tools import nozzle_wipe
from skeinforge_tools import polyfile
import cStringIO
import math
import sys
import time


__author__ = "Enrique Perez (perez_enrique@yahoo.com)"
__date__ = "$Date: 2008/21/04 $"
__license__ = "GPL 3.0"


def getOozebaneChainGcode( filename, gcodeText, oozebanePreferences = None ):
	"Oozebane a gcode linear move text.  Chain oozebane the gcode if it is not already oozebaned."
	gcodeText = gcodec.getGcodeFileText( filename, gcodeText )
	if not gcodec.isProcedureDone( gcodeText, 'nozzle_wipe' ):
		gcodeText = nozzle_wipe.getNozzleWipeChainGcode( filename, gcodeText )
	return getOozebaneGcode( gcodeText, oozebanePreferences )

def getOozebaneGcode( gcodeText, oozebanePreferences = None ):
	"Oozebane a gcode linear move text."
	if gcodeText == '':
		return ''
	if gcodec.isProcedureDone( gcodeText, 'oozebane' ):
		return gcodeText
	if oozebanePreferences == None:
		oozebanePreferences = OozebanePreferences()
		preferences.readPreferences( oozebanePreferences )
	if not oozebanePreferences.activateOozebane.value:
		return gcodeText
	skein = OozebaneSkein()
	skein.parseGcode( gcodeText, oozebanePreferences )
	return skein.output.getvalue()

def writeOutput( filename = '' ):
	"Oozebane a gcode linear move file.  Chain oozebane the gcode if it is not already oozebaned. If no filename is specified, oozebane the first unmodified gcode file in this folder."
	if filename == '':
		unmodified = import_translator.getGNUTranslatorFilesUnmodified()
		if len( unmodified ) == 0:
			print( "There are no unmodified gcode files in this folder." )
			return
		filename = unmodified[ 0 ]
	oozebanePreferences = OozebanePreferences()
	preferences.readPreferences( oozebanePreferences )
	startTime = time.time()
	print( 'File ' + gcodec.getSummarizedFilename( filename ) + ' is being chain oozebaned.' )
	suffixFilename = filename[ : filename.rfind( '.' ) ] + '_oozebane.gcode'
	oozebaneGcode = getOozebaneChainGcode( filename, '', oozebanePreferences )
	if oozebaneGcode == '':
		return
	gcodec.writeFileText( suffixFilename, oozebaneGcode )
	print( 'The oozebaned file is saved as ' + gcodec.getSummarizedFilename( suffixFilename ) )
	analyze.writeOutput( suffixFilename, oozebaneGcode )
	print( 'It took ' + str( int( round( time.time() - startTime ) ) ) + ' seconds to oozebane the file.' )


class OozebaneSkein:
	"A class to oozebane a skein of extrusions."
	def __init__( self ):
		self.afterStartupDistances = []
		self.afterStartupFlowRates = []
		self.decimalPlacesCarried = 3
		self.earlyShutdownDistances = []
		self.earlyShutdownFlowRates = []
		self.earlyStartupDistance = None
		self.extruderActive = False
		self.extruderInactiveLongEnough= False
		self.feedrateMinute = 960.0
		self.isShutdownEarly = False
		self.isShutdownNeeded = False
		self.isStartupEarly = False
		self.lineIndex = 0
		self.lines = None
		self.oldLocation = None
		self.output = cStringIO.StringIO()
		self.shutdownStepIndex = 999999999
		self.startupStepIndex = 999999999

	def addAfterStartupLine( self, splitLine ):
		"Add the after startup lines."
		distanceAfterThreadBeginning = self.getDistanceAfterThreadBeginning()
		location = gcodec.getLocationFromSplitLine( self.oldLocation, splitLine )
		segment = self.oldLocation.minus( location )
		segmentLength = segment.length()
		distanceBack = distanceAfterThreadBeginning - self.afterStartupDistances[ self.startupStepIndex ]
		if segmentLength > 0.0:
			locationBack = location.plus( segment.times( distanceBack / segmentLength ) )
			feedrate = self.feedrateMinute * self.afterStartupFlowRates[ self.startupStepIndex ]
			if not self.isClose( locationBack, self.oldLocation ) and not self.isClose( locationBack, location ):
				self.addLine( self.getLinearMoveWithFeedrate( feedrate, locationBack ) )
		self.startupStepIndex += 1

	def addLine( self, line ):
		"Add a line of text and a newline to the output."
		self.output.write( line + "\n" )

	def addLineSetShutdowns( self, line ):
		"Add a line and set the shutdown variables."
		self.addLine( line )
		self.isShutdownNeeded = False
		self.isShutdownEarly = True

	def addShutSlowDownLine( self, splitLine ):
		"Add the shutdown and slowdown lines."
		distanceThreadEnd = self.getDistanceThreadEnd()
		location = gcodec.getLocationFromSplitLine( self.oldLocation, splitLine )
		segment = self.oldLocation.minus( location )
		segmentLength = segment.length()
		distanceBack = self.earlyShutdownDistances[ self.shutdownStepIndex ] - distanceThreadEnd
		if self.shutdownStepIndex == 0:
			self.isShutdownNeeded = True
		if segmentLength > 0.0:
			locationBack = location.plus( segment.times( distanceBack / segmentLength ) )
			feedrate = self.feedrateMinute * self.earlyShutdownFlowRates[ self.shutdownStepIndex ]
			if not self.isClose( locationBack, self.oldLocation ) and not self.isClose( locationBack, location ):
				self.addLine( self.getLinearMoveWithFeedrate( feedrate, locationBack ) )
				if self.isShutdownNeeded:
					self.addLineSetShutdowns( 'M103' )
		self.shutdownStepIndex += 1

	def addStartupLine( self, distanceThreadBeginning, splitLine ):
		"Add the startup line."
		location = gcodec.getLocationFromSplitLine( self.oldLocation, splitLine )
		segment = self.oldLocation.minus( location )
		segmentLength = segment.length()
		distanceBack = self.earlyStartupDistance - distanceThreadBeginning
		if segmentLength <= 0.0:
			return
		locationBack = location.plus( segment.times( distanceBack / segmentLength ) )
		if not self.isClose( locationBack, self.oldLocation ) and not self.isClose( locationBack, location ):
			self.addLine( self.getLinearMoveWithFeedrate( self.feedrateMinute, locationBack ) )

	def getAddAfterStartupLines( self, line ):
		"Get and / or add after the startup lines."
		splitLine = line.split()
		while self.isDistanceAfterThreadBeginningGreater():
			self.addAfterStartupLine( splitLine )
		if self.startupStepIndex >= self.slowdownStartupSteps:
			return line
		return self.getLinearMoveWithFeedrateSplitLine( self.feedrateMinute * self.getStartupFlowRateMultiplier( self.getDistanceAfterThreadBeginning() / self.afterStartupDistance ), splitLine )

	def getAddBeforeStartupLines( self, line ):
		"Get and / or add before the startup lines."
		distanceThreadBeginning = self.getDistanceThreadBeginning()
		splitLine = line.split()
		if distanceThreadBeginning == None:
			return line
		self.extruderInactiveLongEnough = False
		self.isStartupEarly = True
		self.addStartupLine( distanceThreadBeginning, splitLine )
		self.addLine( 'M101' )
		if self.isJustBeforeStart():
			return self.getLinearMoveWithFeedrateSplitLine( self.feedrateMinute * self.afterStartupFlowRate, splitLine )
		return line

	def getAddShutSlowDownLines( self, line ):
		"Get and / or add the shutdown and slowdown lines."
		distanceThreadEnd = self.getDistanceThreadEnd()
		splitLine = line.split()
		while self.getDistanceThreadEnd() != None:
			self.addShutSlowDownLine( splitLine )
		if distanceThreadEnd != None:
			if distanceThreadEnd > 0.0:
				shutdownLine = self.getLinearMoveWithFeedrateSplitLine( self.feedrateMinute * self.getShutdownFlowRateMultiplier( 1.0 - distanceThreadEnd / self.earlyShutdownDistance ), splitLine )
				if self.isShutdownNeeded:
					self.addLineSetShutdowns( shutdownLine )
					return 'M103'
				return shutdownLine
		return line

	def getDistanceAfterThreadBeginning( self ):
		"Get the distance after the beginning of the thread."
		line = self.lines[ self.lineIndex ]
		splitLine = line.split()
		lastThreadLocation = gcodec.getLocationFromSplitLine( self.oldLocation, splitLine )
		totalDistance = 0.0
		extruderOnReached = False
		for beforeIndex in xrange( self.lineIndex - 1, 3, - 1 ):
			line = self.lines[ beforeIndex ]
			splitLine = line.split()
			firstWord = gcodec.getFirstWord( splitLine )
			if firstWord == 'G1':
				location = gcodec.getLocationFromSplitLine( lastThreadLocation, splitLine )
				totalDistance += location.distance( lastThreadLocation )
				lastThreadLocation = location
				if extruderOnReached:
					return totalDistance
			elif firstWord == 'M101':
				extruderOnReached = True
		return None

	def getDistanceThreadBeginning( self ):
		"Get the distance to the beginning of the thread."
		if self.earlyStartupDistance == None:
			return None
		return self.getDistanceToWord( self.earlyStartupDistance,  'M101' )

	def getDistanceThreadEnd( self ):
		"Get the distance to the end of the thread."
		if self.shutdownStepIndex >= self.slowdownStartupSteps:
			return None
		return self.getDistanceToWord( self.earlyShutdownDistances[ self.shutdownStepIndex ],  'M103' )

	def getDistanceToWord( self, remainingDistance, word ):
		"Get the distance to the word."
		line = self.lines[ self.lineIndex ]
		splitLine = line.split()
		lastThreadLocation = gcodec.getLocationFromSplitLine( self.oldLocation, splitLine )
		totalDistance = 0.0
		for afterIndex in xrange( self.lineIndex + 1, len( self.lines ) ):
			line = self.lines[ afterIndex ]
			splitLine = line.split()
			firstWord = gcodec.getFirstWord( splitLine )
			if firstWord == 'G1':
				location = gcodec.getLocationFromSplitLine( lastThreadLocation, splitLine )
				totalDistance += location.distance( lastThreadLocation )
				lastThreadLocation = location
				if totalDistance >= remainingDistance:
					return None
			elif firstWord == word:
				return totalDistance
		return None

	def getLinearMoveWithFeedrate( self, feedrate, location ):
		"Get a linear move line with the feedrate."
		return 'G1 X%s Y%s Z%s F%s' % ( self.getRounded( location.x ), self.getRounded( location.y ), self.getRounded( location.z ), self.getRounded( feedrate ) )

	def getLinearMoveWithFeedrateSplitLine( self, feedrate, splitLine ):
		"Get a linear move line with the feedrate and split line."
		location = gcodec.getLocationFromSplitLine( self.oldLocation, splitLine )
		return self.getLinearMoveWithFeedrate( feedrate, location )

	def getOozebaneLine( self, line ):
		"Get oozebaned gcode line."
		splitLine = line.split()
		self.feedrateMinute = gcodec.getFeedrateMinute( self.feedrateMinute, splitLine )
		if self.oldLocation == None:
			return line
		if self.startupStepIndex < self.slowdownStartupSteps:
			return self.getAddAfterStartupLines( line )
		if self.extruderInactiveLongEnough:
			return self.getAddBeforeStartupLines( line )
		if self.shutdownStepIndex < self.slowdownStartupSteps:
			return self.getAddShutSlowDownLines( line )
		if self.isJustBeforeStart():
			return self.getLinearMoveWithFeedrateSplitLine( self.feedrateMinute * self.afterStartupFlowRate, splitLine )
		return line

	def getRounded( self, number ):
		"Get number rounded to the number of carried decimal places as a string."
		return euclidean.getRoundedToDecimalPlaces( self.decimalPlacesCarried, number )

	def getShutdownFlowRateMultiplier( self, along ):
		"Get the shut down flow rate multipler."
		along = min( along, float( self.slowdownStartupSteps - 1 ) / float( self.slowdownStartupSteps ) )
		return 1.0 - 0.5 / float( self.slowdownStartupSteps ) - along

	def getStartupFlowRateMultiplier( self, along ):
		"Get the startup flow rate multipler."
		return min( 1.0, 0.5 / float( self.slowdownStartupSteps ) + along )

	def isClose( self, locationFirst, locationSecond ):
		"Determine if the first location is close to the second location."
		return locationFirst.distance2( locationSecond ) < self.closeSquared

	def isDistanceAfterThreadBeginningGreater( self ):
		"Determine if the distance after the thread beginning is greater than the step index after startup distance."
		if self.startupStepIndex >= self.slowdownStartupSteps:
			return False
		return self.getDistanceAfterThreadBeginning() > self.afterStartupDistances[ self.startupStepIndex ]

	def isJustBeforeStart( self ):
		"Determine if the first location is close to the second location."
		if self.extruderActive:
			return False
		if not self.isNextExtruderOn():
			return False
		if self.getDistanceToWord( 1.03 * ( self.earlyShutdownDistance + self.afterStartupDistance ),  'M103' ) != None:
			return False
		self.startupStepIndex = 0
		return True

	def isNextExtruderOn( self ):
		"Determine if there is an extruder on command before a move command."
		line = self.lines[ self.lineIndex ]
		splitLine = line.split()
		for afterIndex in xrange( self.lineIndex + 1, len( self.lines ) ):
			line = self.lines[ afterIndex ]
			splitLine = line.split()
			firstWord = gcodec.getFirstWord( splitLine )
			if firstWord == 'G1' or firstWord == 'M103':
				return False
			elif firstWord == 'M101':
				return True
		return False

	def parseGcode( self, gcodeText, oozebanePreferences ):
		"Parse gcode text and store the oozebane gcode."
		self.lines = gcodec.getTextLines( gcodeText )
		self.parseInitialization( oozebanePreferences )
		for self.lineIndex in xrange( self.lineIndex, len( self.lines ) ):
			line = self.lines[ self.lineIndex ]
			self.parseLine( line )

	def parseInitialization( self, oozebanePreferences ):
		"Parse gcode initialization and store the parameters."
		for self.lineIndex in xrange( len( self.lines ) ):
			line = self.lines[ self.lineIndex ]
			splitLine = line.split()
			firstWord = gcodec.getFirstWord( splitLine )
			if firstWord == '(<extrusionWidth>':
				self.extrusionWidth = float( splitLine[ 1 ] )
				self.setExtrusionWidth( oozebanePreferences )
			elif firstWord == '(<decimalPlacesCarried>':
				self.decimalPlacesCarried = int( splitLine[ 1 ] )
			elif firstWord == '(<extrusionStart>':
				self.addLine( '(<procedureDone> oozebane )' )
				return
			self.addLine( line )

	def parseLine( self, line ):
		"Parse a gcode line and add it to the bevel gcode."
		splitLine = line.split()
		if len( splitLine ) < 1:
			return
		firstWord = splitLine[ 0 ]
		if firstWord == 'G1':
			self.setEarlyStartupDistance( splitLine )
			line = self.getOozebaneLine( line )
			self.oldLocation = gcodec.getLocationFromSplitLine( self.oldLocation, splitLine )
		elif firstWord == 'M101':
			self.extruderActive = True
			self.extruderInactiveLongEnough = False
			if self.getDistanceThreadEnd() == None:
				self.isShutdownNeeded = True
				self.shutdownStepIndex = 0
			if self.isStartupEarly:
				self.isStartupEarly = False
				return
		elif firstWord == 'M103':
			self.extruderActive = False
			self.shutdownStepIndex = 999999999
			if self.getDistanceThreadBeginning() == None:
				self.extruderInactiveLongEnough = True
			self.earlyStartupDistance = None
			if self.isShutdownEarly:
				self.isShutdownEarly = False
				return
		self.addLine( line )

	def setEarlyStartupDistance( self, splitLine ):
		"Set the early startup distance."
		if self.earlyStartupDistance != None:
			return
		totalDistance = 0.0
		lastThreadLocation = gcodec.getLocationFromSplitLine( self.oldLocation, splitLine )
		if self.oldLocation != None:
			totalDistance = lastThreadLocation.distance( self.oldLocation )
		for afterIndex in xrange( self.lineIndex + 1, len( self.lines ) ):
			line = self.lines[ afterIndex ]
			splitLine = line.split()
			firstWord = gcodec.getFirstWord( splitLine )
			if firstWord == 'G1':
				location = gcodec.getLocationFromSplitLine( lastThreadLocation, splitLine )
				totalDistance += location.distance( lastThreadLocation )
				lastThreadLocation = location
			elif firstWord == 'M101':
				distanceConstants = totalDistance / self.earlyStartupDistanceConstant
				self.earlyStartupDistance = self.earlyStartupMaximumDistance * ( 1.0 - math.exp( - distanceConstants ) )
				return

	def setExtrusionWidth( self, oozebanePreferences ):
		"Set the extrusion width."
		self.afterStartupDistance = oozebanePreferences.afterStartupDistanceOverExtrusionWidth.value * self.extrusionWidth
		self.closeSquared = 0.01 * self.extrusionWidth * self.extrusionWidth
		self.earlyShutdownDistance = oozebanePreferences.shutdownDistanceOverExtrusionWidth.value * self.extrusionWidth
		self.earlyStartupMaximumDistance = oozebanePreferences.earlyStartupMaximumDistanceOverExtrusionWidth.value * self.extrusionWidth
		self.earlyStartupDistanceConstant = oozebanePreferences.earlyStartupDistanceConstantOverExtrusionWidth.value * self.extrusionWidth
		self.slowdownStartupSteps = max( 1, oozebanePreferences.slowdownStartupSteps.value )
		for stepIndex in xrange( self.slowdownStartupSteps ):
			afterWay = ( stepIndex + 1 ) / float( self.slowdownStartupSteps )
			afterMiddleWay = self.getStartupFlowRateMultiplier( stepIndex / float( self.slowdownStartupSteps ) )
			downMiddleWay = self.getShutdownFlowRateMultiplier( stepIndex / float( self.slowdownStartupSteps ) )
			downWay = 1.0 - stepIndex / float( self.slowdownStartupSteps )
			self.afterStartupDistances.append( afterWay * self.afterStartupDistance )
			if stepIndex == 0:
				self.afterStartupFlowRate = afterMiddleWay
			else:
				self.afterStartupFlowRates.append( afterMiddleWay )
			self.earlyShutdownFlowRates.append( downMiddleWay )
			self.earlyShutdownDistances.append( downWay * self.earlyShutdownDistance )
		self.afterStartupFlowRates.append( 1.0 )


class OozebanePreferences:
	"A class to handle the oozebane preferences."
	def __init__( self ):
		"Set the default preferences, execute title & preferences filename."
		#Set the default preferences.
		self.archive = []
		self.activateOozebane = preferences.BooleanPreference().getFromValue( 'Activate Oozebane', True )
		self.archive.append( self.activateOozebane )
		self.afterStartupDistanceOverExtrusionWidth = preferences.FloatPreference().getFromValue( 'After Startup Distance Over Extrusion Width (ratio):', 2.0 )
		self.archive.append( self.afterStartupDistanceOverExtrusionWidth )
		self.earlyStartupDistanceConstantOverExtrusionWidth = preferences.FloatPreference().getFromValue( 'Early Startup Distance Constant Over Extrusion Width (ratio):', 30.0 )
		self.archive.append( self.earlyStartupDistanceConstantOverExtrusionWidth )
		self.earlyStartupMaximumDistanceOverExtrusionWidth = preferences.FloatPreference().getFromValue( 'Early Startup Maximum Distance Over Extrusion Width (ratio):', 2.0 )
		self.archive.append( self.earlyStartupMaximumDistanceOverExtrusionWidth )
		self.filenameInput = preferences.Filename().getFromFilename( import_translator.getGNUTranslatorGcodeFileTypeTuples(), 'Open File to be Oozebaned', '' )
		self.archive.append( self.filenameInput )
		self.slowdownStartupSteps = preferences.IntPreference().getFromValue( 'Slowdown Startup Steps (positive integer):', 5 )
		self.archive.append( self.slowdownStartupSteps )
		self.shutdownDistanceOverExtrusionWidth = preferences.FloatPreference().getFromValue( 'Shutdown Distance Over Extrusion Width (ratio):', 2.0 )
		self.archive.append( self.shutdownDistanceOverExtrusionWidth )
		#Create the archive, title of the execute button, title of the dialog & preferences filename.
		self.executeTitle = 'Oozebane'
		self.filenamePreferences = preferences.getPreferencesFilePath( 'oozebane.csv' )
		self.filenameHelp = 'skeinforge_tools.oozebane.html'
		self.saveTitle = 'Save Preferences'
		self.title = 'Oozebane Preferences'

	def execute( self ):
		"Oozebane button has been clicked."
		filenames = polyfile.getFileOrDirectoryTypesUnmodifiedGcode( self.filenameInput.value, import_translator.getGNUTranslatorFileTypes(), self.filenameInput.wasCancelled )
		for filename in filenames:
			writeOutput( filename )


def main( hashtable = None ):
	"Display the oozebane dialog."
	if len( sys.argv ) > 1:
		writeOutput( ' '.join( sys.argv[ 1 : ] ) )
	else:
		preferences.displayDialog( OozebanePreferences() )

if __name__ == "__main__":
	main()
