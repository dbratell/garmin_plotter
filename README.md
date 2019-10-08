Tool to plot gpx files on a map
===============================

Using garminexport to download gpx files from Garmin Connect,
and minidom to read said files (following the pattern of gpxplotter) and
matplotlib to plot the parsed data and finally
mplleaflet to get the plot onto a map (Openstreetmap).

gpxplotter was a bit too slow because it did more than I needed and it also
couldn't parse dates on my computer. Might have been a Windows thing, but the Z at
the end of ISO-8601 dates could not be parsed.

Usage
=====
Download the gpx files with garminexport or some other method.
Run:

./python garmin_export <directory>

Flags
=====

 --filter_outliers: If used, if there is a set of fewer than 10% of the total set somewhere far from the normal runs, then those will be ignored.

 --since: If set to a date, only gpx plots since that date will be included

--activity: Specify what activities to include. Can be used several times like "--activity=walking --activity=cycling". If not set, everything will be included.
