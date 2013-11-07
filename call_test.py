import json
import urllib
import time
import raspibrew
from datetime import datetime,date,timedelta
from datetime import time as dtime


if raspibrew.runAsSimulation == 0:
	speedUp = 1.0
	updateInterval = 1.0
	autoConfirm = 0
else:	
	speedUp = raspibrew.speedUp 
	updateInterval = 2.0
	autoConfirm = 1

hoptime = -1.0

def enum(**enums):
    return type('Enum', (), enums)

BrewState = enum(WaitForHeat=1, WaitForUser=2, WaitForTime=3, WaitForCool=4, WaitForAlarmConfirm=5, WaitForHoldTimeTemp=6)


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
	print "Ready!"		 


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


def WaitForHeat(temp,message):
	startAuto(1,temp)
	print message," > ",temp, "C"
	while getTemp(1) < (temp-0.5):
		time.sleep(updateInterval/speedUp)

def WaitForBoilTime(waittime):
	WaitForHeldTempTime(100,waittime,"Boiling")
		
def WaitForHeldTempTime(temp,waittime,message):
	tempTime = waittime * 60
	startAuto(1,temp)
	print message," @ ",temp, "C for ",waittime," min"
	while tempTime > 0:
		time.sleep(updateInterval/speedUp)
		tempTime = tempTime - updateInterval 

def WaitForTime(waittime,message):
	tempTime = waittime * 60
	print message," for ",waittime,"min"
	while tempTime > 0:
		time.sleep(updateInterval/speedUp)
		tempTime = tempTime - updateInterval 

def WaitForUserConfirm(message):
	print message 
	if (autoConfirm == 0):
		print '\a\a\a'
		nb = raw_input('Press Enter to Confirm')

def StopHeat():
	print "Stopping heater"
	data = status(1)
	control(1,'off',0,0,data['cycle_time'])

def StopPump():
	print "Stopping Pump"
	data = status(1)
	control(2,'off',0,0,data['cycle_time'])

def ActivatePump():
	print "Starting Pump in Continous Mode"
	data = status(1)
	control(2,'manual',0,100,data['cycle_time'])

def StartHopTimer(hoptime):
	global hopTime
	hopTime = time.time() + hoptime*(60.0/speedUp)

def WaitForUserConfirmHop(droptime,message):
	dropTimeTime = hopTime - droptime * (60.0/speedUp)
	while time.time() < dropTimeTime:
		time.sleep(updateInterval/speedUp)
	WaitForUserConfirm("Drop Hop!"+" @" + str(droptime))	
	print "Dropped Hop @ %.2f" % ((hopTime - time.time())*speedUp/60.0) 


def WaitForHopTimerDone():
	while time.time() < hopTime:
		time.sleep(updateInterval/speedUp)

def WaitUntilTime(waitdays,hour,min,message):
	whenStart = datetime.combine(datetime.today() + timedelta(days = waitdays), dtime(hour,min))
	print message + " @ " + whenStart.isoformat(' ')
	while datetime.now() < whenStart:
		time.sleep(updateInterval)

def ActivatePumpInterval(duty,intervaltime):
	print "Starting Pump in Interval Mode on=",float(intervaltime)*duty/100.0,"min, off=",(100.0-float(duty))/100.0*intervaltime,"min"
	control(2,'manual',0,duty,intervaltime*60)


Init()
WaitForUserConfirm('Filled Water?')
ActivatePump()
WaitForTime(1,"Pump Init")
StopPump()
WaitForTime(1,"Pump Init")
WaitUntilTime(0,21,06,"Waiting for starting time")
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
WaitForUserConfirmHop(60,'Hop @60')
WaitForUserConfirmHop(30,'Hop @30')
WaitForUserConfirmHop(15,'Hop @15')
WaitForUserConfirmHop(5,'Hop @5')
WaitForUserConfirmHop(0,'Hop @0')
WaitForHopTimerDone()
StopHeat()
WaitForTime(15,'Cooling')
WaitForUserConfirm('Whirlpool started?')
WaitForTime(15,'Whirlpool Settle Down')
WaitForUserConfirm('Start filling fermenter!')
