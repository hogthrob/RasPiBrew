import json
import urllib
import time

speedUp = 20.0

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
                              'http://localhost:8080/',
                              {'mode': mode, 'setpoint': setpoint, 'k': 30, 'i': 81.0, 'd': 4.5, 'dutycycle': dutycycle, 'cycletime': cycletime},
                              'POST'
                         )

def Init():
        content, response_code = fetch_thing(
                              'http://localhost:8080/',
                              {'mode': 'off', 'setpoint': 0, 'k': 30, 'i': 81.0, 'd': 4.5, 'dutycycle': 0, 'cycletime': 5.0},
                              'POST'
                         )


def status(num):
        content, response_code = fetch_thing(
                              'http://localhost:8080/getstatus',
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
		time.sleep(1.0)

def WaitForBoilTime(waittime):
	WaitForHeldTempTime(100,waittime,"Boiling")
		
def WaitForHeldTempTime(temp,waittime,message):
	tempTime = (waittime * 60)/speedUp
	startAuto(1,temp)
	print message," @ ",temp, "C for ",waittime," min"
	while tempTime > 0:
		time.sleep(1.0)
		tempTime = tempTime - 1

def WaitForTime(waittime,message):
	tempTime = (waittime * 60)/speedUp
	print message," for ",waittime,"min"
	while tempTime > 0:
		time.sleep(1.0)
		tempTime = tempTime - 1

def StopHeat():
	print "Stopping heater"
	data = status(1)
	control(1,'off',0,0,data['cycle_time'])

def StopPump():
	print "Stopping Pump"
	data = status(1)
	# control(2,'off',0,0,data['cycle_time'])

def ActivatePump():
	print "Starting Pump in Continous Mode"
	data = status(1)
	# control(2,'manual',0,100,data['cycle_time'])

def ActivatePumpInterval(duty,intervaltime):
	print "Starting Pump in Interval Mode on=",float(intervaltime)*duty/100.0,"min, off=",(100.0-float(duty))/100.0*intervaltime,"min"
	# control(2,'manual',0,duty,intervaltime*60)


Init()
## WaitForUser('Filled Water?')
ActivatePump()
WaitForTime(1,"Pump Init")
WaitForHeat(70,'Waiting for Mash In Temp')
StopPump()
## WaitForUser('Mashed in?')
ActivatePumpInterval(90,10)
WaitForHeldTempTime(68,60,'Mash Rest 1')
WaitForHeat(72, 'Heating to Mash Rest 2')
WaitForHeldTempTime(72,10,'Mash Rest 2')
WaitForHeat(76,'Heating to Mash Rest 3')
WaitForHeldTempTime(76,10,'Mash Out Temp')
StopPump()
WaitForHeldTempTime(76,5,'Lauter Settle Wait')
## WaitForUser('Mashed out?')
## WaitForUser('Confirm Boil Start')
WaitForHeat(100,'Heat to boil temp')
WaitForBoilTime(15)
## WaitForUserConfirm('Removed Foam?')
WaitForBoilTime(5)
## StartHopTimer(60)
## WaitForUserConfirmHop(60,'Hop @60')
## WaitForUserConfirmHop(30,'Hop @30')
## WaitForUserConfirmHop(15'Hop @15')
## WaitForUserConfirmHop(5,'Hop @5')
## WaitForUserConfirmHop('Hop @0')
StopHeat()
WaitForTime(15,'Cooling')
## WaitUser('Whirlpool')
WaitForTime(15,'Whirlpool Settle Down')
## WaitForUser('Done')
