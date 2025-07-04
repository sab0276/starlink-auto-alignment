import time
import math
import IMU
import datetime
import os
import sys
import configparser


RAD_TO_DEG = 57.29578
M_PI = 3.14159265358979323846
G_GAIN = 0.070  # [deg/s/LSB]  If you change the dps for gyro, you need to update this value accordingly
AA =  0.40	  # Complementary filter constant
lHeading1 = -1
lHeading2 = -1
lHeading3 = -1
lHeading4 = -1


INIFile = "StarlinkAlignment.ini" #NAME OF FILE TO STORE LOCATION SETTINGS BETWEEN USAGE
config = configparser.ConfigParser()
config.read(INIFile)



################# Compass Calibration values ############
# Use calibrateBerryIMU.py to get calibration values
# Calibrating the compass isnt mandatory, however a calibrated
# compass will result in a more accurate heading value.

'''
magXmin = -2708
magYmin = -1172
magZmin = -2092
magXmax = 529
magYmax = 2196
magZmax = 1409
'''



magXmin = -3218
magYmin = -2224
magZmin = -3319
magXmax = 1485
magYmax = 2947
magZmax = -1985

'''
Here is an example:
magXmin =  -1748
magYmin =  -1025
magZmin =  -1876
magXmax =  959
magYmax =  1651
magZmax =  708
Dont use the above values, these are just an example.
'''
############### END Calibration offsets #################


#Kalman filter variables
Q_angle = 0.02
Q_gyro = 0.0015
R_angle = 0.005
y_bias = 0.0
x_bias = 0.0
XP_00 = 0.0
XP_01 = 0.0
XP_10 = 0.0
XP_11 = 0.0
YP_00 = 0.0
YP_01 = 0.0
YP_10 = 0.0
YP_11 = 0.0
KFangleX = 0.0
KFangleY = 0.0



def updateIMUFound(IMUFOUND):
	config['DEFAULT']['imufound'] = str(IMUFOUND)
	with open(INIFile, 'w') as configfile:
		config.write(configfile)
		configfile.close()


def kalmanFilterY ( accAngle, gyroRate, DT):
	y=0.0
	S=0.0

	global KFangleY
	global Q_angle
	global Q_gyro
	global y_bias
	global YP_00
	global YP_01
	global YP_10
	global YP_11

	KFangleY = KFangleY + DT * (gyroRate - y_bias)

	YP_00 = YP_00 + ( - DT * (YP_10 + YP_01) + Q_angle * DT )
	YP_01 = YP_01 + ( - DT * YP_11 )
	YP_10 = YP_10 + ( - DT * YP_11 )
	YP_11 = YP_11 + ( + Q_gyro * DT )

	y = accAngle - KFangleY
	S = YP_00 + R_angle
	K_0 = YP_00 / S
	K_1 = YP_10 / S

	KFangleY = KFangleY + ( K_0 * y )
	y_bias = y_bias + ( K_1 * y )

	YP_00 = YP_00 - ( K_0 * YP_00 )
	YP_01 = YP_01 - ( K_0 * YP_01 )
	YP_10 = YP_10 - ( K_1 * YP_00 )
	YP_11 = YP_11 - ( K_1 * YP_01 )

	return KFangleY

def kalmanFilterX ( accAngle, gyroRate, DT):
	x=0.0
	S=0.0

	global KFangleX
	global Q_angle
	global Q_gyro
	global x_bias
	global XP_00
	global XP_01
	global XP_10
	global XP_11


	KFangleX = KFangleX + DT * (gyroRate - x_bias)

	XP_00 = XP_00 + ( - DT * (XP_10 + XP_01) + Q_angle * DT )
	XP_01 = XP_01 + ( - DT * XP_11 )
	XP_10 = XP_10 + ( - DT * XP_11 )
	XP_11 = XP_11 + ( + Q_gyro * DT )

	x = accAngle - KFangleX
	S = XP_00 + R_angle
	K_0 = XP_00 / S
	K_1 = XP_10 / S

	KFangleX = KFangleX + ( K_0 * x )
	x_bias = x_bias + ( K_1 * x )

	XP_00 = XP_00 - ( K_0 * XP_00 )
	XP_01 = XP_01 - ( K_0 * XP_01 )
	XP_10 = XP_10 - ( K_1 * XP_00 )
	XP_11 = XP_11 - ( K_1 * XP_01 )

	return KFangleX


IMU.detectIMU()	 #Detect if BerryIMU is connected.
if(IMU.BerryIMUversion == 99):
	print(" No BerryIMU found... exiting ")
	IMUFOUND = False
	updateIMUFound(IMUFOUND)
	#manualMode()
	#sys.exit()
else:
	IMU.initIMU()	   #Initialise the accelerometer, gyroscope and compass
	IMUFOUND = True
	updateIMUFound(IMUFOUND)
	gyroXangle = 0.0
	gyroYangle = 0.0
	gyroZangle = 0.0
	CFangleX = 0.0
	CFangleY = 0.0
	kalmanX = 0.0
	kalmanY = 0.0

	a = datetime.datetime.now()


def getHeading():
	global gyroXangle, gyroYangle, gyroZangle, CFangleX, CFangleY, kalmanX,kalmanY
	global magXmin, magYmin, magZmin, magXmax, magYmax, magZmax
	global a

	#Read the accelerometer,gyroscope and magnetometer values
	ACCx = IMU.readACCx()
	ACCy = IMU.readACCy()
	ACCz = IMU.readACCz()
	GYRx = IMU.readGYRx()
	GYRy = IMU.readGYRy()
	GYRz = IMU.readGYRz()
	MAGx = IMU.readMAGx()
	MAGy = IMU.readMAGy()
	MAGz = IMU.readMAGz()


	#Apply compass calibration
	MAGx -= (magXmin + magXmax) /2
	MAGy -= (magYmin + magYmax) /2
	MAGz -= (magZmin + magZmax) /2


	##Calculate loop Period(LP). How long between Gyro Reads
	b = datetime.datetime.now() - a
	a = datetime.datetime.now()
	LP = b.microseconds/(1000000*1.0)
#	outputString = "Loop Time %5.2f " % ( LP )
	outputString = ""


	#Convert Gyro raw to degrees per second
	rate_gyr_x =  GYRx * G_GAIN
	rate_gyr_y =  GYRy * G_GAIN
	rate_gyr_z =  GYRz * G_GAIN


	#Calculate the angles from the gyro.
	gyroXangle+=rate_gyr_x*LP
	gyroYangle+=rate_gyr_y*LP
	gyroZangle+=rate_gyr_z*LP



	#Convert Accelerometer values to degrees
	AccXangle =  (math.atan2(ACCy,ACCz)*RAD_TO_DEG)
	AccYangle =  (math.atan2(ACCz,ACCx)+M_PI)*RAD_TO_DEG

	#convert the values to -180 and +180
	if AccYangle > 90:
		AccYangle -= 270.0
	else:
		AccYangle += 90.0


	#Complementary filter used to combine the accelerometer and gyro values.
	CFangleX=AA*(CFangleX+rate_gyr_x*LP) +(1 - AA) * AccXangle
	CFangleY=AA*(CFangleY+rate_gyr_y*LP) +(1 - AA) * AccYangle

	#Kalman filter used to combine the accelerometer and gyro values.
	kalmanY = kalmanFilterY(AccYangle, rate_gyr_y,LP)
	kalmanX = kalmanFilterX(AccXangle, rate_gyr_x,LP)


	#Calculate heading
	heading = 180 * math.atan2(MAGy,MAGx)/M_PI

	#Only have our heading between 0 and 360
	if heading < 0:
		heading += 360





	####################################################################
	###################Tilt compensated heading#########################
	####################################################################
	#Normalize accelerometer raw values.
	accXnorm = ACCx/math.sqrt(ACCx * ACCx + ACCy * ACCy + ACCz * ACCz)
	accYnorm = ACCy/math.sqrt(ACCx * ACCx + ACCy * ACCy + ACCz * ACCz)


	#Calculate pitch and roll
	pitch = math.asin(accXnorm)
	roll = -math.asin(accYnorm/math.cos(pitch))


	#Calculate the new tilt compensated values
	#The compass and accelerometer are orientated differently on the the BerryIMUv1, v2 and v3.
	#This needs to be taken into consideration when performing the calculations

	#X compensation
	if(IMU.BerryIMUversion == 1 or IMU.BerryIMUversion == 3):			#LSM9DS0 and (LSM6DSL & LIS2MDL)
		magXcomp = MAGx*math.cos(pitch)+MAGz*math.sin(pitch)
	else:																#LSM9DS1
		magXcomp = MAGx*math.cos(pitch)-MAGz*math.sin(pitch)

	#Y compensation
	if(IMU.BerryIMUversion == 1 or IMU.BerryIMUversion == 3):			#LSM9DS0 and (LSM6DSL & LIS2MDL)
		magYcomp = MAGx*math.sin(roll)*math.sin(pitch)+MAGy*math.cos(roll)-MAGz*math.sin(roll)*math.cos(pitch)
	else:																#LSM9DS1
		magYcomp = MAGx*math.sin(roll)*math.sin(pitch)+MAGy*math.cos(roll)+MAGz*math.sin(roll)*math.cos(pitch)




	#Calculate tilt compensated heading
	tiltCompensatedHeading = 180 * math.atan2(magYcomp,magXcomp)/M_PI

	if tiltCompensatedHeading < 0:
		tiltCompensatedHeading += 360


	##################### END Tilt Compensation ########################



	if 1:					   #Change to '0' to stop showing the angles from the accelerometer
		outputString += "#  ACCX Angle %5.2f ACCY Angle %5.2f  #  " % (AccXangle, AccYangle)

	if 1:					   #Change to '0' to stop  showing the angles from the gyro
		outputString +="\t# GRYX Angle %5.2f  GYRY Angle %5.2f  GYRZ Angle %5.2f # " % (gyroXangle,gyroYangle,gyroZangle)

	if 1:					   #Change to '0' to stop  showing the angles from the complementary filter
		outputString +="\t#  CFangleX Angle %5.2f   CFangleY Angle %5.2f  #" % (CFangleX,CFangleY)

	if 1:					   #Change to '0' to stop  showing the heading
		outputString +="\t# HEADING %5.2f  tiltCompensatedHeading %5.2f #" % (heading,tiltCompensatedHeading)

	if 1:					   #Change to '0' to stop  showing the angles from the Kalman filter
		outputString +="# kalmanX %5.2f   kalmanY %5.2f #" % (kalmanX,kalmanY)

	#print (outputString)
	#print("Heading= " + str(int(heading*100)/100) + " ;CompensatedHeading= " + str(int(tiltCompensatedHeading*100)/100))
	#slow program down a bit, makes the output more readable
	return tiltCompensatedHeading

def check360(curHeading, lHeading):
	if (curHeading<=360 and curHeading>=340 and lHeading>=0 and  lHeading<=20):
		return True
	elif (lHeading<=360 and lHeading>=240 and curHeading>=0 and curHeading<=20):
		return True
	else:
		return False

def avgHeading(curHeading):
	global lHeading1, lHeading2, lHeading3, lHeading4
	currHeading = int(curHeading)
	if (lHeading1 == -1 or check360(curHeading, lHeading1)):
		lHeading1 = curHeading
	if (lHeading2 == -1 or check360(curHeading, lHeading2)):
		lHeading2 = lHeading1
	if (lHeading3 == -1 or check360(curHeading, lHeading3)):
		lHeading3 = lHeading2
	if (lHeading4 == -1 or check360(curHeading, lHeading4)):
		lHeading4 = lHeading3

#ToDo: NEED TO TAKE INTO ACCOUNT WHEN ROTATING PAST 0/360

	cHeading = int(((curHeading+lHeading1+lHeading2+lHeading3+lHeading4)/5))
	lHeading4 = lHeading3
	lHeading3 = lHeading2
	lHeading2 = lHeading1
	lHeading1 = curHeading

	return cHeading

def getAvgHeading():
	return avgHeading(getHeading())

'''
while True:
	print (getHeading())
	time.sleep(0.1)
'''
