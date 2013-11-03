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


from multiprocessing import Process, Pipe, Queue, current_process
from subprocess import Popen, PIPE, call
from datetime import datetime
import web, time, random, json, serial, os
from smbus import SMBus
import RPi.GPIO as GPIO
from pid import pidpy as PIDController
import xml.etree.ElementTree as ET
import sys


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


#global hook for communication between web POST and temp control process as well as web GET and temp control process
def add_global_hook(parent_conn, statusQ):
    
    g = web.storage({"parent_conn" : parent_conn, "statusQ" : statusQ})
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
	print "XXXX"
        
    # main web page    
    def GET(self):
	i = web.input(number=1)
	print i.number
       
        return render.raspibrew(self.mode, self.set_point, self.duty_cycle, self.cycle_time, \
                                self.k_param,self.i_param,self.d_param)
    
    # get command from web browser or Android    
    def POST(self):
        data = web.data()
        datalist = data.split("&")
        for item in datalist:
            datalistkey = item.split("=")
            if datalistkey[0] == "mode":
                self.mode = datalistkey[1]
            if datalistkey[0] == "setpoint":
                self.set_point = round((float(datalistkey[1])*1.8+32)*100)/100;
		# input as celsius
            if datalistkey[0] == "dutycycle": #is boil duty cycle if mode == "boil"
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
        
        #send to main temp control process 
        #if did not receive variable key value in POST, the param class default is used
        web.ctx.globals.parent_conn.send([self.mode, self.cycle_time, self.duty_cycle, self.set_point, \
                              self.boil_manage_temp, self.num_pnts_smooth, self.k_param, self.i_param, self.d_param])  


class getstatus:
    
    def __init__(self):
        pass    

    def GET(self):
                    
        #blocking receive - current status
        temp, elapsed, mode, cycle_time, duty_cycle, set_point, boil_manage_temp, num_pnts_smooth, \
        k_param, i_param, d_param = web.ctx.globals.statusQ.get() 
            
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
    

# Retrieve temperature from DS18B20 temperature sensor

temp_C_sim = 20
temp_C_sim_count = 0

def tempDataSim(tempSensorId):
    global temp_C_sim    
    global temp_C_sim_count
    temp_C_sim_count += 1
    if temp_C_sim_count > 120:
    	temp_C_sim = temp_C_sim +  0.01 
    return temp_C_sim

# Retrieve temperature from DS18B20 temperature sensor

def tempData1Wire(tempSensorId):
    
    pipe = Popen(["cat","/opt/owfs/uncached/" + tempSensorId + "/temperature"], stdout=PIPE)
    result = pipe.communicate()[0]
    temp_C = float(result) # temp in Celcius
    return temp_C

# Stand Alone Get Temperature Process               

def getConfigXMLValue(param):
    tree = ET.parse('config.xml')
    root = tree.getroot()
    return root.find(param).text.strip()

def gettempProc(conn):
    p = current_process()
    print 'Starting:', p.name, p.pid
    
    tempSensorId = getConfigXMLValue('Temp_Sensor_Id')
    
    while (True):
        t = time.time()
        time.sleep(.5) #.1+~.83 = ~1.33 seconds
        num = tempData1Wire(tempSensorId)
        #num = tempDataSim(tempSensorId)
        elapsed = "%.2f" % (time.time() - t)
        conn.send([num, elapsed])
        
#Get time heating element is on and off during a set cycle time
def getonofftime(cycle_time, duty_cycle):
    duty = duty_cycle/100.0
    on_time = cycle_time*(duty)
    off_time = cycle_time*(1.0-duty)   
    return [on_time, off_time]
        
# Stand Alone Heat Process using I2C
def heatProcI2C(cycle_time, duty_cycle, conn):
    p = current_process()
    print 'Starting:', p.name, p.pid
    bus = SMBus(0)
    bus.write_byte_data(0x26,0x00,0x00) #set I/0 to write
    while (True):
        while (conn.poll()): #get last
            cycle_time, duty_cycle = conn.recv()
        conn.send([cycle_time, duty_cycle])  
        if duty_cycle == 0:
            bus.write_byte_data(0x26,0x09,0x00)
            time.sleep(cycle_time)
        elif duty_cycle == 100:
            bus.write_byte_data(0x26,0x09,0x01)
            time.sleep(cycle_time)
        else:
            on_time, off_time = getonofftime(cycle_time, duty_cycle)
            bus.write_byte_data(0x26,0x09,0x01)
            time.sleep(on_time)
            bus.write_byte_data(0x26,0x09,0x00)
            time.sleep(off_time)

# Stand Alone Heat Process using GPIO
def heatProcGPIO(cycle_time, duty_cycle, conn):
    p = current_process()
    print 'Starting:', p.name, p.pid
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin, GPIO.OUT)
    while (True):
        while (conn.poll()): #get last
            cycle_time, duty_cycle = conn.recv()
        conn.send([cycle_time, duty_cycle])  
        if duty_cycle == 0:
            GPIO.output(pin, False)
            time.sleep(cycle_time)
        elif duty_cycle == 100:
            GPIO.output(pin, True)
            time.sleep(cycle_time)
        else:
            on_time, off_time = getonofftime(cycle_time, duty_cycle)
            GPIO.output(pin, True)
            time.sleep(on_time)
            GPIO.output(pin, False)
            time.sleep(off_time)
           
# Main Temperature Control Process
def tempControlProc(mode, cycle_time, duty_cycle, boil_duty_cycle, set_point, boil_manage_temp, num_pnts_smooth, k_param, i_param, d_param, statusQ, conn):
   
	if false: 
        	#initialize LCD
        	ser = serial.Serial("/dev/ttyAMA0", 9600)
        	ser.write("?BFF")
        	time.sleep(.1) #wait 100msec
        	ser.write("?f?a")
        	ser.write("?y0?x00PID off      ")
        	ser.write("?y1?x00HLT:")
        	ser.write("?y3?x00Heat: off      ")
        	ser.write("?D70609090600000000") #define degree symbol
        	time.sleep(.1) #wait 100msec
            
        p = current_process()
        print 'Starting:', p.name, p.pid
        
        #Pipe to communicate with "Get Temperature Process"
        parent_conn_temp, child_conn_temp = Pipe()    
        #Start Get Temperature Process        
        ptemp = Process(name = "gettempProc", target=gettempProc, args=(child_conn_temp,))
        ptemp.daemon = True
        ptemp.start()   
        #Pipe to communicate with "Heat Process"
        parent_conn_heat, child_conn_heat = Pipe()    
        #Start Heat Process       
        pheat = Process(name = "heatProcGPIO", target=heatProcGPIO, args=(cycle_time, duty_cycle, child_conn_heat))
        pheat.daemon = True
        pheat.start() 
        
        temp_F_ma_list = []
        manage_boil_trigger = False
        
        while (True):
            readytemp = False
            while parent_conn_temp.poll(): #Poll Get Temperature Process Pipe
                temp_C, elapsed = parent_conn_temp.recv() #non blocking receive from Get Temperature Process
                
                if temp_C == -99:
                    print "Bad Temp Reading - retry"
                    continue
                temp_F = (9.0/5.0)*temp_C + 32
                
                temp_F_ma_list.append(temp_F) 
                
                #smooth data
                temp_F_ma = 0.0 #moving avg init
                while (len(temp_F_ma_list) > num_pnts_smooth):
                    temp_F_ma_list.pop(0) #remove oldest elements in list 
                
                if (len(temp_F_ma_list) < num_pnts_smooth):
                    for temp_pnt in temp_F_ma_list:
                        temp_F_ma += temp_pnt
                    temp_F_ma /= len(temp_F_ma_list)
                else: #len(temp_F_ma_list) == num_pnts_smooth
                    for temp_idx in range(num_pnts_smooth):
                        temp_F_ma += temp_F_ma_list[temp_idx]
                    temp_F_ma /= num_pnts_smooth                                      
                
                #print "len(temp_F_ma_list) = %d" % len(temp_F_ma_list)
                #print "Num Points smooth = %d" % num_pnts_smooth
                #print "temp_F_ma = %.2f" % temp_F_ma
                #print temp_F_ma_list
                
                temp_C_str = "%3.2f" % temp_C
                temp_F_str = "%3.2f" % temp_F
                #write to LCD
		if false:
                	ser.write("?y1?x05")
                	ser.write(temp_F_str)
                	ser.write("?7") #degree
                	time.sleep(.005) #wait 5msec
                	ser.write("F   ") 
                readytemp = True
                
            if readytemp == True:        
                if mode == "auto":
                    #calculate PID every cycle - always get latest temperature
                    print "Temp F MA %.2f" % temp_F_ma
                    duty_cycle = pid.calcPID_reg4(temp_F_ma, set_point, True)
                    #send to heat process every cycle
                    parent_conn_heat.send([cycle_time, duty_cycle])             
                if mode == "boil":
                    if (temp_F > boil_manage_temp) and (manage_boil_trigger == True): #do once
                        manage_boil_trigger = False
                        duty_cycle = boil_duty_cycle 
                        parent_conn_heat.send([cycle_time, duty_cycle]) 
                
                #put current status in queue    
                try:
                    statusQ.put([temp_F_str, elapsed, mode, cycle_time, duty_cycle, set_point, \
                                 boil_manage_temp, num_pnts_smooth, k_param, i_param, d_param]) #GET request
                except Queue.Full:
                    pass
                         
                while (statusQ.qsize() >= 2):
                    statusQ.get() #remove old status 
                    
                print "Temp: %3.2f deg F, Heat Output: %3.1f%% %s %f" % (temp_F, duty_cycle, mode, boil_manage_temp)
                    
                readytemp == False   
                
            while parent_conn_heat.poll(): #Poll Heat Process Pipe
                cycle_time, duty_cycle = parent_conn_heat.recv() #non blocking receive from Heat Process
                #write to LCD
		if false:
                	ser.write("?y2?x00Duty: ")
                	ser.write("%3.1f" % duty_cycle)
                	ser.write("%     ")    
                                 
            readyPOST = False
            while conn.poll(): #POST settings - Received POST from web browser or Android device
                mode, cycle_time, duty_cycle_temp, set_point, boil_manage_temp, num_pnts_smooth, k_param, i_param, d_param = conn.recv()
                readyPOST = True
            if readyPOST == True:
                if mode == "auto":
		    if false:
                    	ser.write("?y0?x00Auto Mode     ")
                    	ser.write("?y1?x00HLT:")
                    	ser.write("?y3?x00Set To: ")
                    	ser.write("%3.1f" % set_point)
                    	ser.write("?7") #degree
                    	time.sleep(.005) #wait 5msec
                    	ser.write("F   ") 
                    print "auto selected"
                    pid = PIDController.pidpy(cycle_time, k_param, i_param, d_param) #init pid
                    duty_cycle = pid.calcPID_reg4(temp_F_ma, set_point, True)
                    parent_conn_heat.send([cycle_time, duty_cycle])  
                if mode == "boil":
		    if false:
                    	ser.write("?y0?x00Boil Mode     ")
                    	ser.write("?y1?x00BK: ")
                    	ser.write("?y3?x00Heat: on       ")
                    print "boil selected"
                    boil_duty_cycle = duty_cycle_temp
                    duty_cycle = 100 #full power to boil manage temperature
                    manage_boil_trigger = True
                    parent_conn_heat.send([cycle_time, duty_cycle])  
                if mode == "manual": 
		    if false:
                    	ser.write("?y0?x00Manual Mode     ")
                    	ser.write("?y1?x00BK: ")
                    	ser.write("?y3?x00Heat: on       ")
                    print "manual selected"
                    duty_cycle = duty_cycle_temp
                    parent_conn_heat.send([cycle_time, duty_cycle])    
                if mode == "off":
		    if false:
                    	ser.write("?y0?x00PID off      ")
                    	ser.write("?y1?x00HLT:")
                    	ser.write("?y3?x00Heat: off      ")
                    print "off selected"
                    duty_cycle = 0
                    parent_conn_heat.send([cycle_time, duty_cycle])
                readyPOST = False
            time.sleep(.01)
                    
                    
if __name__ == '__main__':
    
    print 'Number of arguments:', len(sys.argv), 'arguments.'
    print 'Argument List:', str(sys.argv)

    pin = int(getConfigXMLValue('Pin'))

    os.chdir("/opt/RasPiBrew")
     
    #// call(["modprobe", "w1-gpio"])
    #// call(["modprobe", "w1-therm"])
    call(["modprobe", "i2c-bcm2708"])
    call(["modprobe", "i2c-dev"])
    
    urls = ("/", "raspibrew",
        "/getrand", "getrand",
        "/getstatus", "getstatus")

    render = web.template.render("/opt/RasPiBrew/templates/")

    app = web.application(urls, globals()) 
    
    statusQ = Queue(2) #blocking queue      
    parent_conn, child_conn = Pipe()
    p = Process(name = "tempControlProc", target=tempControlProc, args=(param.mode, param.cycle_time, param.duty_cycle, param.boil_duty_cycle, \
                                                              param.set_point, param.boil_manage_temp, param.num_pnts_smooth, \
                                                              param.k_param, param.i_param, param.d_param, \
                                                              statusQ, child_conn))
    p.start()
    
    app.add_processor(add_global_hook(parent_conn, statusQ))
     
    app.run()


