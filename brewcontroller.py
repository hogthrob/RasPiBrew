import json
import urllib2, urllib
import time, sys
import raspibrew
import threading, csv
from datetime import datetime, date, timedelta
from datetime import time as dtime

global configFile

def loadConfig(configFileArg='config.json'):
    global configFile
    configFile = configFileArg
    with open(configFile) as data_file:
        global config
        config = json.load(data_file)


if len(sys.argv) == 3:
    configFile = sys.argv[2]
else:
    configFile = 'config.json'

loadConfig(configFile)

def enum(**enums):
    return type('Enum', (), enums)

BrewState = enum(WaitForHeat=1, WaitForUser=2, WaitForTime=3, WaitForCool=4, WaitForAlarmConfirm=5, WaitForHoldTimeTemp=6, Finished=7, Idle=8, Boot=9, Start=10)

# # speedUp -> global variable, float, SW Config
speedUp = config['globals']['speedUp']
# indicating simulation speedup
# (how many times faster than real time)
# must be 1.0 for real brewing
# must be same as raspibrew.speedUp in the temp controllers for simulation

# # updateInterval -> global, float
updateInterval = config['globals']['updateInterval']
# time between status and display updates in seconds

# # autoConfirm -> global, boolean, SW Config
autoConfirm = config['globals']['autoConfirm']
# where user confirmation is required, assume confirmation has been given
# Used for simulation and calibration runs
# must be 0/False for real brewing

# # useLCD -> global, boolean, HW Config
useLCD = config['globals']['useLCD']
# use a locally connected LCD to display data&messages

# # useLCD -> global, boolean, HW Config
lcdSimulation = config['globals']['lcdSimulation']
# use a locally connected LCD to display data&messages

# # useTTY -> global, boolean, HW Config
useTTY = config['globals']['useTTY']
# Use a terminal to display data&messages

# # useBeep -> global, boolean, HW Config
useBeep = config['globals']['useBeep']
# Use sound to indicate user interaction

# # confirmHWButtons -> global, boolean, HW config
# use connected RPi HW buttons (GPIO) to read user input
confirmHWButtons = config['globals']['confirmHWButtons']

# # confirmTTYKeyboard -> global, boolean, HW config
# use connected terminal keyboard buttons to read user input
confirmTTYKeyboard = config['globals']['confirmTTYKeyboard']

# # useCirculationPump -> global, boolean, HW Config
useCirculationPump = config['brewSetup']['useCirculationPump']
# control a connected mixer or mixing pump
# if set to False , all commands to Pump&Mixer are ignored

useIPCheck = config['globals']['useIPCheck']

recipeUnit = config['globals']['recipeUnit']
displayUnit = config['globals']['displayUnit']

'''
pidConfig = [{},
              { 'url': 'http://localhost:8080','id': '1', \
                'k': 50, 'i': 400, 'd':0, 'cycletime': 5.0},\
              { 'url': 'http://localhost:8080','id': '2', \
                'k': 0, 'i': 0, 'd': 0, 'cycletime': 6.0}]
'''
#######################################################
# Internal Global Variables
#######################################################
hoptime = -1.0

# temp1 -> global, float, in degree Fahrenheit
temp1 = -100.0
# vessel water temperature
# value of -100.0 is used to indicate that temperature
# is not valid or should not be considered valid

# settemp1 -> global, float, in degree Fahrenheit
settemp1 = -100.0
# vessel water target temperature
# value of -100.0 is used to indicate that temperature
# is not valid or should not be considered valid

# duty_cycle -> global, float, in percent
duty_cycle1 = -100.0
# PWM & PID duty cycle
# value of -100.0 is used to indicate that duty cycle
# is not valid or should not be considered valid

# remainTime -> global, float, in seconds
remainTime = 0.0
# remaining time in execution of a automation step
# if set to zero, step is done or remainTime does make
# sense in this step (i.e. when heating to target temperature)

# # startTime -> global, float, datetime
startTime = 0.0
# this is the time the automation process started and used as reference

# # runTime -> global, float, seconds
runTime = 0.0
# this is the time the automation process has been running
# it stops counting once the automation process is done


# # stepTime -> global, float, seconds
stepTime = 0.0
# # how long is the current step
# if 0.0, stepTime is not set or used

# # endTime -> global, float, datetime
endTime = 0.0
# # when will the current step end
# if 0.0, endTime is not set or used

# # brewState, global, enum
brewState = BrewState.Boot
# indicates the current state of the brewing process

def internalToDisplayTemp(temp):
    if (displayUnit == 'C'):
        return (float(temp) - 32.0) / 1.8
    else:
        return float(temp)

def recipeToInternalTemp(temp):
    if (recipeUnit == 'C'):
        return (float(temp) * 1.8) + 32.0
    else:
        return float(temp)

if useLCD:
    if lcdSimulation == False:
        from pylcd import lcd
        import RPi.GPIO as GPIO
    else:
        from pylcd import lcdSimulation as lcd

class RasPiBrew(threading.Thread):
    def __init__(self, configFile):
        self.configFile = configFile
        threading.Thread.__init__(self)
    def run(self):
        raspibrew.startRasPiBrew(self.configFile, display)

# This thread object controls and continously updates a connected LCD display
class CharLCDUpdate(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.msg = "LCD Ready"
        self.new = 1
        time.sleep(1.0)
        self.lcd = lcd(0x3f, 0, 1)
        time.sleep(1.0)
        self.lcd.clear()
        self.updateLCD()

    def run(self):
        while True:
            self.updateLCD()
            time.sleep(updateInterval)
    def message(self, msg):
        self.msg = msg
        self.new = 1

    def updateLCD(self):
        if self.new:
            self.lcd.clear()
            self.lcd.setCursor(0, 0)
            self.lcd.puts(self.msg)
            self.new = 0
        if temp1 != -100.0:
            self.lcd.setCursor(0, 2)
            self.lcd.puts("T %5.1f" % internalToDisplayTemp(temp1))
        else:
            self.lcd.setCursor(0,2)
            self.lcd.puts('T ---.-')
        if settemp1 != -100.0:

            self.lcd.puts("/%2.0f" % internalToDisplayTemp(settemp1))
        else:
            self.lcd.puts("/--")
        if duty_cycle1 > 0:
            self.lcd.puts(" %3.0f%%" % duty_cycle1)
        else:
            self.lcd.puts(" Off  ")
        self.lcd.setCursor(0, 3)
        if (stepTime > 0):
            runTime = (time.time() - stepTime) * speedUp
        else:
            runTime = 0

        if (endTime > 0 and brewState != BrewState.Finished):
            remainTime = (endTime - time.time()) * speedUp
        else:
            remainTime = 0

        if remainTime > 0:
            self.lcd.puts("R %3d:%02d" % (remainTime / 60, remainTime % 60))
        elif runTime > 0:
            self.lcd.puts("r %3d:%02d" % (runTime / 60, runTime % 60))
        else:
            self.lcd.puts("        ")
        if (brewState != BrewState.Finished and brewState != BrewState.Boot):
            self.lcd.setCursor(10, 3)
            self.lcd.puts(timeDiffStr(startTime, time.time()))
        if (brewState == BrewState.Finished):
            self.lcd.setCursor(10, 3)
            self.lcd.puts(timeDiffStr(startTime, endTime))

# ##
# This class' object is a thread responsible for acquiring sensor and status
# data from the raspibrew controllers regularily
# It also provides logging of the acquired data straight to CSV
# ##

class StatusUpdate(threading.Thread):
    def __init__(self, logEnable=True):
        threading.Thread.__init__(self)
        self.status = [[], [], []]
        self.logEnable = logEnable

        if self.logEnable:
            from collections import OrderedDict
            ordered_fieldnames = OrderedDict([('time', None), ('temp', None), ('mode', None), ('set_point', None), ('dutycycle', None)])
            self.fou = open('log.csv', 'wb')
            self.dw = csv.DictWriter(self.fou, delimiter=',', fieldnames=ordered_fieldnames)
            self.dw.writeheader()

    def run(self):
        global temp1,duty_cycle1
        while True:
            try:
                self.status[1] = status(1)
                self.status[2] = status(2)
            except IOError:
                emergencyExit("No status received")

            temp1 = float(self.status[1]['temp'])
            settemp1 = float(self.status[1]['set_point'])
            duty_cycle1 = float(self.status[1]['duty_cycle'])
            if self.logEnable:
                record = { 'time': time.time() - startTime, 'temp': internalToDisplayTemp(temp1), 'mode': self.status[1]['mode'], 'set_point': self.status[1]['set_point'], 'dutycycle':self.status[1]['duty_cycle'] }
                self.dw.writerow(record)
                self.fou.flush()

            time.sleep(updateInterval / speedUp)


# ##
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
# ##

# TODO: Read button numbers from config, support more buttons (at least 3)

class GPIOButtons(threading.Thread):
    def __init__(self):
        buttonConfig = [{ 'Pin': 21, 'Label': "Green"}, { 'Pin': 22, 'Label': "Blue"}]
        GPIO.setmode(GPIO.BCM)
        threading.Thread.__init__(self)
        self.buttons = []
        for button in buttonConfig:
           self.buttons.append({ 'Pin': button['Pin'], 'Label': button['Label'], 'State': False, 'Pressed': False })
           self.button_setup(button['Pin'])

    def button_setup(self, b):
        GPIO.setup(b, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def button_value(self, b):
        return (GPIO.input(b) == 0)

    def button_check(self, b):
        if self.button_value(b):
            time.sleep(0.02)
            if self.button_value(b):
                return True
        return False


    def run(self):
        while True:
            for button in self.buttons:
                if self.button_check(button['Pin']):
                   if (button['Pressed'] != True):
                    button['Pressed'] = True
            else:
                if button['Pressed']:
                    button['State'] = True
                button['Pressed'] = False
            time.sleep(0.02)

    def button(self, label):
        for button in self.buttons:
            if button['Label'] == label:
                return button['State']
        return False

    def resetButton(self, label):
        for button in self.buttons:
            if button['Label'] == label:
                button['State'] = False
                return True
        return False

import json
from pprint import pprint

def initHardware():
    if True:
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

def timeDiffStr(startTime, endTime):
    return str(timedelta(seconds=int((endTime - startTime) * speedUp)))


# ##
# Connect to remote controllers (at localhost for now)
# ##
def fetch_thing(url, params, method):
    params = urllib.urlencode(params)
    if method == 'POST':
        f = urllib2.urlopen(url, params, timeout=10)
    else:
        f = urllib2.urlopen(url + '?' + params, timeout=10)
    return (f.read(), f.code)

def fetch_controller(num, params):
        return fetch_thing(
                              config['brewSetup']['pidConfig'][num]['url'],
                              params,
                              'POST'
                         )



def control(num, mode, setpoint, dutycycle):
    content, response_code = fetch_controller(
                num,
                              { 'id': config['brewSetup']['pidConfig'][num]['id'],
                                'mode': mode, 'setpoint': setpoint,
                                'k': config['brewSetup']['pidConfig'][num]['k'],
                                'i': config['brewSetup']['pidConfig'][num]['i'],
                                'd': config['brewSetup']['pidConfig'][num]['d'],
                                'dutycycle': dutycycle,
                                'cycletime': config['brewSetup']['pidConfig'][num]['cycletime']}
                         )
    return content, response_code
def status(num):
        content, response_code = fetch_thing(
                              config['brewSetup']['pidConfig'][num]['url'] + '/getstatus',
                              {'id': config['brewSetup']['pidConfig'][num]['id']},
                              'GET'
                         )
        if response_code != 200:
            beep()
            userMessage("Something is wrong when get controller %d status, halting", num)
            InitControllers()
            sys.exit(1)
        return  json.loads(content)

def userMessage(message, shortMessage=""):
    print message
    if shortMessage != "":
        printLCD(shortMessage)
    else:
        printLCD(message)


def getTemp(num):
        return  float(statusUpdate.status[num]['temp'])

def startAuto(num, temp):
    global settemp1
    settemp1 = temp
    data = status(num)
    control(num, 'auto', settemp1, 0)


def beep():
    if useBeep:
        # TODO Replace with "native" beep code
        Popen(["/usr/bin/perl", "pwm.pl"])
if useIPCheck == True:
    from netifaces import interfaces, ifaddresses, AF_INET

def get_ip():
    has_ip = False
    result = "No (W)LAN Address"
    for ifaceName in interfaces():
        addresses = [i['addr'] for i in ifaddresses(ifaceName).setdefault(AF_INET, [{'addr':''}])]
        if has_ip == False and ifaceName != 'lo' and addresses != ['']:
            print addresses
            result = ('(W)LAN OK: %s' % (addresses))
            has_ip = True
    return has_ip, result

from subprocess import Popen, call

def WaitForIP():
    userMessage("Waiting for IP Address")
    result, ipStr = get_ip()
    if result == False:
        time.sleep(20.0)
        result, ipStr = get_ip()
    userMessage(ipStr)
    if result == False:
        if WaitForUserConfirm("No W(LAN) detected  BL: Reboot GN: Continue") == "blue":
            userMessage("Rebooting now...")
            time.sleep(updateInterval * 2)
            Popen(["/sbin/reboot"])
            time.sleep(updateInterval * 2)
            sys.exit(1)


def emergencyExit(message):
            userMessage(message)
            InitControllers()

            if WaitForUserConfirm("Controllers not foundBL: Stop  GN: Reboot") == "Green":
                userMessage("Rebooting now...")
                time.sleep(updateInterval * 2)
                Popen(["/sbin/reboot"])
                sys.exit(1)
            else:
                userMessage("Stopping now...")
                time.sleep(updateInterval * 2)
                sys.exit(1)
def InitControllers():
    numberControllers = config['raspibrew']['numberControllers']
    for idx in range(0, numberControllers):
        content, response_code = control(num=idx + 1, mode='off', setpoint=0, dutycycle=0)

def Init():
    initHardware()
    beep()
    if useIPCheck == True:
        WaitForIP()

    userMessage("Starting controllers...")
    rpbT = RasPiBrew(configFile)
    rpbT.start()
    time.sleep(5.0)
    userMessage("Checking controllers...")
    ok = False
    while ok != True:
        try:
            userMessage("Status 1")
            status(1)
            userMessage("Status 2")
            status(2)
            ok = True
        except IOError:
	    emergencyExit("No controller")
    InitControllers()
    global startTime, runTime
    global statusUpdate

    statusUpdate = StatusUpdate()
    statusUpdate.start()
    startTime = time.time()
    runTime = startTime - startTime
    global brewState
    brewState = BrewState.Start
    userMessage("Ready!")


def Done():
    global brewState, endTime
    brewState = BrewState.Finished
    endTime = time.time()
    if WaitForUserConfirm("All done!           BL: Restart GN : Poweroff") == "green":
        userMessage("Power Off now...")
        time.sleep(updateInterval * 2)
        Popen(["/sbin/poweroff"])
        sys.exit(1)
    else:
        userMessage("Restarting now...")
        time.sleep(updateInterval * 2)



def startStep():
    global stepTime
    stepTime = time.time()

def endStep():
    global stepTime
    userMessage("Step Duration: %s" % timeDiffStr(stepTime, time.time()))
    stepTime = 0.0

def startTimedStep(waittime):
    startStep()
    global endTime
    endTime = time.time() + (waittime * 60) / speedUp

def endTimedStep():
    endTime = 0.0
    endStep()

# This part implements the low level actions
# for heating and pumping, interacting with the user

def WaitForHeat(temp, message):
    startStep()
    startAuto(1, temp)
    userMessage(("%s, Target Temp: %5.1f %s" % (message, internalToDisplayTemp(temp), displayUnit)), message)
    while temp1 < (temp - 1):
        time.sleep(updateInterval / speedUp)
    endStep()

def WaitForBoilTime(waittime):
    WaitForHeldTempTime(212, waittime, "Boiling")

def WaitForHeldTempTime(temp, waittime, message):
    startTimedStep(waittime)
    startAuto(1, temp)
    userMessage("%s @ %5.2f%s for %dmin" % (message, internalToDisplayTemp(temp), displayUnit, waittime), "%s %dmin" % (message, waittime))
    while time.time() < endTime:
        time.sleep(updateInterval / speedUp)
    endTimedStep()

def WaitForTime(waittime, message):
    startTimedStep(waittime)
    userMessage("%s for %dmin" % (message, waittime), "%s %dmin" % (message, waittime))
    while time.time() < endTime:
        time.sleep(updateInterval / speedUp)
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

def StoredStep(name, *arguments, **keywords):
    return {'name': name, 'args': arguments, 'kwargs': keywords}

def StoreStep(name, *arguments, **keywords):
    global steps
    steps.append(StoredStep(name, *arguments, **keywords))

def ExecStep(stepDef):
    print 'Now running: ', stepDef['name']
    globals()[stepDef['name']](*stepDef['args'], **stepDef['kwargs'])

def stepWaitForUserConfirm(*args, **keyw):
    ExecStep(StoredStep("WaitForUserConfirm", *args, **keyw))

def StopHeat():
    startStep()
    userMessage("Stopping heater")
    control(1, 'off', 0, 0)
    global settemp1
    settemp1 = -100
    endStep()

def StopPump():
    startStep()
    userMessage("Stopping Pump")
    control(2, 'off', 0, 0)
    endStep()

def ActivatePump():
    startStep()
    userMessage("Starting Pump")
    control(2, 'manual', 100, 100)
    endStep()

def StartHopTimer(hoptime):
    global hopTime
    hopTime = time.time() + hoptime * (60.0 / speedUp)

def WaitForUserConfirmHop(droptime, message):
    global endTime
    userMessage("Now: Wort Boiling   Next: Hop Drop @" + str(droptime))
    endTime = hopTime - droptime * (60.0 / speedUp)
    while time.time() < endTime:
        time.sleep(updateInterval / speedUp)
    WaitForUserConfirm("Dropped Hop" + "@" + str(droptime) + "?")
    userMessage("Dropped Hop @ %.2f" % ((hopTime - time.time()) * speedUp / 60.0))

def WaitForHopTimerDone():
    global endTime
    userMessage("Wait for Boil End")
    endTime = hopTime - time.time()
    while time.time() < endTime:
        time.sleep(updateInterval / speedUp)

def WaitUntilTime(waitdays, hour, min, message):
    startStep()
    whenStart = datetime.combine(datetime.today() + timedelta(days=waitdays), dtime(hour, min))
    userMessage(message + "@" + whenStart.isoformat(' '))
    while datetime.now() < whenStart:
        time.sleep(updateInterval / speedUp)
    endStep()

def ActivatePumpInterval(duty):
    intervaltime = config['brewSetup']['pidConfig'][2]['cycletime'] / 60.0
    userMessage("Pump Interval on=%.1fmin, off=%.1fmin" % ((float(intervaltime) * duty / 100.0), (100.0 - float(duty)) / 100.0 * intervaltime))
    control(2, 'manual', 0, duty)
    ActivatePump()




# these functions implement the high level brewing process for a given set of
# low level actions for a given hardware setup.
def RunSteps(stepList):
    for step in stepList:
        ExecStep(step)

def DoPreparation():
    StoreStep('WaitForUserConfirm', 'Filled Water?')
    StoreStep('ActivatePump')
    StoreStep('WaitForTime', 1, "Now: Pump Init")
    StoreStep('StopPump')


def DoMashHeating(mashInTemp, wait=False, days=0, hour=0, min=0):
    if wait:
        StoreStep('WaitUntilTime', days, hour, min, "Mash In Heating")
    StoreStep('ActivatePump')
    StoreStep('WaitForHeat', recipeToInternalTemp(mashInTemp), 'Waiting for Mash In Temp')

def DoMashing(steps):
    StoreStep('WaitForUserConfirm', 'Ready to mash?')
    StoreStep('StopPump')
    StoreStep('WaitForUserConfirm', 'Mashed in?')
    StoreStep('ActivatePumpInterval', 90)
    stepNo = 1
    for step in steps:
        StoreStep('WaitForHeat', recipeToInternalTemp(step['temp']), 'Heat for Mash Rest ' + str(stepNo))
        StoreStep('WaitForHeldTempTime', recipeToInternalTemp(step['temp']), step['duration'], 'Mash Rest ' + str(stepNo))
        stepNo = stepNo + 1

def DoLauter(lauterRest):
    StoreStep('WaitForHeldTempTime', 172, lauterRest, 'Lauter Settle Wait')
    StoreStep('WaitForUserConfirm', 'Start Lauter/Sparge!')
    StoreStep('StopPump')
    StoreStep('StopHeat')

def DoWortBoil(hops, boilTime):

    StoreStep('WaitForUserConfirm', 'Confirm Boil Start')
    StoreStep('WaitForHeat', 212, 'Heat to boil temp')
    StoreStep('WaitForBoilTime', 5)
    StoreStep('WaitForUserConfirm', 'Removed Foam?')
    StoreStep('WaitForBoilTime', 1)
    StoreStep('StartHopTimer', boilTime)
    for hop in hops:
        StoreStep('WaitForUserConfirmHop', hop['when'], 'Hop@' + str(hop['when']))
    StoreStep('WaitForHopTimerDone')
    StoreStep('StopHeat')

def DoWhirlpool(settleTime, coolTime):
    StoreStep('WaitForTime', coolTime, 'Cooling')
    StoreStep('WaitForUserConfirm', 'Whirlpool started?')
    StoreStep('WaitForTime', settleTime, 'Whirlpool Settle Down')

def DoFinalize():
    StoreStep('WaitForUserConfirm', 'Start filling fermenter!')

# This is the brew program. Here you will not see setup specific stuff,
# basically this just the brew recipe. Eventually the configuration of
# part should be as simple as reformulating the brew recipe in the form
# of a configuration as shown below.

Recipe = { 'mashInTemp': 70,
           'mashHeatingStartTime': { 'advancedays': 0, 'hour': 0, 'min': 0 },
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


def PrintSteps(steps):
    for step in steps:
        print step['name'], step['args'], step['kwargs']

if __name__ == '__main__':
    steps = []
    Init()
    DoPreparation()
    DoMashHeating(mashInTemp=Recipe['mashInTemp'], wait=True, days=Recipe['mashHeatingStartTime']['advancedays'], hour=Recipe['mashHeatingStartTime']['hour'], min=Recipe['mashHeatingStartTime']['min'])
    DoMashing(Recipe['mashRests'])
    DoLauter(Recipe['lauterRest'])
    DoWortBoil(Recipe['hopAdditions'], boilTime=Recipe['boilTime'])
    DoWhirlpool(coolTime=Recipe['whirlPoolWait']['Before'], settleTime=Recipe['whirlPoolWait']['After'])
    DoFinalize()

    PrintSteps(steps)
    RunSteps(steps)

    Done()
