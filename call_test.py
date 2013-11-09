import json
import urllib
import time
import raspibrew
import threading
from datetime import datetime,date,timedelta
from datetime import time as dtime

def enum(**enums):
    return type('Enum', (), enums)

BrewState = enum(WaitForHeat=1, WaitForUser=2, WaitForTime=3, WaitForCool=4, WaitForAlarmConfirm=5, WaitForHoldTimeTemp=6,Finished =7, Idle = 8, Boot = 9, Start = 10)

brewState = BrewState.Idle


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



if raspibrew.runAsSimulation == 0:
	speedUp = 1.0
	updateInterval = 1.0
	autoConfirm = 0
	useLCD = 1
else:	
	speedUp = raspibrew.speedUp 
	updateInterval = 2.0
	autoConfirm = 1
	useLCD = 1

if useLCD:
	import pylcd

hoptime = -1.0

temp1 = -100.0
settemp1 = -100.0
remainTime = 0.0
startTime = 0.0
stepTime = 0.0
endTime = 0.0
brewState = BrewState.Boot


def initLCD():
	if useLCD:
		global display
		display = Update()
		display.start()

def printLCD(message):
	display.message(message)

def timeDiffStr(startTime,endTime):
	return str(timedelta(seconds=int((endTime-startTime)*speedUp)))


def fetch_thing(url, params, method):
    params = urllib.urlencode(params)
    if method=='POST':
        f = urllib.urlopen(url, params)
    else:
        f = urllib.urlopen(url+'?'+params)
    return (f.read(), f.code)


def control(num,mode,setpoint,dutycycle,cycletime):
        content, response_code = fetch_thing(
                              'http://localhost:'+ str(8079+num)+ '/',
                              {'mode': mode, 'setpoint': setpoint, 'k': 30, 'i': 810, 'd': 45, 'dutycycle': dutycycle, 'cycletime': cycletime},
                              'POST'
                         )

def Init():
        content, response_code = fetch_thing(
                              'http://localhost:'+ str(8080)+ '/',
                              {'mode': 'off', 'setpoint': 0, 'k': 30, 'i': 810, 'd': 45, 'dutycycle': 0, 'cycletime': 5.0},
                              'POST'
                         )
        content, response_code = fetch_thing(
                              'http://localhost:'+ str(8081)+ '/',
                              {'mode': 'off', 'setpoint': 0, 'k': 30, 'i': 810, 'd': 45, 'dutycycle': 0, 'cycletime': 600.0},
                              'POST'
                         )
	global temp1
	temp1 = getTemp(1)
	global startTime,runTime
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
                              'http://localhost:'+ str(8079+num)+ '/getstatus',
                              {'num': 1},
                              'GET'
                         )
        return  json.loads(content)



def getTemp(num):
        return (float(status(num)['temp'])-32)/1.8

def startAuto(num,temp):
	data = status(num)
	control(num,'auto',temp,0,data['cycle_time'])
	global settemp1
	settemp1 = temp


def WaitForHeat(temp,message):
	global stepTime
	stepTime = time.time()
	global temp1
	startAuto(1,temp)
	print message,", Target Temp: ",temp, "C"
	temp1 = getTemp(1)
	printLCD(message)
	while temp1 < (temp-0.5):
		time.sleep(updateInterval/speedUp)
		temp1 = getTemp(1)
	print "Step Duration: ", timeDiffStr(stepTime,time.time())
	stepTime = 0.0

def WaitForBoilTime(waittime):
	WaitForHeldTempTime(100,waittime,"Boiling")
		
def WaitForHeldTempTime(temp,waittime,message):
	global endTime
	endTime = time.time() + (waittime * 60)/speedUp
	startAuto(1,temp)
	print message," @ ",temp, "C for ",waittime,"min"
	printLCD(message +" " + str(waittime) +"min")
	while time.time() < endTime:
		global temp1
		temp1 = getTemp(1)
		time.sleep(updateInterval/speedUp)
	endTime = 0.0

def WaitForTime(waittime,message):
	global endTime
	endTime = time.time() + (waittime * 60)/speedUp
	print message," for ",waittime,"min"
	printLCD(message+" "+str(waittime)+"min")
	while time.time() < endTime:
		global temp1
		temp1 = getTemp(1)
		time.sleep(updateInterval/speedUp)
	endTime = 0.0

def WaitForUserConfirm(message):
	global stepTime
	stepTime = time.time()
	print message 
	printLCD(message)
	if (autoConfirm == 0):
		print '\a\a\a'
		nb = raw_input('Press Enter to Confirm')
	print "Step Duration: ", timeDiffStr(stepTime,time.time())
	stepTime = 0.0

def StopHeat():
	print "Stopping heater"
	printLCD("Stopping heater")
	data = status(1)
	control(1,'off',0,0,data['cycle_time'])
	global settemp1
	settemp1 = -100

def StopPump():
	print "Stopping Pump"
	printLCD("Stopping Pump")
	data = status(1)
	control(2,'off',0,0,data['cycle_time'])

def ActivatePump():
	printLCD("Starting Pump")
	data = status(1)
	control(2,'manual',0,100,data['cycle_time'])

def StartHopTimer(hoptime):
	global hopTime
	hopTime = time.time() + hoptime*(60.0/speedUp)

def WaitForUserConfirmHop(droptime,message):
	global endTime
	printLCD("Now: Wort Boiling   Next: Hop Drop @"+str(droptime))
	endTime = hopTime - droptime * (60.0/speedUp)
	while time.time() < endTime:
		global temp1
		temp1 = getTemp(1)
		time.sleep(updateInterval/speedUp)
	WaitForUserConfirm("Dropped Hop"+"@" + str(droptime) + "?")	
	print "Dropped Hop @ %.2f" % ((hopTime - time.time())*speedUp/60.0) 


def WaitForHopTimerDone():
	global endTime
	printLCD("Wait for Boil End")
	endTime = hopTime - time.time()
	while time.time() < endTime:
		global temp1
		temp1 = getTemp(1)
		time.sleep(updateInterval/speedUp)

def WaitUntilTime(waitdays,hour,min,message):
	global stepTime
	stepTime = time.time()
	whenStart = datetime.combine(datetime.today() + timedelta(days = waitdays), dtime(hour,min))
	print message + "@" + whenStart.isoformat(' ')
	printLCD(message + "@" + whenStart.isoformat(' '))
	while datetime.now() < whenStart:
		global temp1
		temp1 = getTemp(1)
		time.sleep(updateInterval/speedUp)
	print "Step Duration: ", timeDiffStr(time.time(),stepTime)
	stepTime = 0.0

def ActivatePumpInterval(duty,intervaltime):
	print "Starting Pump in Interval Mode on=",float(intervaltime)*duty/100.0,"min, off=",(100.0-float(duty))/100.0*intervaltime,"min"
	printLCD("Pump Interval on="+str(float(intervaltime)*duty/100.0)+"min, off=" +str((100.0-float(duty))/100.0*intervaltime)+"min")
	control(2,'manual',0,duty,intervaltime*60)


initLCD()

Init()
WaitForUserConfirm('Filled Water?')
#ActivatePump()
#WaitForTime(1,"Now: Pump Init")
#StopPump()
#WaitForTime(1,"Now: Pump Init")
#WaitUntilTime(0,0,1,"Mash In Heating")
ActivatePump()
WaitForHeat(70,'Waiting for Mash In Temp')
StopPump()
WaitForUserConfirm('Mashed in?')
ActivatePumpInterval(90,10)
WaitForHeldTempTime(68,60,'Mash Rest 1')
WaitForHeat(72, 'Heating to Mash Rest 2')
WaitForHeldTempTime(72,10,'Mash Rest 2')
WaitForHeat(76,'Heating to Mash Rest 3')
WaitForHeldTempTime(76,10,'Mash Out Temp')
StopPump()
WaitForHeldTempTime(76,5,'Lauter Settle Wait')
WaitForUserConfirm('Start Mash out!')
WaitForUserConfirm('Confirm Boil Start')
WaitForHeat(100,'Heat to boil temp')
WaitForBoilTime(15)
WaitForUserConfirm('Removed Foam?')
WaitForBoilTime(5)
StartHopTimer(60)
WaitForUserConfirmHop(60,'Hop 60')
WaitForUserConfirmHop(30,'Hop 30')
WaitForUserConfirmHop(15,'Hop 15')
WaitForUserConfirmHop(5,'Hop 5')
WaitForUserConfirmHop(0,'Hop 0')
WaitForHopTimerDone()
StopHeat()
WaitForTime(15,'Cooling')
WaitForUserConfirm('Whirlpool started?')
WaitForTime(15,'Whirlpool Settle Down')
WaitForUserConfirm('Start filling fermenter!')
Done("All done!")
