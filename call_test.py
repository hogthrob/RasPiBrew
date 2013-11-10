import json
import urllib
import time
import raspibrew
import threading,csv
from datetime import datetime,date,timedelta
from datetime import time as dtime
from netifaces import interfaces, ifaddresses, AF_INET

def enum(**enums):
    return type('Enum', (), enums)

BrewState = enum(WaitForHeat=1, WaitForUser=2, WaitForTime=3, WaitForCool=4, WaitForAlarmConfirm=5, WaitForHoldTimeTemp=6,Finished =7, Idle = 8, Boot = 9, Start = 10)



class Update(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self)
		self.msg = "LCD Ready"
		self.new = 1
		time.sleep(1.0)
		self.lcd = pylcd.lcd(0x3f, 0, 1)
		time.sleep(1.0)
		self.lcd.clear()
		self.updateLCD()

	def run(self):
		while True:
			self.updateLCD()
			time.sleep(updateInterval)
	def message(self,msg):
		self.msg = msg
		self.new = 1

	def updateLCD(self):	
		if self.new:
			self.lcd.clear()
			self.lcd.setCursor(0,0)
			self.lcd.puts(self.msg)
			self.new = 0
		if temp1 != -100.0:
			self.lcd.setCursor(0,2)
			self.lcd.puts("Tm %5.1f" % temp1)
		if settemp1 != -100.0:
			self.lcd.setCursor(10,2)
			self.lcd.puts("Ts %5.1f" % settemp1)
		self.lcd.setCursor(0,3)
		if (stepTime > 0):
			runTime = (time.time() - stepTime)*speedUp
		else:
			runTime = 0

		if (endTime > 0 and brewState != BrewState.Finished):
			remainTime = (endTime - time.time())*speedUp
		else:
			remainTime = 0
	
		if runTime > 0:
			self.lcd.puts("r %3d:%02d" % (runTime/60,runTime%60))
		if remainTime > 0:
			self.lcd.puts("R %3d:%02d" % (remainTime/60,remainTime%60))
		else:
			self.lcd.puts("        ")
		if (brewState != BrewState.Finished and brewState != BrewState.Boot):
			self.lcd.setCursor(10,3)
			self.lcd.puts(timeDiffStr(startTime,time.time()))
		if (brewState == BrewState.Finished):
			self.lcd.setCursor(10,3)
			self.lcd.puts(timeDiffStr(startTime,endTime))


## speedUp -> global variable, float, SW Config
speedUp = 1.0
# indicating simulation speedup 
# (how many times faster than real time)
# must be 1.0 for real brewing
# must be same as raspibrew.speedUp in the temp controllers for simulation
 
## updateInterval -> global, float
updateInterval = 1.0
# time between status and display updates in seconds

## autoConfirm -> global, boolean, SW Config
autoConfirm = False
# where user confirmation is required, assume confirmation has been given
# Used for simulation and calibration runs
# must be 0/False for real brewing

## useLCD -> global, boolean, HW Config
useLCD = True
# use a locally connected LCD to display data&messages

## useTTY -> global, boolean, HW Config
useTTY = True
# Use a terminal to display data&messages

 
## confirmHWButtons -> global, boolean, HW config
# use connected RPi HW buttons (GPIO) to read user input
confirmHWButtons = True
 
## confirmTTYKeyboard -> global, boolean, HW config
# use connected terminal keyboard buttons to read user input
confirmTTYKeyboard = True

## usePumpMixer -> global, boolean, HW Config
usePumpMixer = True
# control a connected mixer or mixing pump
# if set to False , all commands to Pump&Mixer are ignored

pidConfig = [{},{ 'url' : 'http://localhost:8080', 'k': 50, 'i': 400, 'd':0, 'cycletime': 5.0},{'url': 'http://localhost:8081', 'k': 0, 'i': 0, 'd': 0, 'cycletime': 600.0}]

#######################################################
# Internal Global Variables
#######################################################
hoptime = -1.0

# temp1 -> global, float, in degree C
temp1 = -100.0
# vessel water temperature
# value of -100.0 is used to indicate that temperature
# is not valid or should not be considered valid

# settemp1 -> global, float, in degree C
settemp1 = -100.0
# vessel water target temperature
# value of -100.0 is used to indicate that temperature
# is not valid or should not be considered valid

# remainTime -> global, float, in seconds
remainTime = 0.0
# remaining time in execution of a automation step
# if set to zero, step is done or remainTime does make
# sense in this step (i.e. when heating to target temperature)

## startTime -> global, float, datetime 
startTime = 0.0
# this is the time the automation process started and used as reference

## runTime -> global, float, seconds 
runTime = 0.0
# this is the time the automation process has been running 
# it stops counting once the automation process is done


## stepTime -> global, float, seconds 
stepTime = 0.0
## how long is the current step 
# if 0.0, stepTime is not set or used 

## endTime -> global, float, datetime 
endTime = 0.0
## when will the current step end
# if 0.0, endTime is not set or used 

## brewState, global, enum
brewState = BrewState.Boot
# indicates the current state of the brewing process

 
if raspibrew.runAsSimulation:
	speedUp = raspibrew.speedUp 
	updateInterval = 2.0
	autoConfirm = False 
	useLCD = True 

if useLCD:
	import pylcd
	import RPi.GPIO as GPIO

### 
# This class' object is a thread responsible for acquiring sensor and status 
# data from the controllers regularily 
# it also provides logging of the acquired data to CSV
###

class StatusUpdate(threading.Thread):
	def __init__(self, logEnable = True):
		threading.Thread.__init__(self)
		self.status = [[],[],[]]
		self.logEnable = logEnable
	
		if self.logEnable:	
			from collections import OrderedDict
			ordered_fieldnames = OrderedDict([('time',None),('temp',None),('mode',None),('set_point',None),('dutycycle',None)])
			self.fou = open('log.csv','wb')
    			self.dw = csv.DictWriter(self.fou, delimiter=',', fieldnames=ordered_fieldnames)
    			self.dw.writeheader()

	def run(self):
		global temp1
		while True:
			self.status[1] = status(1)
			#print self.status[1]
			#self.status[2] = status(2)
			temp1 = (float(self.status[1]['temp'])-32.0)/1.8
			if self.logEnable:
				record = { 'time': time.time() - startTime, 'temp': temp1, 'mode': self.status[1]['mode'], 'set_point': self.status[1]['set_point'],'dutycycle':self.status[1]['dutycycle'] }
				self.dw.writerow(record)
				self.fou.flush()

			time.sleep(updateInterval/speedUp)


###
# This class implements thread which controls the hardware part for 
# reading simple GPIO buttons # from the RPi. Connect button to GPIO 
# Pin and Ground on HW side. 
# Optional: Use 1k resistor in line for added protection of RPi against
# misconfiguration & external issues
# 
# How to use: If waiting for a button press, set the respective button state
# to False, e.g.  buttonThreadVariable.green = False
# Now wait for this variable to become True
#
# 
###

# TODO: Read button numbers from config, support more buttons (at least 3)

class Buttons(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self)
		GPIO.setmode(GPIO.BCM)
		# green -> 21
		# blue -> 22
		self.button_setup(21)
		self.button_setup(22)
		self.blue = False
		self.green = False


	def button_setup(self,b):
		GPIO.setup(b, GPIO.IN, pull_up_down=GPIO.PUD_UP)

	def button_value(self,b):
		return (GPIO.input(b) == 0)

	def button_check(self,b):
		if self.button_value(b):
			time.sleep(0.02)
			if self.button_value(b):
				return 1
		return 0

	
	def run(self):
		b21 = False
		b22 = False
		while True:
			if self.button_check(21):
				if (b21 != True):
					b21 = True
			else:
				if b21:
					self.green = True	
				b21 = False
			if self.button_check(22):
				if (b22 != True):
					b22 = True
			else:
				if b22:
					self.blue = True	
				b22 = False
			time.sleep(0.02)


def initHardware():
	if useLCD:
		global display
		display = Update()
		display.start()
		global buttons
	if confirmHWButtons:
		buttons = Buttons()
		buttons.start()

def printLCD(message):
	display.message(message)

def timeDiffStr(startTime,endTime):
	return str(timedelta(seconds=int((endTime-startTime)*speedUp)))


###
# Connect to remote controllers (at localhost for now)
###
def fetch_thing(url, params, method):
    params = urllib.urlencode(params)
    if method=='POST':
        f = urllib.urlopen(url, params)
    else:
        f = urllib.urlopen(url+'?'+params)
    return (f.read(), f.code)

def fetch_controller(num, params):
        print pidConfig[num]['url']
        return fetch_thing(
                              pidConfig[num]['url'],
                              params,
                              'POST'
                         )



def control(num,mode,setpoint,dutycycle):
        content, response_code = fetch_controller(
				num,
                              {'mode': mode, 'setpoint': setpoint, 'k': pidConfig[num]['k'], 'i': pidConfig[num]['i'], 'd': pidConfig[num]['d'], 'dutycycle': dutycycle, 'cycletime': pidConfig[num]['cycletime']}
                         )
	return content, response_code

def Init():

	ok = False
	while ok != True:
		try:
        		content, response_code = control(num=1,mode='off',setpoint=0,dutycycle=0)
        		content, response_code = control(num=2,mode='off',setpoint=0,dutycycle=0)
			ok = True
		except IOError:
			print "Need to start controllers"
			if WaitForUserConfirm("No Controllers foundBL: Start  GN: Reboot") == "green":
				printLCD("Rebooting now...")
				Popen(["/sbin/reboot"])
			else:
				printLCD("Starting now...")
				call(["bash","start.sh"])
				time.sleep(10.0)
	
	global startTime,runTime
	global statusUpdate 

	statusUpdate = StatusUpdate()
	statusUpdate.start()
	startTime = time.time()
	runTime = startTime - startTime
	global brewState
	brewState = BrewState.Start
	print "Ready!"		 


def Done(message):
	global brewState,endTime
	brewState = BrewState.Finished
	endTime = time.time()
	printLCD("All done!")

def status(num):
        content, response_code = fetch_thing(
                              pidConfig[num]['url'] + '/getstatus',
                              {'num': num},
                              'GET'
                         )
        return  json.loads(content)



def getTemp(num):
        return  (float(statusUpdate.status[num]['temp'])-32.0)/1.8

def startAuto(num,temp):
	data = status(num)
	control(num,'auto',temp,0)
	global settemp1
	settemp1 = temp

def startStep():
	global stepTime
	stepTime = time.time()

def endStep():
	global stepTime
	print "Step Duration: ", timeDiffStr(stepTime,time.time())
	stepTime = 0.0


def WaitForHeat(temp,message):
	startStep()
	startAuto(1,temp)
	print message,", Target Temp: ",temp, "C"
	printLCD(message)
	while temp1 < (temp-0.5):
		time.sleep(updateInterval/speedUp)
	endStep()

def WaitForBoilTime(waittime):
	WaitForHeldTempTime(100,waittime,"Boiling")

def startTimedStep(waittime):
	global endTime
	endTime = time.time() + (waittime * 60)/speedUp

def endTimedStep():
	endTime = 0.0
		
def WaitForHeldTempTime(temp,waittime,message):
	startTimedStep(waittime)
	startAuto(1,temp)
	print message," @ ",temp, "C for ",waittime,"min"
	printLCD(message +" " + str(waittime) +"min")
	while time.time() < endTime:
		time.sleep(updateInterval/speedUp)
	endTimedStep()

def WaitForTime(waittime,message):
	startTimedStep(waittime)
	print message," for ",waittime,"min"
	printLCD(message+" "+str(waittime)+"min")
	while time.time() < endTime:
		time.sleep(updateInterval/speedUp)
	endTimedStep()

def WaitForUserConfirm(message):
	result = ""
	startStep()
	print message 
	printLCD(message)
	if (autoConfirm == False):
		if confirmHWButtons:
			buttons.green = False
			buttons.blue = False
			while (buttons.green == False and  buttons.blue == False):
				time.sleep(0.1) 		
			if buttons.green:
				result = 'green'
			if buttons.blue:
				result = 'blue'
			
		else:
			print '\a\a\a'
			result = raw_input('Press Enter to Confirm')
	endStep()
	return result

def StopHeat():
	startStep()
	print "Stopping heater"
	printLCD("Stopping heater")
	control(1,'off',0,0)
	global settemp1
	settemp1 = -100
	endStep()

def StopPump():
	startStep()
	print "Stopping Pump"
	printLCD("Stopping Pump")
	control(2,'off',0,0)
	endStep()

def ActivatePump():
	startStep()
	printLCD("Starting Pump")
	control(2,'manual',0,100)
	endStep()

def StartHopTimer(hoptime):
	global hopTime
	hopTime = time.time() + hoptime*(60.0/speedUp)

def WaitForUserConfirmHop(droptime,message):
	global endTime
	printLCD("Now: Wort Boiling   Next: Hop Drop @"+str(droptime))
	endTime = hopTime - droptime * (60.0/speedUp)
	while time.time() < endTime:
		time.sleep(updateInterval/speedUp)
	WaitForUserConfirm("Dropped Hop"+"@" + str(droptime) + "?")	
	print "Dropped Hop @ %.2f" % ((hopTime - time.time())*speedUp/60.0) 


def WaitForHopTimerDone():
	global endTime
	printLCD("Wait for Boil End")
	endTime = hopTime - time.time()
	while time.time() < endTime:
		time.sleep(updateInterval/speedUp)

def WaitUntilTime(waitdays,hour,min,message):
	startStep()
	whenStart = datetime.combine(datetime.today() + timedelta(days = waitdays), dtime(hour,min))
	print message + "@" + whenStart.isoformat(' ')
	printLCD(message + "@" + whenStart.isoformat(' '))
	while datetime.now() < whenStart:
		time.sleep(updateInterval/speedUp)
	endStep()

def ActivatePumpInterval(duty):
	print "Starting Pump in Interval Mode on=",float(intervaltime)*duty/100.0,"min, off=",(100.0-float(duty))/100.0*intervaltime,"min"
	printLCD("Pump Interval on="+str(float(intervaltime)*duty/100.0)+"min, off=" +str((100.0-float(duty))/100.0*intervaltime)+"min")
	control(2,'manual',0,duty)





def get_ip():
	has_ip = False
	result = "No (W)LAN Address"
	for ifaceName in interfaces():
    		addresses = [i['addr'] for i in ifaddresses(ifaceName).setdefault(AF_INET, [{'addr':''}] )]
		if has_ip == False and ifaceName != 'lo' and addresses != ['']:
    			print addresses
    			result = ('(W)LAN OK: %s' % (addresses))
			has_ip = True
	return has_ip,result

from subprocess import Popen, PIPE, call
def WaitForIP():
	result,ipStr = get_ip()
	printLCD(ipStr)
	if result == False:
		if WaitForUserConfirm("No W(LAN) detected  BL: Reboot GN: Continue") == "blue":
			Popen(["/sbin/reboot"])
	
initHardware()

Init()
WaitForIP()



WaitForUserConfirm('Filled Water?')
ActivatePump()
WaitForTime(1,"Now: Pump Init")
StopPump()
WaitForTime(1,"Now: Pump Init")
WaitUntilTime(0,0,1,"Mash In Heating")
ActivatePump()
WaitForHeat(70,'Waiting for Mash In Temp')
StopPump()
WaitForUserConfirm('Mashed in?')
ActivatePumpInterval(90,10)
WaitForHeldTempTime(68,60,'Mash Rest 1')
WaitForHeat(72, 'Heating to Mash Rest 2')
WaitForHeldTempTime(72,5,'Mash Rest 2')
WaitForHeat(76,'Heating to Mash Rest 3')
WaitForHeldTempTime(76,5,'Mash Out Temp')
StopPump()
WaitForHeldTempTime(76,1,'Lauter Settle Wait')
WaitForUserConfirm('Start Mash out!')
WaitForUserConfirm('Confirm Boil Start')
WaitForHeat(100,'Heat to boil temp')
WaitForBoilTime(5)
WaitForUserConfirm('Removed Foam?')
WaitForBoilTime(1)
StartHopTimer(6)
WaitForUserConfirmHop(6,'Hop 60')
WaitForUserConfirmHop(3,'Hop 30')
WaitForUserConfirmHop(1.5,'Hop 15')
WaitForUserConfirmHop(.5,'Hop 5')
WaitForUserConfirmHop(0,'Hop 0')
WaitForHopTimerDone()
StopHeat()
WaitForTime(1.5,'Cooling')
WaitForUserConfirm('Whirlpool started?')
WaitForTime(1.5,'Whirlpool Settle Down')
WaitForUserConfirm('Start filling fermenter!')
Done("All done!")
