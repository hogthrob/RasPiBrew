import json
import urllib


def enum(**enums):
    return type('Enum', (), enums)

BrewState = enum(WaitForHeat=1, WaitForUser=2, WaitForTime=3, WaitForCool=4, WaitForAlarmConfirm=5, WaitForHoldTimeTemp)


def fetch_thing(url, params, method):
    params = urllib.urlencode(params)
    if method=='POST':
        f = urllib.urlopen(url, params)
    else:
        f = urllib.urlopen(url+'?'+params)
    return (f.read(), f.code)


def control(mode,setpoint,dutycycle,cycletime):
        content, response_code = fetch_thing(
                              'http://localhost:8080/',
                              {'mode': mode, 'setpoint': setpoint, 'k': 30, 'i': 810, 'd': 45, 'dutycycle': dutycycle, 'cycletime': cycletime},
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
	control('auto',temp,0,data['cycle_time'])


startAuto(1,30)
print getTemp(1)

## WaitForUser('Filled Water?')
# Activate Pump
## WaitForTime
## WaitForHeat(70,'Mash In Temp')
## Stop Pump
## WaitForUser('Mashed in?')
## Start Pump Interval()
## WaitForHelpTempTime(68,60,'Mash Rest 1')
## WaitForHeat(72)
## WaitForHeldTempTime(72,10,'Mash Rest 2')
## WaitForHeat(76)
## WaitForHeldTempTime(76,10,'Mash Out Temp')
## Stop Pump
## WaitForHeldTempTime(76,5,'Lauter Settle Wait')
## WaitForUser('Mash out')
## WaitForUser('Confirm Boil Start')
## WaitForHeat(98)
## WaitForBoilTime(15)
## WaitForUserConfirm('Remove Bruch')
## WaitForBoilTime(5)
## StartHopTimer(60)
## WaitForUserConfirmHop(60,'Hop @60')
## WaitForUserConfirmHop(30,'Hop @30')
## WaitForUserConfirmHop(15'Hop @15')
## WaitForUserConfirmHop(5,'Hop @5')
## WaitForUserConfirmHop('Hop @0')
## WaitForTime(15,'Cooling')
## WaitUser('Whirlpool')
## WaitForTime(15,'Whirlpool Settle Down')
## WaitForUser('Done')
