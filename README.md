Tool to plot gpx files on a map
===============================

Using garminexport to download gpx files from Garmin Connect,
and minidom to read said files (following the pattern of gpxplotter) and
matplotlib to plot the parsed data and finally
mplleaflet to get the plot onto a map (Openstreetmap).

gpxplotter was a bit too slow because it did more than I needed and it also
couldn't parse dates on my computer. Might have been a Windows thing, but the Z at
the end of ISO-8601 dates could not be parsed.
