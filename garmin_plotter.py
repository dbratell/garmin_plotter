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

def filter_outliers(segments):
    """Filter outliers (for instance a gps plot on the other side of the
    world)"""
    total_segment_count = len(segments)
    max_radius = 0
    centers = []
    for segment in segments:
        boundaries = (np.min(segment["lon"]), np.max(segment["lon"]),
                      np.min(segment["lat"]), np.max(segment["lat"]))
        # FIXME: This is assuming that equal differences in latitude
        # and longitude form squares which is very very far from true.
        # It's *almost* true at the equator but nowhere else and near
        # the poles it's infinitely wrong.
        radius = np.sqrt((boundaries[1] - boundaries[0])**2 +
                         (boundaries[3] - boundaries[2])**2) / 2
        center = (boundaries[0] + (boundaries[1] - boundaries[0]) / 2,
                  boundaries[2] + (boundaries[3] - boundaries[2]) / 2)
        centers.append(center)
        if radius > max_radius:
            max_radius = radius

    import sklearn
    import sklearn.cluster
    dbscan_result = sklearn.cluster.DBSCAN(eps=10*max_radius).fit(centers)
    clusters = dbscan_result.labels_
    cluster_labels = set(clusters)
    if len(cluster_labels) == 1:
        print("No outliers found")
        return segments

    target_cluster = None
    for cluster in sorted(list(cluster_labels)):
        count = sum(1 for c in clusters if c == cluster)
        if count > 0.9 * total_segment_count:
            # This is the cluster we'll plot
            target_cluster = cluster
        print("Cluster %d: %d members" % (cluster, count))

    if target_cluster is None:
        print("Data set too segmented so no single core set of data could be identified.")
        print("Doing no filtering of --filter_outliers.")
        return segments

    print("Filtering out %d (of %d) outliers" % (
        sum(1 for x in clusters if x != target_cluster), total_segment_count))
    segments = [s for (s, c) in zip(segments, clusters) if c == target_cluster]
    return segments

def plot_segments(segments):
    """Plot all the segments on a pyplot figure and return that figure."""
    fig, ax1 = generate_map()

    total_segment_count = len(segments)
    for i, segment in enumerate(segments):
        point_count = len(segment["lon"])
        print("Plotting segment %d/%d (%d points) '%s'..." % (
            (i + 1), total_segment_count, point_count, segment["name"]),
              end="")
        sys.stdout.flush()
        start_time = time.time()
        plot_map(ax1, segment)
        plot_duration = time.time() - start_time
        print("%.2f seconds (%.2f ms per point)" % (
            plot_duration, 1000.0 * plot_duration / point_count))

    fig.tight_layout()
    ax1.use_sticky_edges = True  # Restore to default state
    plt.autoscale(True)

    return fig

def main():
    """Main function when used as a script."""
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument("--activity", nargs="*")
    parser.add_argument("--since")
    parser.add_argument("--filter_outliers", action="store_true")

    args = parser.parse_args()

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

    segments = []
    for track in tracks:
        for segment in track["segments"]:
            segment["name"] = track["name"][0]
            segments.append(segment)
    tracks = None  # Allow GC of all the data

    if args.filter_outliers:
        segments = filter_outliers(segments)

    fig = plot_segments(segments)
    segments = None  # Allow GC of all the data

    print("Saving and opening in a browser (can take a couple of minutes)")
    sys.stdout.flush()
    mplleaflet.show(path="map-all.html", tiles="osm", fig=fig)

if __name__ == "__main__":
    main()
