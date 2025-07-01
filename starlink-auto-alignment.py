#IMPORT NEEDED LIBRARIES
from time import sleep
import RPi.GPIO as GPIO
import berryIMU
import keyboard
import configparser
import StarlinkAPI
from datetime import datetime
import os

#SETUP GPIO BCM PIN NUMBERS
DIR = 13
STEP = 19
ENABLE = 12
LIMIT = 26

GPIO.setmode(GPIO.BCM)
GPIO.setup(DIR, GPIO.OUT) #TELL IT TO ROTATE CCW or CW
GPIO.setup(STEP, GPIO.OUT)
GPIO.setup(ENABLE, GPIO.OUT)
GPIO.setup(LIMIT, GPIO.IN)  #LIMIT SWITCH INPUT PIN


#GLOBAL CONSTANTS
CW = 1
CCW = 0
SPR = 200 # STEPS PER ROTATION.  HOW MANY STEPS THE MOTOR DOES PER ROTATION. CHECK DOCUMENTATION ON MOTOR IF NEEDED.
FASTDELAY = 0.0015 #in seconds
SLOWDELAY = 0.005  #in seconds
STEPX = 2 #MICROSTEP Multiplyer: 1=Fullstep, 2=1/2 step, 4=1/4 step... 32=1/32.  MAKE SURE THIS MATCHES YOUR DIP SWITCH SETTING ON YOUR STEPPER CONTROLLER BOARD.
FSPEED = FASTDELAY*STEPX #FAST SPEED
SSPEED = SLOWDELAY*STEPX #SLOW SPEED
MAXROTATIONS = 24.4 #MAX ROTATIONS TABLE CAN TURN FROM ZERO LIMIT TO MAX LIMIT
MAXSTEPS = MAXROTATIONS*SPR*STEPX #TOTAL NUMBER OF STEPS FROM TABLE AT LIMIT SWITCH (0) TO ROTATE UNTIL OTHER LIMIT IS PHYSICALLY HIT
R360 = 12.25 # MOTOR ROTATIONS IN ORDER TO COMPLETE A FULL 360
RDEGREE = R360/360 #0.0340277 ROTATIONS PER DEGREE
SDEGREE = RDEGREE*SPR*STEPX #13.6111 STEPS PER DEGREE
APITRYAGAIN = 1 #Num Minutes to try again after if Starlink API  failed
STARLINKSSID = "Starlink" #SSID OF YOUR  STARLINK ROUTER
#STARLINKSSID = "SBHome" #Test SSID
MAXDIFFANGLE = 15 # MAX DIFFERENCE IN DEGREES FROM CURRENT TO DESIRED BEFORE STARLINK WILL RE-ALIGN
OFFSET = -75 # USED TO ADJUST COMPASS READING ALIGNMENT

INIFile = "StarlinkAlignment.ini" #NAME OF FILE TO STORE LOCATION SETTINGS BETWEEN USAGE
config = configparser.ConfigParser()
config.read(INIFile)


#GLOBAL VARIABLES
TARGET = 25  #NNE IS OPTIMAL ALIGNMENT ACCORDING TO STARLINK FOR NE LOCATIONS
CURLOC = 0 #CURRENT LOCATION OF MOTOR BASED IN STEPS
DIRECTION = CW
SPEED = FSPEED #SET DEFAULT SPEED OF MOTOR TO FAST
DECLINATION = 0 #DECLINATIONATION MAY CHANGE BASED ON LOCATION
TARGET = TARGET+DECLINATION+OFFSET
travelDirection = 125
satRelDegrees=0
CENTERMOTOR=True
MODE = "MANUAL"  #AUTO, MANUAL, or STARLINKAPI
APIDESIRED = True
APICALLED = datetime.now()
IMUFOUND = True



#FUNCTION DEFINITIONS:
def readINIValues():
	global CURLOC, TARGET, CENTERMOTOR, MODE,  IMUFOUND, OFFSET
	config.read(INIFile)
	CURLOC = config.getint('DEFAULT','curloc',fallback=-1)
	TARGET = config.getfloat('DEFAULT','target',fallback=TARGET)
	CENTERMOTOR = config.getboolean('DEFAULT','centermotor', fallback=True)
	MODE = config.get('DEFAULT','mode',fallback='MANUAL')
	IMUFOUND = config.getboolean('DEFAULT','imufound', fallback=True)
	OFFSET = config.getint('DEFAULT', 'offset', fallback=OFFSET)


def writeLoc(loc): #WRITE THE LOCATION IN STEPS TO FILE FOR LATER RETRIEVAL
	config['DEFAULT']['curloc'] = str(int(loc))
	with open(INIFile, 'w') as configfile:
		config.write(configfile)
		configfile.close()


def updateTarget(target):
	config['DEFAULT']['target'] = str(int(target))
	with open(INIFile, 'w') as configfile:
		config.write(configfile)
		configfile.close()

def updateCENTERMOTOR(centermotor):
	config['DEFAULT']['centermotor'] = str(centermotor)
	with open(INIFile, 'w') as configfile:
		config.write(configfile)
		configfile.close()

def updateMODE(mode):
	config['DEFAULT']['mode'] = str(mode)
	with open(INIFile, 'w') as configfile:
		config.write(configfile)
		configfile.close()


def updateAPICheck():
	global APICALLED
	now = datetime.now()
	APICALLED = now
	config['DEFAULT']['apicheck'] = str(now)
	with open(INIFile, 'w') as configfile:
		config.write(configfile)
		configfile.close()

def updateAPIDesired(APIDESIRED):
	config['DEFAULT']['apidesired'] = str(APIDESIRED)
	with open(INIFile, 'w') as configfile:
		config.write(configfile)
		configfile.close()

def updateOffset():
	global OFFSET
	print ("Old OFFSET is " + str(OFFSET))
	updateDegrees()
	updateAPICheck()
	starlinkCurrent = float(StarlinkAPI.getStarlinkCurrent())
	if (starlinkCurrent < 361):
		OFFSET = OFFSET - int(satHeading - starlinkCurrent)
	print ("New OFFSET is " + str(OFFSET))
	updateStarlinkDegrees()
	config['DEFAULT']['offset'] = str(OFFSET)
	with open(INIFile, 'w') as configfile:
		config.write(configfile)
		configfile.close()


#**************** WiFi CONNECTION FUNCTIONS *****************************
def checkIsWiFiConnected():
	response = os.popen('iwgetid').readline()
	if "wlan" in  response:
		return True
	else:
		return False

def checkWiFiConnected(SSID):
	response = os.popen('iwgetid').readline()
	if SSID in response:
		return True
	else:
		return False

def getWiFiConnectedTo():
	response = os.popen('iwgetid').readline()
	s = response.split(":")[1]
	s = s.replace('"','')
	s=s.strip()
	return s

def getWiFiScan():
	print("Scanning WiFi Networks...")
	response = os.popen('iwlist wlan0 scan |grep -i ESSID')
	for line in response:
		print (line)

def getWiFiSSIDScan(SSID):
	found = False
	print ("Scanning WiFi Networks...")
	response = os.popen('iwlist wlan0 scan |grep -i ESSID')
	for line in response:
		print (line)
		if SSID in  line:
			found =  True
	return found

def reconnectWiFi():
	print ("Trying to reconfigure WiFi...")
	response = os.system("sudo wpa_cli -i wlan0 reconfigure")
	print ("Response= " + str(response))
	if (response == 0):
		print ("Trying to nmcli Connect to Starlink....")
		#os.system("sudo ifdown wlan0")
		os.popen("sudo nmcli dev wifi rescan")
		sleep(5)
		os.popen("sudo nmcli dev wifi list")
		os.popen("sudo nmcli dev wifi connect '" + STARLINKSSID + "'")
		#os.system("sudo ifconfig wlan0 down")
		#os.system("ip link set dev wlan0 down")
		#sleep(7)
		#print("Bringing WiFi back up...")
		#os.system("sudo ifup wlan0")
		#os.system("sudo ifconfig wlan0 up")
	print ("Pi Reconnected!")
	print ("You may need to connect to '" +  STARLINKSSID + "' WiFi and reconnect to Pi.")

def checkStarlinkWiFiConnected():
	StarlinkConnected = False
	WiFiConnected = checkIsWiFiConnected()
	print ("WiFi Connected: " + str(WiFiConnected))
	if (WiFiConnected):
		WiFiSSID = getWiFiConnectedTo()
		print ("WiFi Connected To: " + WiFiSSID)
		StarlinkConnected = checkWiFiConnected(STARLINKSSID)
	print ("WiFi Connected To Starlink: " + str(StarlinkConnected))
	if (not StarlinkConnected):
		#print ("WiFi SSIDs Available: " + str(getWiFiScan()))
		StarlinkAvailable = getWiFiSSIDScan(STARLINKSSID)
		print ("Starlink SSID Available: " + str(StarlinkAvailable))
		if (StarlinkAvailable):
			reconnectWiFi()





#************* MOVE THE MOTOR/SATALITE FUNCTIONS **************************
#BASIC STEPPER MOTOR MOVEMENT FUNCTION
def step_motor(direction, steps, delay):
	global CURLOC
	steps = int(steps*SPR*STEPX)
	GPIO.output(ENABLE, 1)
	GPIO.output(DIR, direction)
	for n in range(steps):
		#print ("CURLOC: " + str(CURLOC) + " , Direction=" + sDir(direction) + ", LimitSwitch=" + str(GPIO.input(LIMIT)))
		if (direction == CW and GPIO.input(LIMIT)): #TEST FOR LIMIT SWITCH.  THIS IS THE 0 STEPS LOCATION.  SATALATILE IS ROTATED ALL THE WAY CW AND PHYSICALLY CANNOT TURN ANY MORE
			GPIO.output(ENABLE, 0)
			print ("RESET HIT AT: " + str(CURLOC) + " , Direction=" + sDir(direction) + ", LimitSwitch=" + str(GPIO.input(LIMIT)))
			CURLOC = 0
			n = steps
			writeLoc(CURLOC)
			break
		#if (n==steps-100):
		#	delay=delay*2
		if (n==steps-50):
			delay=delay*2 #SLOW DOWN WHEN CLODE TO DONE
		if (n==steps-25):
			delay=delay*2

		if (direction==CW and CURLOC < 	abs(degreesToSteps(10))):
			delay=SSPEED #SLOW DOWN IF CLOSE (within 10*) TO LIMIT SWITCH

		GPIO.output(STEP, GPIO.HIGH)
		sleep(delay)
		GPIO.output(STEP, GPIO.LOW)
		if (direction == CW):
			CURLOC -= 1
		if (direction == CCW):
			CURLOC += 1
		if (CURLOC >= MAXSTEPS and direction == CCW): #CHECKS TO SEE IF MOTOR WOULD TURN SATALITE PAST ITS MAX CCW ROTATION WHERE IT WOULD HIT THE OTHER STOP (NO SWITCH) AND NOT BE ABLE TO TURN ANY MORE
			GPIO.output(ENABLE, 0)
			print ("HIT MAX LIMIT  AT: " + str(CURLOC) + ".  Called for "+ str(steps))
			CURLOC = MAXSTEPS
			n=steps
			break
		sleep(delay)
	writeLoc(CURLOC)
	sleep(0.5)
	GPIO.output(ENABLE, 0)


#ROTATE X DEGREES.  DETERMINES BEST WAY TO SAFELY ROTATE TAKING INTO ACCOUNT LIMITS
def rotateDegrees(degrees):
	if (CURLOC == -1):
		centermotor()

	steps = degreesToSteps(degrees)
	print ("***********  ROTATING "  +  str(steps) + " steps (" + str(int(degrees*10)/10) + "*) ******************")
	print ("MaxSteps= " +str(MAXSTEPS))
	print ("Current Steps= " + str(CURLOC) + ", Degrees= " + sDegrees(getCurrentDegrees()) + " rel")
	print ("Requested degree change= " + str(int(degrees*100)/100) + "*")
	print ("Requested steps= " + str(steps))
	newloc = CURLOC+steps
	newDegrees = getDegreesFromSteps(newloc)
	newHeading = heading(newDegrees)
	print ("Cur Steps + Requested Steps=" + str(newloc) + ", would end up at: " + sDegrees(newDegrees)+ " rel" )

	direction = CW
	if (steps+CURLOC>=MAXSTEPS):
		degrees = cleanDegrees(360+degrees)
		steps  = degreesToSteps(degrees)
		#direction = CCW
		print ("MAXSTEPS would be exceeded.  New degree change is " + str(int(degrees*10)/10) + " and new steps is " + str(steps))
	if (CURLOC+steps <= 0):

		degrees=cleanDegrees(360-degrees)*-1
		steps = degreesToSteps(degrees)
		#direction  = CW
		print ("LIMIT SWITCH 0 would be reached. New degree change is " + str(int(degrees*10)/10) + " and new steps is " + str(steps))
	newloc = CURLOC+steps
	if (steps > 0):
		direction = CCW
	if (steps < 0):
		direction = CW
	#moveDegrees = stepsToDegreesRotation(steps)
	newDegrees = getDegreesFromSteps(newloc)

	print ("Move " + str(steps)+  " steps (" + str(int(degrees*10)/10) + "*) " + sDir(direction))
	print ("New CURLOC would be " + str(newloc) + "steps. " + sDegrees(newDegrees) + ") rel" )

	step_motor(direction, stepsToRotations(abs(steps)), SPEED)
	print ("***********  FINISHED ROTATING "  +  str(steps) + " steps (" + str(int(degrees*10)/10) + "*) **********")
	sleep(.2)



def zeromotor(): #BRINGS TABLE TO ZERO LIMIT SWITCH
	print ("***** ZEROING MOTOR *****")
	step_motor(CW, MAXROTATIONS+1, FSPEED/2)
	sleep(1)
	step_motor(CW, 0.2, SSPEED)
	wait(1.5)

def centermotor(): #ZEROS TABLE, THEN ROTATES IT TO CENTER OF USABLE ROTATIONS
	zeromotor()
	wait(1)
	print ("***** CENTERING MOTOR *****")
	step_motor(CCW, MAXROTATIONS/2+0.05, FSPEED/2)
	print ("***** CENTERED *****")
	wait(1)




#********************** UNIT CONVERSIONS *********************
#IN CASE DEGREES IS MORE THAN 360, RETURN ACTUAL DEGREES BETWEEN 0-360
def cleanDegrees(degrees):
	x=1
	if (degrees < 0):
		x=-1
	degrees=(abs(degrees)%360)*x
	return degrees


def getCurrentDegrees(): #GET RELATIVE ALIGNMENT IN DEGREES OF SATALITE FROM THE CURLOC VALUE
	return (360-cleanDegrees(CURLOC/SPR/STEPX/RDEGREE))

def getDegreesFromSteps(steps):  #GETS COMPASS DEGREES FROM STEPS.  DO NOT USE TO CALCULATE CHANGE DEGREES (use stepsToDegreesRotation FCN instead).
	return cleanDegrees((360-cleanDegrees(steps/SPR/STEPX/RDEGREE)))

def degreesToSteps(degrees):
	x=1
	if degrees<0:
		x=-1
	return (int((degrees*RDEGREE*SPR*STEPX)+(0.5*x))*-1)

def degreesToRotations(degrees):
        return (degrees*RDEGREE)

def stepsToDegreesRotation(steps): #USED FOR CALCULATING DEGREES CHANGED FROM STEPS. DO NOT USE TO FIND COMPASS DEGREES (use getDegreesFromSteps FCN instead).
	return cleanDegrees(steps/SPR/STEPX/RDEGREE)

def stepsToRotations(steps):
	return (steps/SPR/STEPX)


#CALCULATE SHORTEST DEGREE CHANGE AND DIRECTION NEEDED TO GET TO DESIRED TARGET.
#SHOULD NEED TO ROTATE LESS THAN 180* IN ORDER TO GET TO DESIRED TARGET.
def calcDegreeDiff(current, target):
	print ("Target Heading= " + sDegrees(target))
	print ("Sat Cur Heading= " + sDegrees(current))

	diff = (current - 360) if current > 180 else current
	diff = target - diff
	if (diff >= 180):
		diff=diff-360
	#return target if target < 180 else target - 360

	print ("Diff Degrees= " + str(int(diff*10)/10) + "*")
	return diff


def calcTravelAlignment(travel, current): #DETERMIS SATALITE'S ACTUAL ALIGNMENT TO EARTH BASED ON TRAVEL DIRECTION AND RELATIVE ALIGNMENT
	print ("-----Calculating Alignments-----")
	print ("MODE: " + MODE + " (APIDESIRED: " + str(APIDESIRED) + ", IMUFOUND: " + str(IMUFOUND) + ")")
	print ("Traveling: " + sDegrees(travel))
	print ("Sat Relative Position = " + sDegrees(current) + " rel")
	actual = cleanDegrees(travel+current)
	#print ("Sat Actual Heading= " + sDegrees(actual))
	return actual



#UPDATES GLOBAL VARIABLES
def updateDegrees():
	global travelDirection, satRelDegrees, satHeading, degreesNeeded
	#UPDATE OUR CURRENT VARIABLES:
	if (IMUFOUND):
		travelDirection = berryIMU.getHeading() + OFFSET + DECLINATION
		if (travelDirection < 0):
			travelDirection = 360 + travelDirection
	satRelDegrees  = getDegreesFromSteps(CURLOC) #SATALITE DISH RELATIVE ORIENTATION TO RV.  FRONT OF RV IS 0/360, REAR IS 180
	satHeading = calcTravelAlignment(travelDirection, satRelDegrees) #SATALITE ACTUAL ORENTATION TO EARTH.
	degreesNeeded = calcDegreeDiff(satHeading, TARGET) #DEGREES NEEDED TO ROTATE DISH IN ORDER TO GET IT TARGET ALIGNMENT.


def updateStarlinkDegrees():
	global degreesNeeded, OFFSET
	APIOK = False
	updateDegrees()
	#UPDATE degreesNeeded from starlinkAPI
	#degreesNeeded = sAPI.getDegrees()
	#If returns good value, set APIOK to True
	updateAPICheck() #UPDATE LAST TIMESTAMP API WAS CHECKED
	diff  = StarlinkAPI.getStarlinkDiff()
	if (diff <181):
		APIOK = True
		degreesNeeded = diff
		print ("Updated degreesNeeded from Starlink API = " +str(degreesNeeded))
	elif (diff == 999):
		print ("* Starlink not fully powered on *")
		checkStarlinkWiFiConnected()
	elif (diff == 920):
		print ("* Starlink still determening orientation *")
	elif (diff == 910):
		print ("* Starlink still aquiring Satalites *")
	return APIOK



#********** STRING FUNCTIONS FOR PRINTING INFO *******************
#get heading string from degrees
def heading(x):
	#x = float(x)
	match x:
		case x if (x>=348.75 or x<11.25):
			return "N"
		case x  if x>=11.25 and x<33.75:
			return "NNE"
		case x if x>=33.75 and x<56.25:
			return "NE"
		case x if x>=56.25 and x<78.75:
			return "ENE"
		case x if x>=78.75 and x<101.25:
			return "E"
		case x if x>=101.25 and x<123.75:
			return "ESE"
		case x if x>=123.75 and x<146.25:
			return "SE"
		case x if x>=146.25 and x<168.75:
			return "SSE"
		case x if x>=168.75 and x<191.25:
			return "S"
		case x if x>=191.25 and x<213.75:
			return "SSW"
		case x if x>=213.75 and x<236.25:
			return "SW"
		case x if x>=236.25 and x<258.75:
			return "WSW"
		case x if x>=258.75 and x<281.25:
			return "W"
		case x if x>=281.25 and x<303.75:
			return "WNW"
		case x if x>=303.75 and x< 326.25:
			return "NW"
		case x if x>=326.25 and x<348.7:
			return "NNW"
		case _:
			return "DNF"

def sDir(dir): #Rotation Direction in String Format
	if (dir==CCW):
		return "CCW"
	if (dir==CW):
		return "CW"

def sDegrees(degrees): #Degrees in a String format
	degrees = float(degrees)
	return (str(int(degrees*100)/100) + "* (" + heading(degrees) + ")")


'''MANUAL MODE WIRELESS KEYBOARD COMMANDS
<-- = Rotate 3* CW LEFT
l-> = Rotate 3* CCW RIGHT
r   = Rotate 1* CCW Right
l   = Rotate 1* CW Left
Enter = Set current Sat Heading as Target Heading
a  = Switch to Auto Compass Mode
s  = Switch to Starlink API Mode
Up = Switch to Starlink API Mode (or Auto Mode if API not returning info)
Down = Switch to Manual Mode
0  = Zero Motor
c  = Center Motor
i  = Initialize Motor (ie,Zero then Center)
e  = Enable Motor to keep satalite in position.  Uses power and motor gets hot.
d  = Disable Motor. May freewheel, but uses less power and keeps motor cool. (better)
w  = Try to reconnect to Starlink WiFi
t  = Get Raspberry Pi Temperaturre in *C
x  = Turns off Zeroing and Centering Motor and starts in Manual Mode on next Restart of Service
p  = Powercycle (ie Reboot) Pi
ESC = Stops StarlinkAutoAlignment Service (this script) and returns to command line
'''


#*************** MODE  FUNCTIONS ***********************
# MANUAL MODE WAITS FOR USERINPUT TO MANUALLY MOVE SATALITE DISH.  CAN TEMPORARILY UPDATE TARGET ALIGNMENT AS WELL AS GO BACK TO AUTO MODE
#USE WIRELESSLY CONNECTED KEYBOARD TO PI
def manualMode():
	global TARGET, SPEED, MODE, APIDESIRED
	MODE = "MANUAL"
	print ("*********MANUAL MODE - WAITING FOR INPUTS*********")
	x=True
	#SPEED = SSPEED
	while(x):

		 #IF THERE WAS ISSUES WITH THE API AND ITS BEEN A X MINUTES SINCE IT WAS LAST CALLED, TRY API MODE AGAIN
		now = datetime.now()
		APITimeAgo = int((now - APICALLED).total_seconds() / 60)
		print ("APITimeAgo = " + str(APITimeAgo))
		if (APIDESIRED and APITimeAgo >= APITRYAGAIN):
			print ("It's been over " + str(APITRYAGAIN) + " minutes. Tring Starlink API Again...")
			x=False
			starlinkAPIMode()

		key = keyboard.read_key()
		print (key)
		if (key == "a"):
			print ("Entering Compass Auto Mode...")
			x = False
			APIDESIRED = False
			updateAPIDesired(APIDESIRED)
			SPEED = FSPEED
			autoMode()
		elif (key == "s" or key == "up"):
			print ("Entering Starlink API Auto Mode...")
			x = False
			APIDESIRED = True
			updateAPIDesired(APIDESIRED)
			starlinkAPIMode()
		elif (key == "left"):
			print ("Rotating LEFT (CW)")
			direction = CW
			SPEED = FSPEED/2
			rotateDegrees(2.5)
			updateDegrees()
			SDEED = FSPEED
			print ("Sat New Heading = " + sDegrees(satHeading))
		elif (key == "l"):
			print ("Rotating Left (CW)")
			SPEED = SSPEED
			direction = CW
			rotateDegrees(1)
			updateDegrees()
			SPEED = FSPEED
			print ("Sat New Heading = " + sDegrees(satHeading))
		elif (key == "right"):
			print ("Rotating RIGHT (CCW)")
			direction = CCW
			SPEED = FSPEED/2
			rotateDegrees(-2.5)
			updateDegrees()
			SPEED = FSPEED
			print ("Sat New Heading = " + sDegrees(satHeading))
		elif (key == "r"):
			print ("Rotating Right (CCW)")
			direction = CCW
			SPEED = SSPEED
			rotateDegrees(-1)
			updateDegrees()
			SPEED = FSPEED
			print ("Sat New Heading = " + sDegrees(satHeading))
		elif (key == "enter"):
			updateDegrees()
			print ("Updating Target Heading to " + sDegrees(satHeading))
			TARGET = satHeading
			updateTarget(TARGET)
		elif (key == "c"):
			centermotor()
		elif (key == "0"):
			zeromotor()
		elif (key == "i"):
			print ("Initializing Motor")
			initializeMotor()
		elif (key == "e"): #ENABLE MOTOR TO HOLD IT IN POSITION. USES POWER AND MOTOR GETS VERY HOT. USE ONLY IF NECESSARY
			GPIO.output(ENABLE, 1)
			print ("Enabling Motor.  This will keep it in place, but will get HOT and uses power!")
		elif (key == "d"): #DISABLE MOTOR.  CAN POSSIBLY FREEWHEEL/ROTATE IF YOU TURN RV FAST ENOUGH OR ITS NOT LEVEL. USES LESS POWER AND KEEPS MOTOR COOL
			GPIO.output(ENABLE, 0)
			print ("Disabling Motor. Uses less power and keeps motor cool. May be able to move freely.")
		elif (key == "w"):
			print ("Checking if connected to Starlink WiFi...")
			checkStarlinkWiFiConnected()
		elif (key == "t"):
			os.system("vcgencmd measure_temp")
		elif (key == "x"):
			#Turn off ZERO AND CENTER MOTOR
			print ("Turning off CENTERING of motor and setting MODE to MANUAL for next power on")
			CENTERMOTOR = False
			updateCENTERMOTOR(CENTERMOTOR)
			updateMODE("MANUAL")
			#x=False
		elif (key == "p"): #Powercycle/Reboot
			sleep(2) #Wait 2 sec to make sure the really mean it
			if (keyboard.is_pressed("p")):
				print ("***** REBOOTING - YOU WILL NEED TO RECONNECT *****")
				cleanupService()
				x=False
				os.system("sudo reboot")
		elif (key == "delete"): #Exit out of script and return to command prompt.  Will have to manually restart service or power cycle.
			sleep(1) #Wait a sec to make sure they really mean it
			if (keyboard.is_pressed("delete")):
				print("***** STOPPING Starlink-Auto-Alignment SERVICE! *****")
				#cleanupService()
				x=False
		elif (key == "esc"): #Restart the service in case of issues.  May want to hit X before so that it doesn't Initialize after restarting.  
			sleep (1) #wait a sec to make sure they really mean it
			if (keyboard.is_pressed("esc")):
				print ("***** RESTARTING Starlink-Auto-Alignment SERVICE! *****")
				cleanupService()
				x=False
				os.system("sudo systemctl restart starlink-auto-alignment")


		#IF THERE WAS ISSUES WITH THE API AND ITS BEEN A X MINUTES SINCE IT WAS LAST CALLED, TRY API MODE AGAIN
		now = datetime.now()
		APITimeAgo = int((now - APICALLED).total_seconds() / 60)
		print ("APITimeAgo = " + str(APITimeAgo))
		if (APIDESIRED and APITimeAgo >= APITRYAGAIN):
			print ("It's been over " + str(APITRYAGAIN) + " minutes. Tring Starlink API Again...")
			x=False
			starlinkAPIMode()

		#step_motor(DIRECTION, ROTATION, SPEED) #TEST THE MOTOR WITHOUT ANY>
		#sleep(1) #SLOW YOUR ROLL! DON'T ASK IT TO CHANGE DIRECTIONS TOO QUICKLY




#AUTOMATICALLY ADJUST SATALITE ALIGNMENT IF IT GETS TOO FAR OUT OF ALIGNENT (ie. WHEN DRIVING)
#HIT M ON WIRELESS CONNECTED KEYBOARD TO GO INTO MANUAL MODE
#HIT S ON WIRELESS CONNECTED KEYBOARD TO GO INTO STARLINK API AUTO ALIGNMENT MODE
#USES COMPASS AND PRESET TARGET HEADING TO KEEP STARLINK ALIGNED.  LESS ACCURATE METHOD.  COMPASS IS NOT SUPER RELIABLE AND TARGET CHANGES WITH LOCATION AND OVER TIME
def autoMode():
	global SPEED, MODE, APIDESIRED
	MODE = "AUTO"
	SPEED = FSPEED
	print ("******************** SWITCHING TO COMPASS AUTO MODE **********************")
	y = True
	while (y):
		if (keyboard.is_pressed("m") or keyboard.is_pressed("down") or keyboard.is_pressed("right") or keyboard.is_pressed("left")):
			print ("Entering Manual Mode...")
			APIDESIRED=False
			updateAPIDesired(APIDESIRED)
			y=False
			manualMode()
		if(keyboard.is_pressed("s") or keyboard.is_pressed("up")):
			print ("Entering Starlink API Mode...")
			y=False
			APIDESIRED = True
			updateAPIDesired(APIDESIRED)
			starlinkAPIMode()
		if (keyboard.is_pressed("a")):
			APIDESIRED = False
			updateAPIDesired(APIDESIRED)
		if (not IMUFOUND):
			print ("Compass IMU not Found!  Switching to Manual Mode")
			y=False
			APIDESIRED = True
			updateAPIDesired(APIDESIRED)
			manualMode()
		updateDegrees()
		if (abs(degreesNeeded)>=MAXDIFFANGLE):
			wait(2)
			updateDegrees()
			if (abs(degreesNeeded)>=MAXDIFFANGLE):
				rotateDegrees(degreesNeeded)
				print ("Waiting 5 secs...")
				wait(4)

		#IF THERE WAS ISSUES WITH THE API AND ITS BEEN A X MINUTES SINCE IT WAS LAST CALLED, TRY API MODE AGAIN
		now = datetime.now()
		APITimeAgo = int((now - APICALLED).total_seconds() / 60)
		print ("APITimeAgo = " + str(APITimeAgo))
		if (APIDESIRED and APITimeAgo >= APITRYAGAIN):
			print ("It's been " + str(APITRYAGAIN) + " minutes. Tring Starlink API Again...")
			y=False
			starlinkAPIMode()
		wait(1)

#USES STARLINK SATALITE API TO GET DESIRED DEGREES NEEDED. MOST ACCURATE METHOD
def starlinkAPIMode():
	global SPEED, MODE, APIDESIRED, TARGET
	MODE = "STARLINKAPI"
	#APIDESIRED = True
	#updateAPIDesired(APIDESIRED)
	SPEED = FSPEED
	print("************ SWITCHING TO STARLINK API AUTO ALIGNMENT MODE ***************")
	z=True
	APIOK = False
	messageSent = False
	i = 0
	while (z):
		if (keyboard.is_pressed("m") or keyboard.is_pressed("down") or keyboard.is_pressed("right") or keyboard.is_pressed("left")):
			print ("Entering Manual Mode...")
			APIDESIRED = False
			updateAPIDesired(APIDESIRED)
			z=False
			i=1
			manualMode()
		if (keyboard.is_pressed("a")):
			print ("Entering Compass Auto Mode...")
			APIDESIRED = False
			updateAPIDesired(APIDESIRED)
			z=False
			i=1
			autoMode()

		if (i%100==0): #CHECK EVERY 10 SECONDS.  This allows time for user to change modes.
			APIOK = updateStarlinkDegrees()
			print ("Can switch to Manual Mode now if needed...")
			messageSent = False
			i=1
		#APIOK = True #FOR TESTING PURPOSES
		if (IMUFOUND and not APIOK):
			print ("*** ISSUE WITH STARLINK API, SWITCHING TO AUTO MODE IN 5 SECS ***")
			APIDESIRED = True
			z=False
			wait(6)
			autoMode()

		if (abs(degreesNeeded)>=MAXDIFFANGLE):
			if (i%20==0):
				if(APIOK):
					APIOK = updateStarlinkDegrees()
					if (abs(degreesNeeded)>=MAXDIFFANGLE):
						rotateDegrees(degreesNeeded)
						#updateDegrees()
						updateOffset()
						print ("Updating Target Heading to " + sDegrees(satHeading))
						TARGET = satHeading
						updateTarget(TARGET)
						print ("Waiting 10 secs...")
						wait(5)
						print ("Still in Starlink Mode, but can switch to Manual Mode now if needed.")
				elif(not IMUFOUND):
					if (not messageSent):
						print ("I think Degrees Needed is: " + sDegrees(degreesNeeded) + " rel.  Starlink API and Compass both not working.  Recommend you switch to Manual Mode.")
						messageSent = True
		sleep(0.1)
		i = i+1

def wait(secs):
	global APIDESIRED
	i=0
	t = True
	while (t):
		if (i>=secs*10):
			t = False
		if (keyboard.is_pressed("right") or keyboard.is_pressed("left") or keyboard.is_pressed("down") or keyboard.is_pressed("m")):
			print ("Entering Manual Mode...")
			APIDESIRED = False
			updateAPIDesired(APIDESIRED)
			i=secs*10
			t = False
			manualMode()
		sleep(0.1)
		i = i+1



def initializeMotor():
	global CENTERMOTOR
	#readLoc()
	print ("CURLOC= " + str(CURLOC) + "steps, " + sDegrees(satRelDegrees) + " rel")
	if (CENTERMOTOR):
		centermotor()
		sleep(0.5)
	print ("********* DETERMNING INITIAL ALIGNMENT FROM PAST DATA1 ************")
	updateDegrees()
	print ("CURLOC= " + str(CURLOC) + "steps, " + sDegrees(satRelDegrees) + " rel")
	print ("TargetHeading= " + str(TARGET) + "* (" + heading(TARGET) + ")")
	print (str(int(cleanDegrees(degreesNeeded)*10)/10) + "* change = " + str(degreesToSteps(degreesNeeded)) + " steps requested")
	print("********* DOING INITIIAL ALIGNMENT FROM PAST DATA2 *************")
	rotateDegrees(degreesNeeded)
	CENTERMOTOR=True
	updateCENTERMOTOR(CENTERMOTOR)
	wait(1)
	checkStarlinkWiFiConnected()
	updateMODE("STARLINKAPI")

def cleanupService():
	writeLoc(CURLOC)
	GPIO.output(ENABLE, 0)
	sleep(1)
	GPIO.cleanup()

def DEBUGMODE():
	CENTERMOTOR = False
	updateCENTERMOTOR(CENTERMOTOR)
	MODE = 'MANUAL'
	updateMODE(MODE)

#OK, LETS GET STARTED!
try:
	#NEED TO:
	#readLoc()
	#centerMotor()
	#sleep(1)
	#updateDegrees()
	#rotateDegrees(degreesNeeded)
	#sleep(1)
	#autoMode
	 # or
	#manualMode()
	#DEBUGMODE()
	readINIValues()
	initializeMotor()

	#INITIALIZE MOTOR
	#readLoc() #LETS GET THE CURRENT LOCATION IN STEPS NOW.  MUST DO THIS TO GET CURLOC. DO THIS FIRST, DON'T COMMENT OUT UNLESS YOU MANUALLY SET CURLOC.
	if (CURLOC == -1):
		centermotor()


	#SHOULD EITHER CENTER MOTOR OR AT LEAST ZERO MOTOR WHEN PI FIRST POWERS ON
	#zeromotor() #ZEROS THE MOTOR FULLY CCW, AKA 0 STEPS
	#centermotor() #ZEROS MOTOR, THEN CENTERS IT SO THAT IT CAN ROTATE A FULL 360 IN EITHER DIRECTION.  CENTERED AT 0 DEGREES RELATIVE TO RV (POINTING TOWARDS FRONT OF RV)

	#ADJUST VARIABLES FOR TESTING. COMMENT OUT WHEN NOT TESTING.
	#degreesNeeded = 90
	#CURLOC = 4000
	#ROTATION = 2
	#DIRECTION = CW
	#TARGET = 330
	#travelDirection =  270
	#MODE=MANUAL #AUTO OR MANUAL VALUES

	#UPDATE OUR VARIABLES INDIVIDUALLY
	#travelDirection = berryIMU.getHeading()
	#satRelDegrees  = getDegreesFromSteps(CURLOC) #SATALITE DISH RELATIVE ORIENTATION TO RV.  FRONT OF RV IS 0 DEGREES, BACK IS 180 DEGREES
	#satHeading = calcTravelAlignment(travelDirection, satRelDegrees) #SATALITE ACTUAL ORENTATION TO EARTH. TAKES INTO ACCOUNT TRAVEL DIRECTION AND RELATIVE ORIENTATION.
	#degreesNeeded = calcDegreeDiff(satHeading, TARGET) #DEGREES NEEDED TO ROTATE DISH IN ORDER TO GET IT TO ACTUAL TARGET ALIGNMENT

	#AUTOMATICALLY UPDATE ALL 4 VARIABLES ABOVE
	#updateDegrees()

	#print ("CURLOC= " + str(CURLOC) + "steps, " + sDegrees(satRelDegrees) + " rel")
	#print ("TargetHeading= " + str(TARGET) + "* (" + heading(TARGET) + ")")
	#print (str(int(cleanDegrees(degreesNeeded)*10)/10) + "* change = " + str(degreesToSteps(degreesNeeded)) + " steps requested")

	#rotateDegrees(degreesNeeded) #ROTATE SATALITE TO TARGET HEADING TAKING INTO ACCOUNT travelDirection

	#step_motor(DIRECTION, ROTATION, SPEED) #TEST THE MOTOR WITHOUT ANY CALCULATIONS.  SET MOTOR ROTATIONS FIRST.
	#sleep(1) #SLOW YOUR ROLL! DON'T ASK IT TO CHANGE DIRECTIONS TOO QUICKLY


	if (MODE == "AUTO"):
		autoMode()
	elif (MODE == "MANUAL"):
		manualMode()
	elif (MODE == "STARLINKAPI"):
		starlinkAPIMode()


except KeyboardInterrupt: # USER HIT CTR+C TO STOP/EXIT PROGRAM
	print("Program interrupted by keyboard")
	GPIO.output(ENABLE, 0)

finally:
	print ("End Loc: " + str(CURLOC) + " steps: " + sDegrees(getDegreesFromSteps(CURLOC)) + " rel")
	print ("End Actaul Alignment = " + sDegrees(calcTravelAlignment(travelDirection, getDegreesFromSteps(CURLOC))))
	print ("Target Alignment was " +sDegrees(TARGET))
	cleanupService()
