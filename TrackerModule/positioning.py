from Hologram.HologramCloud import HologramCloud
import time
from mpu6050 import mpu6050
import datetime
import math
import json
import sys
from gps import *
import threading

hardwareID = "DEVICEKEYGOESHERE"
credentials = {'devicekey':hardwareID}
hologram = HologramCloud(credentials, network='cellular')

result = hologram.network.connect()
while result == False:
    print 'Failed to connect to cellular network ... retrying'
    result = hologram.network.connect()

address = 0x68 # I2C of acc/gyro sensor
sendRate = 20     

def dist(a,b):
    return math.sqrt((a*a)+(b*b))

def get_y_rotation(x,y,z):
    radians = math.atan2(x, dist(y,z))
    return -math.degrees(radians)

def get_x_rotation(x,y,z):
    radians = math.atan2(y, dist(x,z))
    return math.degrees(radians)


motion_sensor = mpu6050(address)
motion_sensor.set_accel_range(mpu6050.ACCEL_RANGE_16G)
motion_sensor.set_gyro_range(mpu6050.GYRO_RANGE_2000DEG)

# Magic Numbers
GYRO_SCALE_MODIFIER_2000DEG = 16.4
ACCEL_SCALE_MODIFIER_16G = 2048.0

maxTilt = 0
motd = None

# Thread to check motion values
class MotionPoller(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        global motd
        self.current_value = None
        motd = True
    
    def run(self):
        global motd
        global maxTilt

        offsetx = 0
        offsety = 0
        calibrateCount = 0
        avgCount = 0
        avgxRot = 0
        avgyRot = 0
        while motd:
            sense = motion_sensor.get_all_data()
            GYRx = sense[1]['x'] * GYRO_SCALE_MODIFIER_2000DEG
            GYRy = sense[1]['y'] * GYRO_SCALE_MODIFIER_2000DEG
            GYRz = sense[1]['z'] * GYRO_SCALE_MODIFIER_2000DEG
            ACCx = sense[0]['x'] * ACCEL_SCALE_MODIFIER_16G
            ACCy = sense[0]['y'] * ACCEL_SCALE_MODIFIER_16G
            ACCz = sense[0]['z'] * ACCEL_SCALE_MODIFIER_16G
            TEMP = sense[2]

            # Normalize accelerometer raw values
            accXnorm = (ACCx/math.sqrt(ACCx * ACCx + ACCy * ACCy + ACCz * ACCz))
            accYnorm = (ACCy/math.sqrt(ACCx * ACCx + ACCy * ACCy + ACCz * ACCz))
            accZnorm = (ACCz/math.sqrt(ACCx * ACCx + ACCy * ACCy + ACCz * ACCz))

            # Get rotations
            xRot = get_x_rotation(accXnorm, accYnorm, accZnorm)
            yRot = get_y_rotation(accXnorm, accYnorm, accZnorm)

            # Take the first 100 values and average them for offset
            if calibrateCount < 100:
                calibrateCount+=1
                offsetx += xRot
                offsety += yRot
            elif calibrateCount == 100:
                calibrateCount+=1
                offsetx /= 100
                offsety /= 100
            else:
                # Average 25 datapoints 
                if avgCount < 25:
                    avgxRot += abs(xRot - offsetx)
                    avgyRot += abs(yRot - offsety)
                    avgCount += 1
                else:
                    avgCount = 0
                    avgxRot /= 25
                    avgyRot /= 25
                    # Keep track of the highest tilt experienced so far
                    if avgxRot > maxTilt or avgyRot > maxTilt:
                        maxTilt = max(avgxRot, avgyRot)
                    avgxRot = abs(xRot - offsetx)
                    avgyRot = abs(yRot - offsety)
    
gpsd = None

# Thread to poll GPS
class GpsPoller(threading.Thread):
  def __init__(self):
    threading.Thread.__init__(self)
    global gpsd
    gpsd = gps(mode=WATCH_ENABLE)
    self.current_value = None
    self.running = True
 
  def run(self):
    global gpsd
    while gpsp.running:
      gpsd.next()
                    

if __name__ == '__main__':
    gpsp = GpsPoller()
    motp = MotionPoller()
    try:
        # Start the threads
        gpsp.start()
        motp.start()
        a = datetime.datetime.now()
        print "Starting..."
        while True:
            b = datetime.datetime.now() - a
            if b.total_seconds() >= sendRate:
                gpsData = {}

                # If it can't get a GPS fix or there is no signal
                if gpsd.utc == '' or math.isnan(gpsd.fix.altitude): 
                    # Use cellular modem location data. This is however slow. 
                    modemLocation = hologram.network.location
                    time = modemLocation.time
                    date = modemLocation.date
                    date = date.split('/')
                    date = "-".join(date[::-1])
                    formatedtimedate = date + " " + time
                    lat = modemLocation.latitude
                    long = modemLocation.longitude
                    alt = modemLocation.altitude
                    gpsData = {'devicekey':credentials['devicekey'], 'timestamp':formatedtimedate, 'lat':lat, 'long':long, 'alt':alt, 'tilt':maxTilt, 'has_gps':False}
                else:
                    gpsData = {'devicekey':credentials['devicekey'], 'timestamp':gpsd.utc, 'lat':gpsd.fix.latitude, 'long':gpsd.fix.longitude, 'alt':gpsd.fix.altitude, 'tilt':maxTilt, 'has_gps':True}

                # Send data to Hologram Routers
                response_code = hologram.sendMessage(json.dumps(gpsData),topics=["LOCATION"],timeout=5)
                print 'Hologram Responsee: ' + hologram.getResultString(response_code) 
                a = datetime.datetime.now()
            
    except(KeyboardInterrupt, SystemExit):
        print "\nKilling Threads..."
        gpsp.running = False
        gpsp.join() # wait for the thread to finish what it's doing
        motd = False
        motp.join()
        print "\nDisonnecting from hologram Network..."
        hologram.network.disconnect()
print "Done.\nExiting."
        
    
