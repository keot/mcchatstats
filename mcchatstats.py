#!/usr/bin/env python

# MCchatstats - Converts a Minecraft (MSM) chat log-file directory into a JSON
# file full of statistics
# Copyright (c) 2014 James Mardell

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

import sys, math, json, operator, subprocess, gzip, glob, os, os.path, time
from datetime import datetime, timedelta

sys.path.append("nbt")
import nbt
from nbt.nbt import NBTFile

debug = True
gzip_logfile_extension = ".log.gz" # default is ".log.gz"
action_list = list()
player_uuid = dict()

def daterange(start_date, end_date):
	# http://stackoverflow.com/a/1060330
	for n in range(int ((end_date - start_date).days)):
		yield start_date + timedelta(n)

def magnitude(x0, y0, x1, y1):
	return math.sqrt(pow(float(x0) - float(x1), 2) + pow(float(y0) - float(y1), 2))

def locationName(user_location, locations_filename, location_threshold = 512):
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
		distances[location['text'].encode('ascii', 'ignore')] = magnitude(location['x'], location['z'], user_location[0], user_location[2])
	
	nearest = min(distances, key=distances.get)
	
	if distances[nearest] > location_threshold:
		return 'somewhere far away'
	else:
		return '%.1f m away from %s' % (distances[nearest], nearest.replace('\n', ' ').strip() )
	
	return None

def humaniseDays(days):
	if days == 0:
		return "yesterday"
	else:
		return str(days + 1) + " days ago"

def insertLogfileLine(current_date, line):
	p = line.split()
	global action_list
	global player_uuid

	try:
		if (p[4] == "logged"):
			# 0          1       2             3                   4      5  6    7      8  9   10  11 12 13
			# [18:02:40] [Server thread/INFO]: $PLAYER[/$IP:$PORT] logged in with entity id $ID at ($X,$Y,$Z)
			current_timestamp = datetime.strptime(current_date + " " + str(p[0][1:-1]), "%Y-%m-%d %H:%M:%S") # minus '[' and ']'
			player = str(p[3].split('[', 1)[0]) # before '[/ip address]'
			action = "connected"
			x = float(p[11][1:-1]) # minus '(' and ',' 
			y = float(p[12][:-1]) # minus ','
			z = float(p[13][:-1]) # minus ')'
			
			action_list.append({"timestamp": current_timestamp, "player": player, "action": action, "x": x, "y": y, "z": z} )

		elif (p[4] == "lost"):
			current_timestamp = datetime.strptime(current_date + " " + str(p[0][1:-1]), "%Y-%m-%d %H:%M:%S") # minus '[' and ']'
			player = str(p[3].split('[', 1)[0]) # before '[/ip address]'
			action = "disconnected"
			
			action_list.append({"timestamp": current_timestamp, "player": player, "action": action} )

		elif (p[4] == "UUID"):
			# 0          1     2             3          4    5  6      7       8  9
			# [22:33:38] [User Authenticator #63/INFO]: UUID of player $PLAYER is $UUID
			player = str(p[7])
			uuid = str(p[9])
			player_uuid[player] = uuid # assume the most recent is most valid

	except IndexError:
		return 1
	
	return 0

def main(*args):
	global action_list
	output_dict = dict()

	# Parse argument(s)
	try:
		input_directory_name = str(args[1])
		days_history = int(args[2])
		input_locations_name = str(args[3])
		player_dat_directory = str(args[4])

	except IndexError:
		sys.stderr.write("Usage: %s [input directory] [days to look back] [location data] [player .dat directory]\n" % (args[0]) )
		return 1
	
	if player_dat_directory[-1] != "/":
		player_dat_directory += "/"

	output_dict["created_on"] = str(datetime.now().replace(microsecond=0) )
	output_dict["history"] = days_history
	
	start_datetime = datetime.today() - timedelta(days = days_history)
	end_datetime = datetime.today() + timedelta(days = 1)

	# Find and convert logfiles into action_list
	for current_datetime in daterange(start_datetime, end_datetime):
		current_timestamp = time.strftime("%Y-%m-%d", current_datetime.timetuple() )

		for gzip_logfile_name in glob.glob(input_directory_name + "/" + current_timestamp + "-*" + gzip_logfile_extension):
			# Skip directories
			if os.path.isdir(gzip_logfile_name):
				continue

			gzip_logfile_basename = os.path.basename(gzip_logfile_name)[:-len(gzip_logfile_extension)]

			with gzip.open(gzip_logfile_name, "rb") as input_logfile:
				for line in input_logfile:
					insertLogfileLine(current_timestamp, line)
	
	# Find playing durations, last_seen and last_location statistics
	duration = dict()
	last_seen = dict()
	last_location = dict()

	for action in sorted(action_list, key=operator.itemgetter("timestamp") ):
		if (action["action"] == "connected"):
			last_seen[action["player"]] = action["timestamp"]
			last_location[action["player"]] = (action["x"], action["y"], action["z"])

		elif (action["action"] == "disconnected"):
			if (action["player"] in last_seen):
				if (action["player"] in duration):
					duration[action["player"]] += (action["timestamp"] - last_seen[action["player"]])
				else:
					duration[action["player"]] = (action["timestamp"] - last_seen[action["player"]])

			else:
				last_seen[action["player"]] = action["timestamp"]
	
	# Convert to dict ready for JSON serialisation
	players = dict()
	
	for p in duration:
		if p not in players:
			players[p] = dict()
		players[p]["duration"] = str(duration[p])
	
	for p in last_seen:
		if p not in players:
			players[p] = dict()
		players[p]["last_seen"] = str(last_seen[p])
	
	for p in last_location:
		if p not in players:
			players[p] = dict()
		players[p]["last_location"] = locationName(last_location[p], input_locations_name)
	
	# NBT Parsing
	for p in players:
		player_dat = player_dat_directory + player_uuid[p] + ".dat"
		if os.path.isfile(player_dat):
			nbt_player = NBTFile(player_dat)
			players[p]["health"] = int(str(nbt_player["Health"]))   
			players[p]["hunger"] = int(str(nbt_player["foodLevel"]))
			players[p]["level"] = int(str(nbt_player["XpLevel"]))   
			players[p]["score"] = int(str(nbt_player["Score"]))     

	
	output_dict["players"] = players

	print json.dumps(output_dict, ensure_ascii = False, sort_keys = True)

	return 0

if (__name__ == "__main__"):
	sys.exit(main(*sys.argv) )
