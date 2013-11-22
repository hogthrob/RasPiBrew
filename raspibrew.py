# Copyright (c) 2012 Stephen P. Smith
# Copyright (c) 2012 Stephen P. Smith
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:

# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR
# IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


config = ''

def loadConfig(configFile='config.json'):
    with open(configFile) as data_file:
        global config
        config = json.load(data_file)

def initGlobalConfig(configFile):
    global useLCD, runAsSimulation, speedUp, runDirPrefix, numberControllers, displayUnit
    loadConfig(configFile)
    useLCD = config['raspibrew']['useLCD']
    numberControllers = config['raspibrew']['numberControllers']
    runDirPrefix = config['raspibrew']['runDirPrefix']
    runAsSimulation = config['globals']['runAsSimulation']
    speedUp = config['globals']['speedUp']
    displayUnit = config['globals']['displayUnit']



from multiprocessing import Process, Pipe, Queue, current_process
import threading
from subprocess import Popen, PIPE, call
from datetime import datetime
import web, time, random, json, serial, os
from pid import pidpy as PIDController
import sys

# Simulated Initial Water Temperature in Degree Celsius
temp_sim = 10.0

'''
# Simulated Room Temperature in Degree Celsius
temp_room_sim = 20.0

# Maximal Heatup of Water in Degree Celsius per Minute
# at Room Temperature when using 100% Power and already warmed up heater
temp_dTHm_sim = 1.5

# Maximal Cooldown of Water in Degree Celsius per Minute
# at measured at Boil Temperature (100 Degree Celsius)
temp_dTCm_sim = 0.78
'''

mpid = 0


def tempValueSave():
        f = open(runDirPrefix + 'run/temp_sim' + str(mpid), 'w')
        f.write(str(temp_sim))
        f.close()

def tempValueRead():
    global temp_sim
    rv = ""
    try:
        f = open(runDirPrefix + 'run/temp_sim' + str(mpid), 'r')
        rv = f.read()
        f.close()
    except:
        1 == 1
    if rv != "":
            temp_sim = float(rv)

# default values used for initialization
class param:
    mode = "off"
    cycle_time = 2.0
    duty_cycle = 0.0
    boil_duty_cycle = 60
    set_point = 0.0
    boil_manage_temp = 200
    num_pnts_smooth = 5
    k_param = 44
    i_param = 165
    d_param = 4


# global hook for communication between web POST and temp control process as well as web GET and temp control process
def add_global_hook(parent_conn, statusQ, numberControllers):

    g = web.storage({"parent_conn" : parent_conn, "statusQ" : statusQ, 'numberControllers': numberControllers})
    def _wrapper(handler):
        web.ctx.globals = g
        return handler()
    return _wrapper


class raspibrew:
    def __init__(self):

        self.mode = param.mode
        self.cycle_time = param.cycle_time
        self.duty_cycle = param.duty_cycle
        self.set_point = param.set_point
        self.boil_manage_temp = param.boil_manage_temp
        self.num_pnts_smooth = param.num_pnts_smooth
        self.k_param = param.k_param
        self.i_param = param.i_param
        self.d_param = param.d_param

    # main web page
    def GET(self):
        id = int(web.input(id=1)['id'])

        return render.raspibrew(self.mode, self.set_point, self.duty_cycle, self.cycle_time, \
                                self.k_param, self.i_param, self.d_param, id, displayUnit)

    # get command from web browser or Android
    def POST(self):
        data = web.data()
        datalist = data.split("&")
        for item in datalist:
            datalistkey = item.split("=")
            if datalistkey[0] == "mode":
                self.mode = datalistkey[1]
            if datalistkey[0] == "setpoint":
                self.set_point = float(datalistkey[1])
            if datalistkey[0] == "dutycycle":  # is boil duty cycle if mode == "boil"
                self.duty_cycle = float(datalistkey[1])
            if datalistkey[0] == "cycletime":
                self.cycle_time = float(datalistkey[1])
            if datalistkey[0] == "boilManageTemp":
                self.boil_manage_temp = float(datalistkey[1])
            if datalistkey[0] == "numPntsSmooth":
                self.num_pnts_smooth = int(datalistkey[1])
            if datalistkey[0] == "k":
                self.k_param = float(datalistkey[1])
            if datalistkey[0] == "i":
                self.i_param = float(datalistkey[1])
            if datalistkey[0] == "d":
                self.d_param = float(datalistkey[1])
            if datalistkey[0] == "id":
                id = int(datalistkey[1])

        # send to main temp control process
        # if did not receive variable key value in POST, the param class default is used
        web.ctx.globals.parent_conn[id - 1].send([self.mode, self.cycle_time, self.duty_cycle, self.set_point, \
                              self.boil_manage_temp, self.num_pnts_smooth, self.k_param, self.i_param, self.d_param])


class getstatus:

    def __init__(self):
        pass

    def GET(self):
        # blocking receive - current status
        id = int(web.input(id=1)['id'])

        temp, elapsed, mode, cycle_time, duty_cycle, set_point, boil_manage_temp, num_pnts_smooth, \
        k_param, i_param, d_param = web.ctx.globals.statusQ[id - 1].get()
        out = json.dumps({"temp" : temp,
                       "elapsed" : elapsed,
                          "mode" : mode,
                    "cycle_time" : cycle_time,
                    "duty_cycle" : duty_cycle,
                     "set_point" : set_point,
              "boil_manage_temp" : boil_manage_temp,
               "num_pnts_smooth" : num_pnts_smooth,
                       "k_param" : k_param,
                       "i_param" : i_param,
                       "d_param" : d_param})
        return out

    def POST(self):
        pass

class getLCD:

    def __init__(self):
        pass

    def GET(self):
	return render.lcd()
	
    def POST(self):
        pass


# Retrieve temperature from simulated temperature sensor


def tempDataSim(tempSensorId):
    tempValueRead()
    return temp_sim

# Retrieve temperature from DS18B20 temperature sensor

def tempData1Wire(tempSensorId):

    with open("/opt/owfs/uncached/" + tempSensorId + "/temperature", 'r') as f:
	result = f.read()
	f.close()
	
    temp_C = float(result)  # temp in Celcius
    return temp_C

# Stand Alone Get Temperature Process
def gettempProc(configFile, num, conn):
    initGlobalConfig(configFile)
    global mpid
    mpid = num

    p = current_process()
    print 'Starting:', p.name, p.pid

    tempSensorId = config['raspibrew']['controller'][num]['sensorId']
    tempSensorType = config['raspibrew']['controller'][num]['sensorType']

    t = time.time()

    while (True):
        time.sleep(0.5 / speedUp)  # .5+~.83 = ~1.33 seconds
        if tempSensorType == "Simulated":
            num = tempDataSim(tempSensorId)
        elif tempSensorType == "1w":
            num = tempData1Wire(tempSensorId)
        else:
            raise Exception("Unknown Sensor Type: " + tempSensorType)

        t1 = time.time()
        elapsed = "%.2f" % ((t1 - t) * speedUp)
        t = t1
        conn.send([num, elapsed])


# Get time heating element is on and off during a set cycle time
def getonofftime(cycle_time, duty_cycle):
    duty = duty_cycle / 100.0
    on_time = cycle_time * (duty)
    off_time = cycle_time * (1.0 - duty)
    return [on_time, off_time]


class SoftPWMBase(threading.Thread):
    def off(self,waitTime):
        self.cycleDuration = self.cycleDuration + self.waitTimeOrChange(waitTime)

    def on(self,waitTime):
        self.cycleDuration = self.cycleDuration + self.waitTimeOrChange(waitTime)

    def initLoopIteration(self):
        self.cycleDuration = 0.0

    def __init__(self,num):
        self.num = num
        self.cycle_time = 1.0
        self.duty_cycle = 0
        self.cycleDuration = 0.0
        threading.Thread.__init__(self)

    def waitTimeOrChange(self, waitTime):
        cycleTime = self.cycle_time
        dutyCycle = self.duty_cycle

        cycleDuration = 0.0
        seconds = int(waitTime) % 1
        subseconds = waitTime - seconds
        for secondStep in range(0,seconds):
            time.sleep(1.0 / speedUp)
            cycleDuration = cycleDuration + 1.0
            if cycleTime != self.cycle_time or dutyCycle != self.duty_cycle:
                print "BREAK ", self.num
                return cycleDuration
        if subseconds:
            time.sleep(subseconds / speedUp)
            cycleDuration = cycleDuration + subseconds
        return cycleDuration

    def run(self):
        self.cycleDuration = 0.0
        while (True):
            self.initLoopIteration()

            if self.duty_cycle == 0:
                self.off(self.cycle_time)
            elif self.duty_cycle == 100:
                self.on(self.cycle_time)
            else:
                on_time, off_time = getonofftime(self.cycle_time, self.duty_cycle)
                self.on(on_time)
                self.off(off_time)

class SoftPWMSiumulation(SoftPWMBase):

    def on(self, waitTime):
        global temp_sim
        if self.num == 2:
            print "ON ", self.num
        SoftPWMBase.on(self, waitTime)
        temp_sim = temp_sim + self.temp_dTHm_sim * (self.cycleDuration / 60)
    def off(self, waitTime):
        if self.num == 2:
            print "OFF ", self.num
        SoftPWMBase.on(self, waitTime)

    def init(self):
        global temp_sim

        self.temp_dTCm_sim = config['raspibrew']['controller'][self.num]['dTCm']
        self.temp_dTHm_sim = config['raspibrew']['controller'][self.num]['dTHm']
        temp_sim = config['raspibrew']['controller'][self.num]['waterTemp']
        self.temp_room_sim = config['raspibrew']['simulation']['roomTemp']

    def initLoopIteration(self):
        global temp_sim
        temp_sim = temp_sim - self.temp_dTCm_sim * (self.cycleDuration / 60) * (temp_sim - self.temp_room_sim) / (100.0 - self.temp_room_sim)
        tempValueSave()
        self.cycleDuration = 0.0

    def __init__(self,num):
        SoftPWMBase.__init__(self,num)
        self.init()


class SoftPWMGPIO(SoftPWMBase):
    def off(self,waitTime):
        import RPi.GPIO as GPIO
        GPIO.output(self.pin, False)
        SoftPWMBase.off(self,waitTime)

    def on(self,waitTime):
        import RPi.GPIO as GPIO
        GPIO.output(self.pin, True)
        SoftPWMBase.on(self,waitTime)

    def init(self):
        self.pin = config['raspibrew']['controller'][self.num]['heaterId']
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.OUT)
        self.off(0)

    def __init__(self, num):
        SoftPWMBase.__init__(self,num)
        self.init()



class SoftPWMI2C(SoftPWMBase):
    def off(self, waitTime):
        self.bus.write_byte_data(0x26, 0x09, 0x00)
        SoftPWMBase.off(self,waitTime)

    def on(self, waitTime):
        self.bus.write_byte_data(0x26, 0x09, 0x01)
        SoftPWMBase.on(self,waitTime)

    def init(self):
        self.bus = SMBus(0)
        self.off()

    def __init__(self, num):
        SoftPWMBase.__init__(self,num)
        self.init()





def heatProcGeneric(configFile, num,cycle_time, duty_cycle, conn):
    global mpid
    mpid = num

    initGlobalConfig(configFile)


    p = current_process()

    heaterId = config['raspibrew']['controller'][num]['heaterId']
    heaterType = config['raspibrew']['controller'][num]['heaterType']

    if heaterType == 'Simulated':
        pwm = SoftPWMSiumulation(num)
    elif heaterType == 'GPIO':
        pwm = SoftPWMGPIO(num)
    elif heaterType == 'I2C':
        pwm = SoftPWMI2C(num)
    else:
        raise Exception("Unknown Heater Process Style")


    print 'Starting ',heaterType,' Heater Process ', num,' with id', heaterId, ' :', p.name, p.pid




    try:
        pwm.start()

        while (True):
                pwm.cycle_time, pwm.duty_cycle = conn.recv()
                conn.send([pwm.cycle_time, pwm.duty_cycle])
    finally:
        pwm.off()

# Main Teerature Control Process
def tempControlProc(configFile, num, mode, cycle_time, duty_cycle, boil_duty_cycle, set_point, boil_manage_temp, num_pnts_smooth, k_param, i_param, d_param, statusQ, conn):
    initGlobalConfig(configFile)
    if useLCD:
        # initialize LCD
        ser = serial.Serial("/dev/ttyAMA0", 9600)
        ser.write("?BFF")
        time.sleep(.1)  # wait 100msec
        ser.write("?f?a")
        ser.write("?y0?x00PID off      ")
        ser.write("?y1?x00HLT:")
        ser.write("?y3?x00Heat: off      ")
        ser.write("?D70609090600000000")  # define degree symbol
        time.sleep(.1)  # wait 100msec

    p = current_process()
    print 'Starting Controller ', num, ':', p.name, p.pid

    # Pipe to communicate with "Get Temperature Process"
    parent_conn_temp, child_conn_temp = Pipe()
    # Start Get Temperature Process
    ptemp = Process(name="gettempProc", target=gettempProc, args=(configFile, num, child_conn_temp,))
    ptemp.daemon = True
    ptemp.start()
    # Pipe to communicate with "Heat Process"
    parent_conn_heat, child_conn_heat = Pipe()
    # Start Heat Process
    pheat = Process(name="heatProcGeneric", target=heatProcGeneric, args=(configFile, num, cycle_time, duty_cycle, child_conn_heat))
    pheat.daemon = True
    pheat.start()

    temp_F_ma_list = []
    manage_boil_trigger = False
    elapsed = 0.0

    while (True):
        readytemp = False
        if ptemp.is_alive() == False:
            # switch off if temperature process fails to deliver data
            parent_conn_heat.send([cycle_time, 0])
            print "Emergency Stop, no temperature"
            time.sleep(2)
            sys.exit()
        if pheat.is_alive() == False:
            print "Emergency Stop, no heater"
            sys.exit()

        while parent_conn_temp.poll():  # Poll Get Temperature Process Pipe
            temp_C, elapsedMeasurement = parent_conn_temp.recv()  # non blocking receive from Get Temperature Process
            elapsed = elapsed + float(elapsedMeasurement)

            if temp_C == -99:
                 print "Bad Temp Reading - retry"
                 continue
            temp_F = (9.0 / 5.0) * temp_C + 32

            temp_F_ma_list.append(temp_F)

            # smooth data
            temp_F_ma = 0.0  # moving avg init
            while (len(temp_F_ma_list) > num_pnts_smooth):
                temp_F_ma_list.pop(0)  # remove oldest elements in list

            if (len(temp_F_ma_list) < num_pnts_smooth):
                for temp_pnt in temp_F_ma_list:
                    temp_F_ma += temp_pnt
                temp_F_ma /= len(temp_F_ma_list)
            else:  # len(temp_F_ma_list) == num_pnts_smooth
                for temp_idx in range(num_pnts_smooth):
                    temp_F_ma += temp_F_ma_list[temp_idx]
                temp_F_ma /= num_pnts_smooth

            # print "len(temp_F_ma_list) = %d" % len(temp_F_ma_list)
            # print "Num Points smooth = %d" % num_pnts_smooth
            # print "temp_F_ma = %.2f" % temp_F_ma
            # print temp_F_ma_list

            temp_C_str = "%3.2f" % temp_C
            temp_F_str = "%3.2f" % temp_F
            # write to LCD
            if useLCD:
                    ser.write("?y1?x05")
                    ser.write(temp_F_str)
                    ser.write("?7")  # degree
                    time.sleep(.005)  # wait 5msec
                    ser.write("F   ")
            readytemp = True

        if readytemp == True:
            if mode == "auto":
                # calculate PID every cycle - always get latest temperature
                # print "Temp F MA %.2f" % temp_F_ma
                duty_cycle = pid.calcPID_reg4(temp_F_ma, set_point, True)
                # send to heat process every cycle
                parent_conn_heat.send([cycle_time, duty_cycle])
            if mode == "boil":
                if (temp_F > boil_manage_temp) and (manage_boil_trigger == True):  # do once
                    manage_boil_trigger = False
                    duty_cycle = boil_duty_cycle
                    parent_conn_heat.send([cycle_time, duty_cycle])

            # put current status in queue
            try:
                statusQ.put([temp_F_str, elapsed, mode, cycle_time, duty_cycle, set_point, \
                             boil_manage_temp, num_pnts_smooth, k_param, i_param, d_param])  # GET request
            except Queue.Full:
                pass

            while (statusQ.qsize() >= 2):
                statusQ.get()  # remove old status

            # print "Temp: %3.2f deg F, Heat Output: %3.1f%% %s %f" % (temp_F, duty_cycle, mode, boil_manage_temp)

            readytemp == False

        while parent_conn_heat.poll():  # Poll Heat Process Pipe
            cycle_time, duty_cycle = parent_conn_heat.recv()  # non blocking receive from Heat Process
            # write to LCD
        if useLCD:
                ser.write("?y2?x00Duty: ")
                ser.write("%3.1f" % duty_cycle)
                ser.write("%     ")

        readyPOST = False
        while conn.poll():  # POST settings - Received POST from web browser or Android device
            mode, cycle_time, duty_cycle_temp, set_point, boil_manage_temp, num_pnts_smooth, k_param, i_param, d_param = conn.recv()
            readyPOST = True
        if readyPOST == True:
            if mode == "auto":
                if useLCD:
                    ser.write("?y0?x00Auto Mode     ")
                    ser.write("?y1?x00HLT:")
                    ser.write("?y3?x00Set To: ")
                    ser.write("%3.1f" % set_point)
                    ser.write("?7")  # degree
                    time.sleep(.005)  # wait 5msec
                    ser.write("F   ")
                print "auto selected"
                pid = PIDController.pidpy(cycle_time, k_param, i_param, d_param)  # init pid
                duty_cycle = pid.calcPID_reg4(temp_F_ma, set_point, True)
            if mode == "boil":
                if useLCD:
                    ser.write("?y0?x00Boil Mode     ")
                    ser.write("?y1?x00BK: ")
                    ser.write("?y3?x00Heat: on       ")
                print "boil selected"
                boil_duty_cycle = duty_cycle_temp
                duty_cycle = 100  # full power to boil manage temperature
                manage_boil_trigger = True
            if mode == "manual":
                if useLCD:
                    ser.write("?y0?x00Manual Mode     ")
                    ser.write("?y1?x00BK: ")
                    ser.write("?y3?x00Heat: on       ")
                print "manual selected"
                duty_cycle = duty_cycle_temp
            if mode == "off":
                if useLCD:
                    ser.write("?y0?x00PID off      ")
                    ser.write("?y1?x00HLT:")
                    ser.write("?y3?x00Heat: off      ")
                print "off selected"
                duty_cycle = 0
            parent_conn_heat.send([cycle_time, duty_cycle])
            readyPOST = False
        time.sleep(.01)



def startRasPiBrew(configFile):
    initGlobalConfig(configFile)
    mydir = os.getcwd()

    urls = ("/", "raspibrew",
        "/getrand", "getrand",
        "/getstatus", "getstatus",
	"/lcd","getLCD")

    global render
    render = web.template.render(mydir + "/templates/")

    app = web.application(urls, globals())

    statusQ = []
    parent_conn = []
    child_conn = []
    p = []

    for idx in range(0, numberControllers):
        statusQ.append(Queue(2))  # blocking queue
        p_c, c_c = Pipe()
        parent_conn.append(p_c)
        child_conn.append(c_c)
        p.append(Process(name="tempControlProc" + str(idx + 1), target=tempControlProc, args=(configFile, idx + 1, param.mode, param.cycle_time, param.duty_cycle, param.boil_duty_cycle, \
                                                              param.set_point, param.boil_manage_temp, param.num_pnts_smooth, \
                                                              param.k_param, param.i_param, param.d_param, \
                                                              statusQ[idx], child_conn[idx])))
        p[idx].start()


    app.add_processor(add_global_hook(parent_conn, statusQ, numberControllers))

    app.run()

if __name__ == '__main__':
    startRasPiBrew('config.json')
