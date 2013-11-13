import json
import urllib
import time,sys
import raspibrew
import threading,csv
from datetime import datetime,date,timedelta
from datetime import time as dtime

def enum(**enums):
    return type('Enum', (), enums)

BrewState = enum(WaitForHeat=1, WaitForUser=2, WaitForTime=3, WaitForCool=4, WaitForAlarmConfirm=5, WaitForHoldTimeTemp=6,Finished =7, Idle = 8, Boot = 9, Start = 10)





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

## useBeep -> global, boolean, HW Config
useBeep = True
# Use sound to indicate user interaction 
 
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

pidConfig = [{},
              { 'url': 'http://localhost:8080','id': '1', \
                'k': 50, 'i': 400, 'd':0, 'cycletime': 5.0},\
              { 'url': 'http://localhost:8080','id': '2', \
                'k': 0, 'i': 0, 'd': 0, 'cycletime': 6.0}]

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

pcSimulation = True
 
if raspibrew.runAsSimulation:
    speedUp = raspibrew.speedUp 
    updateInterval = 2.0
    autoConfirm = True 
    if pcSimulation:
        useLCD = False 
        useBeep = False
        confirmHWButtons = False
        autoConfirm = False
		
if useLCD:
	import pylcd
	import RPi.GPIO as GPIO

# This thread object controls and continously updates a connected LCD display 
class CharLCDUpdate(threading.Thread):
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
	
### 
# This class' object is a thread responsible for acquiring sensor and status 
# data from the raspibrew controllers regularily 
# It also provides logging of the acquired data straight to CSV
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
			temp1 = (float(self.status[1]['temp'])-32.0)/1.8
			if self.logEnable:
				record = { 'time': time.time() - startTime, 'temp': temp1, 'mode': self.status[1]['mode'], 'set_point': self.status[1]['set_point'],'dutycycle':self.status[1]['duty_cycle'] }
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
	def __init__(self,buttonConfig = [{ 'Pin': 21, 'Label': "Green"},{ 'Pin': 22, 'Label': "Blue"}]):
		threading.Thread.__init__(self)
		GPIO.setmode(GPIO.BCM)
		# green -> 21
		# blue -> 22
		self.buttons = []
		for button in buttonConfig:
		   self.button_setup(button['Pin'])
		   self.buttons.append({ 'Pin': button['Pin'], 'Label': button['Label'], 'State': False, 'Pressed': False }) 

	def button_setup(self,b):
		GPIO.setup(b, GPIO.IN, pull_up_down=GPIO.PUD_UP)

	def button_value(self,b):
		return (GPIO.input(b) == 0)

	def button_check(self,b):
		if self.button_value(b):
			time.sleep(0.02)
			if self.button_value(b):
				return True
		return False

	
	def run(self):
		while True:
			for button in buttons:
			    if self.button_check(button['Pin']):
				   if (button['Pressed'] != True):
					button['Pressed'] = True
			else:
				if button['Pressed']:
					button['State'] = True	
				button['Pressed'] = False
			time.sleep(0.02)
			
	def button(label):
		for button in buttons:
			if self.button_check(button['Label'] == label):
				return button['State']
		return False
		
	def resetButton(label):
		for button in buttons:
			if self.button_check(button['Label'] == label):
				button['State'] = False
				return True
 		return False		

def initHardware():
    if useLCD:
        global display
        display = CharLCDUpdate()
        display.start()
	    
    if confirmHWButtons:
        global buttons
        buttons = GPIOButtons()
        buttons.start()

def printLCD(message):
    if useLCD:
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
        return fetch_thing(
                              pidConfig[num]['url'],
                              params,
                              'POST'
                         )



def control(num,mode,setpoint,dutycycle):
        content, response_code = fetch_controller(
				num,
                              {'id': pidConfig[num]['id'], 'mode': mode, 'setpoint': setpoint, 'k': pidConfig[num]['k'], 'i': pidConfig[num]['i'], 'd': pidConfig[num]['d'], 'dutycycle': dutycycle, 'cycletime': pidConfig[num]['cycletime']}
                         )
	return content, response_code
def status(num):
        content, response_code = fetch_thing(
                              pidConfig[num]['url'] + '/getstatus',
                              {'id': pidConfig[num]['id']},
                              'GET'
                         )
        return  json.loads(content)

def userMessage(message, shortMessage=""):
    print message
    if shortMessage != "":
        printLCD(shortMessage)
    else:
        printLCD(message)
		

def getTemp(num):
        return  (float(statusUpdate.status[num]['temp'])-32.0)/1.8

def startAuto(num,temp):
	data = status(num)
	control(num,'auto',temp,0)
	global settemp1
	settemp1 = temp
	
def beep():
	if useBeep:
		# TODO Replace with "native" beep code
		Popen(["/usr/bin/perl","pwm.pl"])
if pcSimulation == False:
	from netifaces import interfaces, ifaddresses, AF_INET

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

from subprocess import Popen,call

def WaitForIP():
	userMessage("Waiting for IP Address")
	result,ipStr = get_ip()
	if result == False:
		time.sleep(20.0)
		result, ipStr = get_ip()
	userMessage(ipStr)
	if result == False:
		if WaitForUserConfirm("No W(LAN) detected  BL: Reboot GN: Continue") == "blue":
			userMessage("Rebooting now...")
			time.sleep(updateInterval*2)
			Popen(["/sbin/reboot"])
			time.sleep(updateInterval*2)
			sys.exit(1)
		
def Init():
	initHardware()
	beep()
	if pcSimulation == False:
		WaitForIP()

	ok = False
	while ok != True:
		try:
        		content, response_code = control(num=1,mode='off',setpoint=0,dutycycle=0)
        		content, response_code = control(num=2,mode='off',setpoint=0,dutycycle=0)
			ok = True
		except IOError:
			userMessage("Need to start controllers")
			if WaitForUserConfirm("No Controllers foundBL: Start  GN: Reboot") == "Green":
				userMessage("Rebooting now...")
				time.sleep(updateInterval*2)
				Popen(["/sbin/reboot"])
				sys.exit(1)
			else:
				userMessage("Starting over now...")
				call(["bash","start.sh"])
				time.sleep(updateInterval*2)
	
	global startTime,runTime
	global statusUpdate 

	statusUpdate = StatusUpdate()
	statusUpdate.start()
	startTime = time.time()
	runTime = startTime - startTime
	global brewState
	brewState = BrewState.Start
	userMessage("Ready!")		 


def Done():
	global brewState,endTime
	brewState = BrewState.Finished
	endTime = time.time()
	if WaitForUserConfirm("All done!           BL: Restart GN : Poweroff") == "green":
		userMessage("Power Off now...")
		time.sleep(updateInterval*2)
		Popen(["/sbin/poweroff"])
		sys.exit(1)
	else:
		userMessage("Restarting now...")
		time.sleep(updateInterval*2)



def startStep():
	global stepTime
	stepTime = time.time()

def endStep():
	global stepTime
	userMessage("Step Duration: %s" % timeDiffStr(stepTime,time.time()))
	stepTime = 0.0

def startTimedStep(waittime):
	startStep()
	global endTime
	endTime = time.time() + (waittime * 60)/speedUp

def endTimedStep():
	endTime = 0.0
	endStep()
		
# This part implements the low level actions
# for heating and pumping, interacting with the user

def WaitForHeat(temp,message):
	startStep()
	startAuto(1,temp)
	userMessage(("%s, Target Temp: %5.1f C" % (message,temp)), message)
	while temp1 < (temp-0.5):
		time.sleep(updateInterval/speedUp)
	endStep()

def WaitForBoilTime(waittime):
	WaitForHeldTempTime(100,waittime,"Boiling")

def WaitForHeldTempTime(temp,waittime,message):
	startTimedStep(waittime)
	startAuto(1,temp)
	userMessage("%s @ %5.2fC for %dmin" %(message,temp,waittime),"%s %dmin" %(message,waittime))
	while time.time() < endTime:
		time.sleep(updateInterval/speedUp)
	endTimedStep()

def WaitForTime(waittime,message):
	startTimedStep(waittime)
	userMessage("%s for %dmin" %(message,waittime),"%s %dmin" %(message,waittime))
	while time.time() < endTime:
		time.sleep(updateInterval/speedUp)
	endTimedStep()

def WaitForUserConfirm(message):
	result = ""
	startStep()
	userMessage(message)
	beep()
	if (autoConfirm == False):
		if confirmHWButtons:
			buttons.resetButton('Blue')
			buttons.resetButton('Green')
			while (buttons.button('Green') == False and  buttons.button('Blue') == False):
				time.sleep(0.1) 		
			if buttons.button('Green'):
				result = 'green'
			if buttons.button('Blue'):
				result = 'blue'
			
		else:
			print '\a\a\a'
			result = raw_input('Type B for Blue, G for Green and then Enter to Confirm')
			if (result == 'B'):
			   result = 'blue' 
			if (result == 'G'):
			   result = 'green'   
	endStep()
	return result

def StopHeat():
	startStep()
	userMessage("Stopping heater")
	control(1,'off',0,0)
	global settemp1
	settemp1 = -100
	endStep()

def StopPump():
	startStep()
	userMessage("Stopping Pump")
	control(2,'off',0,0)
	endStep()

def ActivatePump():
	startStep()
	userMessage("Starting Pump")
	control(2,'manual',100,100)
	endStep()

def StartHopTimer(hoptime):
	global hopTime
	hopTime = time.time() + hoptime*(60.0/speedUp)

def WaitForUserConfirmHop(droptime,message):
	global endTime
	userMessage("Now: Wort Boiling   Next: Hop Drop @"+str(droptime))
	endTime = hopTime - droptime * (60.0/speedUp)
	while time.time() < endTime:
		time.sleep(updateInterval/speedUp)
	WaitForUserConfirm("Dropped Hop"+"@" + str(droptime) + "?")	
	userMessage("Dropped Hop @ %.2f" % ((hopTime - time.time())*speedUp/60.0)) 

def WaitForHopTimerDone():
	global endTime
	userMessage("Wait for Boil End")
	endTime = hopTime - time.time()
	while time.time() < endTime:
		time.sleep(updateInterval/speedUp)

def WaitUntilTime(waitdays,hour,min,message):
	startStep()
	whenStart = datetime.combine(datetime.today() + timedelta(days = waitdays), dtime(hour,min))
	userMessage(message + "@" + whenStart.isoformat(' '))
	while datetime.now() < whenStart:
		time.sleep(updateInterval/speedUp)
	endStep()

def ActivatePumpInterval(duty):
	intervaltime = pidConfig[2]['cycletime']/60.0
	userMessage("Pump Interval on=%.1fmin, off=%.1fmin" %((float(intervaltime)*duty/100.0),(100.0-float(duty))/100.0*intervaltime))
	#control(2,'manual',0,duty)
	#TODO FIX ISSUE with blocking PWM change until end of PWM cycletime
	ActivatePump()


# these functions implement the high level brewing process for a given set of
# low level actions for a given hardware setup.

def DoPreparation():
	WaitForUserConfirm('Filled Water?')
	ActivatePump()
	WaitForTime(1,"Now: Pump Init")
	StopPump()

def DoMashHeating(wait = False, days = 0, hour = 0, min = 0, mashInTemp = 70):
	if wait:
		WaitUntilTime(days,hour,min,"Mash In Heating")
	ActivatePump()
	WaitForHeat(mashInTemp,'Waiting for Mash In Temp')

def DoMashing(steps):
	WaitForUserConfirm('Ready to mash?')
	StopPump()
	WaitForUserConfirm('Mashed in?')
	ActivatePumpInterval(90)
	stepNo = 1
	for step in steps:
		WaitForHeat(step['temp'], 'Heat for Mash Rest '+ str(stepNo))
		WaitForHeldTempTime(step['temp'],step['duration'],'Mash Rest '+str(stepNo))
		stepNo = stepNo + 1
	StopPump()
	
def DoLauter(lauterRest):
	WaitForHeldTempTime(78,lauterRest,'Lauter Settle Wait')
	WaitForUserConfirm('Start Lauter/Sparge!')
	
def DoWortBoil(hops, boilTime):

	WaitForUserConfirm('Confirm Boil Start')
	WaitForHeat(100,'Heat to boil temp')
	WaitForBoilTime(5)
	WaitForUserConfirm('Removed Foam?')
	WaitForBoilTime(1)
	StartHopTimer(boilTime)
	for hop in hops:
		WaitForUserConfirmHop(hop['when'],'Hop@'+str(hop['when']))
	WaitForHopTimerDone()
	StopHeat()

def DoWhirlpool(settleTime, coolTime):
	WaitForTime(coolTime,'Cooling')
	WaitForUserConfirm('Whirlpool started?')
	WaitForTime(settleTime,'Whirlpool Settle Down')

def DoFinalize():
	WaitForUserConfirm('Start filling fermenter!')

# This is the brew program. Here you will not see setup specific stuff,
# basically this just the brew recipe. Eventually the configuration of 
# part should be as simple as reformulating the brew recipe in the form
# of a configuration as shown below.

Recipe = { 'mashInTemp': 70,
		   'mashHeatingStartTime': { 'advancedays': 0, 'hours': 0, 'min': 0 }, 
		   'mashRests': [
				{'temp': 68, 'duration': 60 },
				{'temp': 72, 'duration': 10 },
				{'temp': 76, 'duration': 10 }
			],
			'lauterRest': 5,
			'boilTime': 60,
			'hopAdditions': [ 
				{ 'when': 60 },
				{ 'when': 30 },
				{ 'when': 15 },
				{ 'when': 5 },
				{ 'when': 0 }
			],
			'whirlPoolWait': { 'Before': 15, 'After': 15 }
		}
			

Init()
DoPreparation()
DoMashHeating(mashInTemp = Recipe['mashInTemp'])
DoMashing(Recipe['mashRests'])
DoLauter(Recipe['lauterRest'])
DoWortBoil(Recipe['hopAdditions'], boilTime = Recipe['boilTime'])
DoWhirlpool(coolTime = Recipe['whirlPoolWait']['Before'], settleTime = Recipe['whirlPoolWait']['After'])
DoFinalize()

Done()