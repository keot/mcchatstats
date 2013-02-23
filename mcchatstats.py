#!/usr/bin/env python

# MCchatstats - Converts a Minecraft (MSM) chat log-file into an HTML document
# full of statistics
# Copyright (c) 2012 James Mardell

# MCchatstats is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# MCchatstats is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# MCchatstats. If not, see <http://www.gnu.org/licenses/>.

import sys, math, json, operator, subprocess
from datetime import datetime, timedelta

def magnitude(x0, y0, x1, y1):
	return math.sqrt(pow(float(x0) - float(x1), 2) + pow(float(y0) - float(y1), 2))

def locationName(user_location, locations_filename, location_threshold):
	try:
		locations_file = open(locations_filename, 'r')
		locations_data = locations_file.read().replace('var markersDB={','{', 1).replace('};', '}', 1)
		locations_dict = json.loads(locations_data)

	except IOError:
		sys.stderr.write("Unable to open file '" + locations_filename + "' for reading. Cannot determine locations.\n")
		return "at an unknown location"

	except ValueError:
		sys.stderr.write("Error parsing '" + locations_filename + "'. Cannot determine locations.\n")
		return "at an unknown location"

	else:
		locations_file.close()
	
	# Extract a list of location co-ordinates x, y, z and text
	locations = None
	for k in locations_dict.keys():
		if k.startswith('Locations'):
			locations = locations_dict[k]['raw']

	distances = dict()
	for location in locations:
		distances[location['text']] = magnitude(location['x'], location['z'], user_location[0], user_location[2])
	
	nearest = min(distances, key=distances.get)
	
	if distances[nearest] > location_threshold:
		return 'somewhere far away'
	else:
		return '%.1f m away from %s' % (distances[nearest], nearest.replace('\n', ' ') )
	
	return None

def activityLog(logfile, history=14, resolution=15):
	# Returns an tuple containing a activity log and the set of players
	# logfile: the processed logfile
	# history: number of days to look back from 'now'
	# resolution: number of minutes to look at individually

	activity = list() # the resulting activity log
	players = set()
	connections = set() # set of active users for this segment
	disconnections = set()
	previous_disconnections = set()

	# Iterate through the past week
	start = datetime.today()
	now = datetime(start.year, start.month, start.day, start.hour) - timedelta(days=history)
	while (now <= start):
		for log in logfile:
			if (log['timestamp'] >= now) and (log['timestamp'] < now + timedelta(minutes=resolution) ):
				# Interpret logfile
				if log['action'] == 'connected':
					connections.add(log['username'])
					players.add(log['username'])
				elif log['action'] == 'disconnected':
					disconnections.add(log['username'])
					players.add(log['username'])

		for item in previous_disconnections:
			connections.discard(item)

		activity.append((now, connections.copy() ) )
		
		previous_disconnections = disconnections.copy()
		disconnections.clear()

		now += timedelta(minutes=resolution)
	# end while date

	# Output data
	datafile = open("graphs/activity_log.dat", "w")
	datafile.write("x_axis")
	for player in sorted(players):
		datafile.write("\t%s" % (player) )
	datafile.write("\n")

	for item in sorted(activity):
		x, y = item

		datafile.write("\"%s\"" % x)

		accumulator = 0 # for a stacked filledcurves plot, we need to accumulate values

		for player in sorted(players):
			if player in y:
				accumulator += 1
				datafile.write("\t%d" % (accumulator) )
			else:
				datafile.write("\t0")

		datafile.write("\n")
	
	datafile.close()

	# Generate graph
	devnull = open("/dev/null", "w")
	subprocess.call(["gnuplot", "graphs/activity_log.gpi"], stderr=devnull, stdout=devnull)
	devnull.close()

	print "<h3>Activity Log</h3>"
	print "<img src=\"activity_log.png\" alt=\"Activtiy Log\" width=\"640px\" height=\"360px\">"
	
	return


def humaniseDays(days):
	if days == 0:
		return "yesterday"
	else:
		return str(days + 1) + " days ago"

def main(*args):
	# Parse argument(s)
	if not (len(args) == 3 + 1):
		print "Usage:", args[0], "[input log-file] [overviewer markers database file] [location threshold in metres]"
		return 1
	
	chatfilename = str(args[1])
	markers_filename = str(args[2])
	location_threshold = float(args[3])

	try:
		chatfile = open(chatfilename, 'r')
	except IOError:
		print "Unable to open file '" + str(args[1]) + "' for reading. Aborted."
		return 1
	
	# Important variables
	logfile = list() # {timestamp, username, action}
	# actions: connected (location), disconnected (None), chat (text)

	# Parse input file into logfile list of dicts
	for line in chatfile:
		# Grab the parts
		try:
			raw_date, raw_time, level, item = line.split(None, 3) # split until 3rd part, then shove remainder in 'item'

		except ValueError:
			pass # line not long enough to bother parsing

		# Convert and verify the date
		raw_datetime = raw_date + " " + raw_time

		try:
			raw_timestamp = datetime.strptime(raw_datetime, "%Y-%m-%d %H:%M:%S")

		except ValueError:
			pass # not a valid timestamp

		# Analyse the actual item
		parts = item.split()
		
		try:
			# Action: chat
			if (parts[0][0] == '<') and (parts[0][-1] == '>'):
				logfile.append({'timestamp': raw_timestamp, 'username': parts[0][1:-1], 'action': 'chat', 'text': item[item.find('> ') + 2:-1] }) # +2 for after '> ', -1 to get rid of newline
			
			# Action: disconnect
			elif (parts[1] == 'lost') and (parts[2] == 'connection:'):
				logfile.append({'timestamp': raw_timestamp, 'username': parts[0], 'action': 'disconnected'})
			
			# Action: connect (old-style)
			elif (parts[1][0] == '[') and (parts[1][-1] == ']') and (parts[2] == 'logged') and (parts[3] == 'in') and (parts[4] == 'with') and (parts[5] == 'entity') and (parts[6] == 'id'):
				logfile.append({'timestamp': raw_timestamp, 'username': parts[0], 'action': 'connected', 'location': [parts[9][1:-1], parts[10][:-1], parts[11][:-1] ] })

			# Action: connect (new-style)
			elif (parts[0][-1] == ']') and (parts[1] == 'logged') and (parts[2] == 'in') and (parts[3] == 'with') and (parts[4] == 'entity') and (parts[5] == 'id'):
				logfile.append({'timestamp': raw_timestamp, 'username': parts[0][0:item.find('[/')], 'action': 'connected', 'location': [parts[8][1:-1], parts[9][:-1], parts[10][:-1] ] })

			# Action: moved_wrongly
			elif (parts[1] == 'moved') and (parts[2] == 'wrongly!'):
				logfile.append({'timestamp': raw_timestamp, 'username': parts[0], 'action': 'moved_wrongly'})

		except IndexError:
			pass # not valid, so ignore

	chatfile.close()

	# Sort the logfile
	sortedlogfile = sorted(logfile, key=lambda item: item['timestamp'])
	
	# Calculate play durations
	play_duration = dict() # {'username': duration}
	play_connected = dict() # {'username': timestamp}

	for log in sortedlogfile: # in ascending order
		if (log['action'] == 'connected'):
			play_connected[log['username']] = log['timestamp']
		elif (log['action'] == 'disconnected'):
			if log['username'] in play_duration:
				play_duration[log['username']] += (log['timestamp'] - play_connected[log['username']])
			else:
				play_duration[log['username']] = (log['timestamp'] - play_connected[log['username']])
				
	# Work out last known co-ordinates and connection time
	last_connected_dict = dict()
	last_location = dict()

	for log in sortedlogfile: # in ascending order
		if (log['action'] == 'connected'):
			last_connected_dict[log['username']] = log['timestamp']
			last_location[log['username']] = log['location']

	# Sort various statistics
	last_connected = sorted(last_connected_dict.iteritems(), key=operator.itemgetter(1), reverse=True)
	play_duration_sorted = sorted(play_duration.iteritems(), key=operator.itemgetter(1), reverse=True)
	
	# Wrong move statistics
	moved_wrongly_counts = dict()
	for log in sortedlogfile:
		if (log['action'] == 'moved_wrongly'):
			if not log['username'] in moved_wrongly_counts:
				moved_wrongly_counts[log['username'] ] = 1
			else:
				moved_wrongly_counts[log['username'] ] += 1
	
	moved_wrongly_sorted_counts = sorted(moved_wrongly_counts.iteritems(), key=operator.itemgetter(1), reverse=True)

	# HTML Output

	print "<h3>Total Time Online</h3>"
	print "<dl id=\"timeonline\">"
	
	top_duration = play_duration_sorted[0][1]
	for player, duration in play_duration_sorted:
		percentage = (duration.total_seconds() / top_duration.total_seconds() ) * 100.0
		print "\t<dt><span class=\"player\">" + str(player) + "</span></dt>"
		print "\t<dd class=\"bar\"><span class=\"barchart\" style=\"width: %.1f%%;\">%.1f%%</span></dd>" % (percentage, percentage)
		print "\t<dd><span class=\"time\">" + str(duration) + "</span></dd>"
	
	print "</dl>"
	print


	print "<h3>Last Time Online</h3>"
	print "<dl id=\"lastplayed\">"

	now = datetime.today()
	for player, connected in last_connected:
		delta = now - connected
		print "\t<dt><span class=\"player\">" + str(player) + "</span></dt>"
		print "\t<dd><span class=\"relativetime\">" + humaniseDays(delta.days) + "</span></dd>"
	
	print "</dl>"
	print

	print "<h3>Previously Connected Near&hellip;</h3>"
	print "<dl id=\"lastplayed\">"

	for player, location in last_location.iteritems():
		print "\t<dt><span class=\"player\">" + str(player) + "</span></dt>"
		print "\t<dd><span class=\"distance\">" + locationName(location, markers_filename, location_threshold) + "</span></dd>"

	print "</dl>"
	print

	print "<h3>Moved Wrongly Counts</h3>"
	print "<dl id=\"lastplayed\">"

	for player, count in moved_wrongly_sorted_counts:
		print "\t<dt><span class=\"player\">" + str(player) + "</span></dt>"
		print "\t<dd><span>" + str(count) + "</span></dd>"

	print "</dl>"
	
	activityLog(sortedlogfile)

	return 0

if (__name__ == "__main__"):
	sys.exit(main(*sys.argv) )
