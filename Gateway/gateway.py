from flask import Flask, request, jsonify, render_template
from flask_googlemaps import GoogleMaps
from flask_googlemaps import Map, icons
from datetime import datetime

import sqlite3 as db
import json
import base64
import ast

try:
	trackDB = db.connect("/trackDB.db")
except db.Error as e:
	print("Error %s:" % e.args[0])
	sys.exit(1)

app = Flask(__name__)
googleMapsAPIKey = #GoogleMapsKeyGoesHere#
GoogleMaps(app, key=googleMapsAPIKey)

# In memory dicts of trackers and it's tilt values for less db calls
maxTiltList = {}
currTiltList = {}

# Populate the dicts
with trackDB:
	curr = trackDB.cursor()
	query = "SELECT * FROM trackName"
	curr.execute(query)
	rows = curr.fetchall()
	deviceKeys = []
	if rows == None:
		curr.close()
	else:
		# Gets the user entered max tilt before notification
		for row in rows:
			key = row[0]
			maxVal = row[4]
			deviceKeys.append(key)
			maxTiltList[key] = maxVal

		# Gets the last tilt value
		for device in deviceKeys:
			curr.execute("SELECT TILT FROM gpstrack WHERE DEVICEKEY=? ORDER BY id DESC LIMIT 1;", (device,))
			row = curr.fetchone()[0]
			currTiltList[device] = row
		curr.close()

# returns list of trackers and the user entered information
def getTrackerList():
	trackerlist = []
	with trackDB:
		curr = trackDB.cursor()
		query = "SELECT * FROM trackName"
		curr.execute(query)
		rows = curr.fetchall()
		if rows == None:
			curr.close()
		else:
			for row in rows:
				tmp = {}
				tmp['devicekey'] = row[0]
				tmp['name'] = row[1]
				tmp['description'] = row[2]
				tmp['maxTilt'] = row[4]
				trackerlist.append(tmp)
	return trackerlist

# Returns list of gps points given the devicekey. Earliest first.
def getTrackData(deviceid):
	trackerdata = []
	with trackDB:
		curr = trackDB.cursor()
		query = "SELECT * FROM gpstrack WHERE DEVICEKEY=? ORDER BY ID ASC"
		curr.execute(query, (deviceid,))
		rows = curr.fetchall()
		if rows == None:
			curr.close()
		else:
			for row in rows:
				tmp = {}
				tmp['datetime']=row[2].split('.')[0] + ' UTC'
				tmp['lat'], tmp['long'] = row[3].split(', ')
				tmp['tilt'] = row[4]
				tmp['alt'] = row[5]
				tmp['has_gps'] = row[6]
				trackerdata.append(tmp)
	return trackerdata

# endpoint for logging data. Sent to from hologram data router
@app.route('/device/log', methods=['POST'])
def log():
	content = request.form
	if content['payload'] != None:
		data = content['payload']
		data = ast.literal_eval(data)
		data = data['data']
		data = base64.b64decode(data)
		data = data.replace("'", "\"")
		data = json.loads(data)
		deviceid = data['devicekey']
		time = data['timestamp']
		time = time.split('.')[0]
		time = time.replace('T', ' ')
		time = time.replace('-', ' ')
		timeobj = datetime.strptime(time,'%Y %m %d %H:%M:%S')
		long = data['long']
		lat = data['lat']
		latlong = str(lat) + ', ' + str(long)
		tilt = data['tilt']
		alt = data['alt']
		has_gps = data['has_gps']

		with trackDB:
			curr = trackDB.cursor()
			curr.execute("INSERT INTO gpstrack (DEVICEKEY, TIMESTAMP, LATLONG, TILT, ALT, GPS) VALUES (?, ?, ?, ?, ?, ?)", (deviceid, timeobj, latlong, tilt, alt, has_gps))
			curr.close()

		# While we're here. Check to see if tilt has gone past user setting
		if tilt >= maxTiltList[deviceid]:
			print deviceid + " was tilted past it's maxTilt value."
			#TODO: This would be a great place to call APIs for notifications such as Twillo or any email service
		if tilt > currTiltList[deviceid]:
			currTiltList[deviceid] = tilt

		return "OK"
	else:
		return "Error"

trackerListHTML = '<li><a href="index.html" style="%s"><i class="fa fa-archive fa-fw"></i>%s</a></li>'

# Render webpage
@app.route('/')
@app.route('/<devicekey>')
def hello(devicekey=None):
	trackerlist = ""
	trackers = getTrackerList()
	#Build the sidebar
	for tracker in trackers:
		color = ""
		label = ""
		if currTiltList[tracker['devicekey']] >= maxTiltList[tracker['devicekey']]:
			color = "color:red"
		else:
			color = "color:green"
		label = tracker['name'] + ' - ' + tracker['devicekey'] + '</br> ---- </br>' + tracker['description'] + '</br>' + 'Tilted: ' + str(int(currTiltList[tracker['devicekey']])) + '&#176; - Max Allowed: ' + str(tracker['maxTilt']) + '&#176;'
		trackerlist += '<li><a href="%s" style="%s"><i class="fa fa-archive fa-fw"></i> %s</a></li>' % (tracker['devicekey'], color, label)

	#Build the map
	if devicekey in maxTiltList:
		trackingData = getTrackData(devicekey)
		print trackingData
		lastlat = 0
		lastlng = 0
		pathList = []
		bluemarkers = []
		redmarkers = []
		maxTiltVal = maxTiltList[devicekey]
		for data in trackingData:
			curr = {'lat': float(data['lat']), 'lng': float(data['long'])}
			pathList.append(curr)
			locSource = "Cellular"
			if data['has_gps']:
				locSource = "GPS"
			taginfo = 'Time: ' + data['datetime'] + '</br>' + 'Tilt: ' + str(data['tilt']) + '</br>' + 'Altitude: ' + str(data['alt']) + '</br>' + 'Data Source: ' + locSource
			curr = (float(data['lat']), float(data['long']), taginfo)
			if float(data['tilt']) >= maxTiltVal:
				redmarkers.append(curr)
			else:
				bluemarkers.append(curr)
			lastlat = float(data['lat'])
			lastlng = float(data['long'])
		markersDict = {icons.dots.blue: bluemarkers, icons.dots.red: redmarkers}
		polyline = {
		'stroke_color': '#0AB0DE',
		'stroke_opacity': 1.0,
		'stroke_weight': 3,
		'path': pathList
		}

		plinemap = Map(
			identifier="plinemap",
			varname="plinemap",
			lat=lastlat,
			lng=lastlng,
			polylines=[polyline],
			markers=markersDict,
			style="height:700px;width:1000px;margin:0;"
		)
		nothing = ""
	else:
		plinemap = None
		nothing = "<h1 align='center'>Please select a tracker on the sidebar</h1>"

	return render_template('index.html', plinemap=plinemap, trackerlist=trackerlist, selectsomething=nothing)

# render tracker adding form
@app.route('/add')
def add():
	return render_template('addTracker.html')

# endpoint to add the tracker options into database (called via javascript by Add Tracker form)
@app.route('/onboard', methods=['POST', 'GET'])
def onboard():
	try:
		_devicekey = request.form['inputDevicekey']
		_name = request.form['inputName']
		_description = request.form['inputDescription']
		_notifyemail = request.form['inputEmail']
		_maxtilt = request.form['inputMaxtilt']

		if _devicekey and _name and _notifyemail and _maxtilt:
			with trackDB:
				curr = trackDB.cursor()
				curr.execute("INSERT INTO trackName (DEVICEKEY, NAME, DESCRIPTION, EMAIL, MAXTILT) VALUES (?, ?, ?, ?, ?)", (_devicekey, _name, _description, _notifyemail, _maxtilt))
				curr.close()
			maxTiltList[_devicekey] = _maxtilt
			currTiltList[deviceid] = 0
			return json.dumps({'success':'trackerSucessfully added!'})
		else:
			return json.dumps({'error':'All fields are required!'})
	except Exception as e:
		return json.dumps({'error':str(e)})

# endpoint to remove tracker data from databases
@app.route('/deboard', methods=['POST'])
def deboard():
	_devicekey = request.form['devicekey']
	if _devicekey:
		if _devicekey in maxTiltList: del maxTiltList[_devicekey]
		if _devicekey in currTiltList: del currTiltList[_devicekey]
		with trackDB:
			curr = trackDB.cursor()
			curr.execute("DELETE FROM trackName WHERE DEVICEKEY=?", (_devicekey,))
			curr.execute("DELETE FROM gpstrack WHERE DEVICEKEY=?", (_devicekey,))
			curr.close()
		return json.dumps({'message':'tracker deleted!'})
	else:
		return json.dumps({'html':'<span>Enter the required trackerID</span>'})


if __name__ == '__main__':
	app.run(host='0.0.0.0', port=80)