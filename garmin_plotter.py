"""Plot gpx files to an html files with an svg and show in a browser."""

import argparse
import datetime
import math
import os
import sys
import time
from xml.dom import minidom

import numpy as np
from matplotlib import pyplot as plt
import matplotlib
import mplleaflet

def generate_map():
    """Creates the matplotlib figure to draw at."""
    fig = plt.figure()
    ax1 = fig.add_subplot(111)
    ax1.use_sticky_edges = False  # Too slow if this is True

    return (fig, ax1)

def plot_map(ax1, data):
    """Plot gps data with heart rate colouring."""
    xdata = data["lon"]
    ydata = data["lat"]
    zdata = data["heart_rate"]
    cmap = matplotlib.cm.get_cmap("viridis")

    # Todo: Min on all zdata globally and not just this one? This creates more colouring...
    norm = matplotlib.colors.Normalize(vmin=math.floor(min(zdata)), vmax=math.ceil(max(zdata)))
    colors = [cmap(norm(z)) for z in zdata]
    for i, (xval, yval) in enumerate(zip(xdata, ydata)):
        try:
            ax1.plot([xval, xdata[i + 1]], [yval, ydata[i + 1]],
                     color=colors[i], lw=4, scalex=False, scaley=False, alpha=0.5)
        except IndexError:
            break

def extract_formatted_data(point, key, formatter):
    """Returns an array of data from children named key, converted with |formatter|"""
    key_elements = point.getElementsByTagName(key)
    for key_element in key_elements:
        return [formatter(child.data) for child in key_element.childNodes]

def iso8601_to_datetime(iso8601):
    """Converts a string to a datetime object, assuming the string is in a common
    ISO-8601 format."""
    if "T" in iso8601:
        try:
            # Assume pure UTC first (and %z/%Z don't match Z on my computer).
            parsed_date = datetime.datetime.strptime(iso8601, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            parsed_date = datetime.datetime.strptime(iso8601, "%Y-%m-%dT%H:%M:%S.%f%z")
    else:
        parsed_date = datetime.datetime.strptime(iso8601, "%Y-%m-%d")

    return parsed_date

def get_point_data(point):
    """Get basic information from a track point. Only what is needed."""
    lat = float(point.getAttribute("lat"))
    lon = float(point.getAttribute("lon"))
#    gpx_time = extract_data(point, "time", iso8601_to_datetime)
    heart_rate = extract_formatted_data(point, "ns3:hr", float)

    if heart_rate is None:
        pass
#        print("Could not read heart_rate from data point")
#        print(point.toxml()))
    return lat, lon, heart_rate

def parse_track_segment(segment):
    """Read points in a segment and return data that can be used my matplotlib"""
    points = segment.getElementsByTagName("trkpt")
    lats = []
    lons = []
#    point_times = []
    heart_rates = []
    prev_heart_rate = None
    for point in points:
        lat, lon, heart_rate = get_point_data(point)
        if heart_rate is None:
            if prev_heart_rate is None:
                # Skip this one
                print("Could not read heart_rate for point, skipping point")
                continue
            heart_rate = prev_heart_rate
        prev_heart_rate = heart_rate

        lats.append(lat)
        lons.append(lon)
        heart_rates.extend(heart_rate)
    data = {
        "lat": np.array(lats),
        "lon": np.array(lons),
        "heart_rate": np.array(heart_rates, dtype=np.int_),
    }
    return data


def get_text_from_xml(node, tag_name):
    """Extract and return texts inside child nodes named tag_name."""
    texts = []
    tag_name_elements = node.getElementsByTagName(tag_name)
    for element in tag_name_elements:
        text = "".join(child.data for child in element.childNodes
                       if child.nodeType == child.TEXT_NODE)
        texts.append(text)
    return texts

def read_gpx_file(gpxfile):
    """Read gps data from a gpxfile given."""
    gpx = minidom.parse(gpxfile)
    metadata = gpx.getElementsByTagName("metadata")[0]
    gpx_time = extract_formatted_data(metadata, "time", iso8601_to_datetime)[0]
    tracks = gpx.getElementsByTagName("trk")
    return_value = []
    for track in tracks:
        segments = track.getElementsByTagName("trkseg")
        track_data = {
            "name": get_text_from_xml(track, "name"),
            "type": get_text_from_xml(track, "type"),
            "time": gpx_time,
            "segments": [parse_track_segment(x) for x in segments],
        }
        return_value.append(track_data)

    return return_value

def main():
    """Main function when used as a script."""
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument("--activity", nargs="*")
    parser.add_argument("--since")

    args = parser.parse_args()
    fig, ax1 = generate_map()

    files = [x for x in os.listdir(args.directory) if x.endswith(".gpx")]
    tracks = []
    total_file_count = len(files)
    for k, file_name in enumerate(sorted(files)):
        file_name = os.path.join(args.directory, file_name)
        start_time = time.time()
        print("Reading file %d/%d: %s..." % ((k+1), total_file_count, file_name), end="")
        sys.stdout.flush()
        file_tracks = read_gpx_file(file_name)
        for track in file_tracks:
            if args.since and track["time"] < iso8601_to_datetime(args.since):
                print("Skipping track, too old...", end="")
                continue
            if args.activity and track["type"][0] not in args.activity:
                print("Skipping track, wrong type (%r)..." % track["type"][0], end="")
                continue
            tracks.append(track)
        print("%.2f seconds" % (time.time() - start_time))

    total_segment_count = sum(len(x["segments"]) for x in tracks)
    i = 0
    for track in tracks:
        for segment in track["segments"]:
            i += 1
            point_count = len(segment["lon"])
            print("Plotting segment %d/%d (%d points) '%s' of %d..." % (
                i, total_segment_count, point_count, track["name"][0]),
                  end="")
            sys.stdout.flush()
            start_time = time.time()
            plot_map(ax1, segment)
            plot_duration = time.time() - start_time
            print("%.2f seconds (%.2f ms per point)" % (
                plot_duration, 1000.0 * plot_duration / point_count))
    tracks = None  # Allow GC of all the data

    fig.tight_layout()
    ax1.use_sticky_edges = True  # Restore to default state
    plt.autoscale(True)

    print("Saving and opening in a browser (can take a couple of minutes)")
    sys.stdout.flush()
    mplleaflet.show(path="map-all.html", tiles="osm", fig=fig)

if __name__ == "__main__":
    main()
