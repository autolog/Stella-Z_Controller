#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Stella-Z Thermostat Controller © Autolog 2013-2014

from collections import deque
import datetime
from datetime import datetime as autologdatetime
import operator
from threading import Lock
import httplib, urllib
import traceback
import sys


class Plugin(indigo.PluginBase):


    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):

        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        self.validatePrefsConfigUi(pluginPrefs)  # Validate the Plugin Config


    def __del__(self):

        indigo.PluginBase.__del__(self)


    def validatePrefsConfigUi(self, valuesDict):

        if "limeProtection" in valuesDict:
            self.limeProtectionEnabled = valuesDict["limeProtection"]
        else:
            self.limeProtectionEnabled = True

        self.scheduleLimeProtectionId = 0
        if self.limeProtectionEnabled == True:
            try:
                if "scheduleLimeProtectionId" in valuesDict:
                    self.scheduleLimeProtectionId = int(valuesDict["scheduleLimeProtectionId"])
            except:
                pass
            if self.scheduleLimeProtectionId == 0:
                errorDict = indigo.Dict()
                errorDict["scheduleLimeProtectionId"] = "Select a schedule which will run the Autolog command 'Lime Protection'."
                errorDict["showAlertText"] = "You must select a Schedule for Lime Protection."
                return (False, valuesDict, errorDict)

        if "bypassHeatSourceControllerTypeValidation" in valuesDict:
            self.bypassHeatSourceControllerTypeValidation = valuesDict["bypassHeatSourceControllerTypeValidation"]
        else:
            self.bypassHeatSourceControllerTypeValidation = False

        return True
    


    def runConcurrentThread(self):

        self.secondCounter = int(indigo.server.getTime().time().second)

        try:
            while True:
                self.sleep(1)  # Sleep for one second
                self.secondCounter += 1

                self.runConcurrentQueue.append('A')

                quotient, remainder = divmod(self.secondCounter, 5)  # 5 seconds
                if remainder == 0:
                    self.runConcurrentQueue.append('B')

                quotient, remainder = divmod(self.secondCounter, 10)  # 10 seconds
                if remainder == 0:
                    self.runConcurrentQueue.append('C')

                quotient, remainder = divmod(self.secondCounter, 30)  # 30 seconds
                if remainder == 0:
                    self.runConcurrentQueue.append('D')

                quotient, remainder = divmod(self.secondCounter, 60)  # 60 seconds
                if remainder == 0:
                    self.runConcurrentQueue.append('E')

                quotient, remainder = divmod(self.secondCounter, 300)  # 5 minutes
                if remainder == 0:
                    self.runConcurrentQueue.append('F')

                #quotient, remainder = divmod(self.secondCounter, 90)  # 30 minutes (1800)
                #if remainder == 0:
                #    self.runConcurrentQueue.append('G')

                quotient, remainder = divmod(self.secondCounter, 3300)  # 55 minutes
                if remainder == 0:
                    self.runConcurrentQueue.append('H')

                while True:
                    try:
                        # Dequeue process request and action it
                        self.runConcurrentProcess = self.runConcurrentQueue.popleft()
                        try:
                            self.methodToCall = getattr(self, "runConcurrentThreadMethod" + str(self.runConcurrentProcess))
                            try:
                                self.methodToCall()
                            except Exception,e:
                                indigo.server.log(u"Error detected in Autolog Plugin runConcurrentThread Method '%s'" % (self.runConcurrentProcess), isError=True)
                                indigo.server.log(u"  Error message: '%s'" % (e), isError=True)   
                        except AttributeError,e:
                            indigo.server.log(u"Error detected in Autolog Plugin runConcurrentThread Method '%s' - Method not implemented" % (self.runConcurrentProcess), isError=True)   
                            indigo.server.log(u"  Error message: '%s'" % (e), isError=True)   
                    except IndexError:
                        break

        except self.StopThread:
            pass    # Optionally catch the StopThread exception and do any needed cleanup.

    


    def runConcurrentThreadMethodA(self):  # 1 Second

        while True:
            try:
                # Dequeue process request and action it
                self.process = self.processQueue.popleft()
                try:
                    self._processThermostat(indigo.devices[self.process[0]], self.process[1])
                except StandardError, e:

                    indigo.server.log(u"StandardError detected for '%s' with function '%s'. Line '%s' has error='%s'" % (indigo.devices[self.process[0]].name, self.process[1], sys.exc_traceback.tb_lineno, e), isError=True)   
            except IndexError:
                break

    


    def runConcurrentThreadMethodB(self):  # 5 Seconds

        for dev in indigo.devices.iter("self"):
            if dev.enabled == True and dev.configured == True:
                devId = dev.id

                # Update Stella-Z Z-Wave status
                self.processQueue.append((dev.id,'updateZwaveStatus'))

                if self.thermostats[devId]['remoteId'] != 0:
                    if self.thermostats[devId]['zwaveRemoteWakeupInterval'] != 0:
                        self.processQueue.append((dev.id,'updateRemoteZwaveStatus'))

                # Check for pending heat request
                if self.thermostats[devId]['mode'] == "Heat Pending":
                    self.lock.acquire()
                    try:
                        # Only increment number of thermostats calling for heat if this thermostat not currently calling for heat
                        if self.thermostats[devId]['mode'] == "Heat Pending":
                            # Only call for heat once the Stella-Z has been sent the z-wave command to set the heat setpoint 
                            if self.thermostats[devId]['modeDatetimeChanged'] < autologdatetime.strptime(self.thermostats[devId]['zwaveDatetime'], '%Y-%m-%d %H:%M:%S'):
                                self.thermostats[devId]['mode'] = "Heat On"
                                self.heaters[self.thermostats[devId]['heatingId']]['callingForHeat'] += 1  # Increment number of thermostats calling for heat
                    finally:
                        self.lock.release()

                if self.thermostats[dev.id]['zwaveWakeupDelay'] == False and self.thermostats[dev.id]['zwaveRemoteWakeupDelay'] == False:


                    if (self.thermostats[dev.id]['mode'] == "Heat On"):
                        dev.updateStateOnServer(key='mode', value='Active', uiValue=self.thermostats[dev.id]['mode'])  # Indicate thermostat calling for heat
                        dev.updateStateImageOnServer(indigo.kStateImageSel.HvacHeating)
                    elif (self.thermostats[dev.id]['mode'] == "Heat Pending"):
                        dev.updateStateOnServer(key='mode', value='Pending', uiValue=self.thermostats[dev.id]['mode'])  # Indicate thermostat calling for heat but Pending
                        dev.updateStateImageOnServer(indigo.kStateImageSel.HvacHeatMode)
                    else:
                        dev.updateStateOnServer(key='mode', value='Inactive', uiValue=self.thermostats[dev.id]['mode'])  # Indicate thermostat no longer calling for heat
                        dev.updateStateImageOnServer(indigo.kStateImageSel.HvacOff)

    


    def runConcurrentThreadMethodC(self):  # 10 Seconds

        # Check all heat sources - should they be on or off
        for key, value in self.heaters.iteritems():
                self.checkHeatingSourceStatus(key)

    


    def runConcurrentThreadMethodD(self):  # 30 Seconds

        self.currentTime = indigo.server.getTime()

        for dev in indigo.devices.iter("self"):
            if dev.enabled == True and dev.configured == True:
                devId = dev.id
                
                # Check for AM heating period
                if self.thermostats[devId]['scheduleAmSetup'] == True:
                    if (self.checkTime(self.currentTime, self.thermostats[devId]['scheduleResetAmTimeOn']) == True) or (self.checkTime(self.currentTime, self.thermostats[devId]['scheduleResetAmTimeOff']) == True):
                        if self.thermostats[devId]['scheduleAmFired'] == False:
                            self.thermostats[devId]['scheduleAmFired'] = True
                            if self.thermostats[devId]['advanceStatus'] == "on":
                                self.processQueue.append((dev.id,'processCancelAdvance'))   
                            self.processQueue.append((dev.id,'processSchedule'))
                    else:
                        self.thermostats[devId]['scheduleAmFired'] = False

                # Check for PM heating period
                if self.thermostats[devId]['schedulePmSetup'] == True:
                    if (self.checkTime(self.currentTime, self.thermostats[devId]['scheduleResetPmTimeOn']) == True) or (self.checkTime(self.currentTime, self.thermostats[devId]['scheduleResetPmTimeOff']) == True):
                        if self.thermostats[devId]['schedulePmFired'] == False:
                            self.thermostats[devId]['schedulePmFired'] = True
                            if self.thermostats[devId]['advanceStatus'] == "on":
                                self.processQueue.append((dev.id,'processCancelAdvance'))   
                            self.processQueue.append((dev.id,'processSchedule'))
                    else:
                        self.thermostats[devId]['schedulePmFired'] = False

                # Check whether a boost is 'on' for this thermostat and if so check whether it should be ended       
                if self.thermostats[devId]['boostStatus'] == "on":
                    # As 'boost' is on - check whether it should be ended
                    self.testDateTime = self.thermostats[devId]['boostDateTimeEnd']
                    if self.testDateTime < self.currentTime:
                        indigo.server.log(u"'%s' Checking for Boost End from runConcurrentThread" % (dev.name))
                        self.processQueue.append((dev.id,'processEstablishState'))

                # Check whether an extend is 'on' for this thermostat and if so check whether it should be ended       
                if self.thermostats[devId]['extendStatus'] == "on":
                    # As 'extend' is on - check whether it should be ended
                    self.testDateTime = self.thermostats[devId]['extendDateTimeEnd']
                    if self.testDateTime < self.currentTime:
                        indigo.server.log(u"'%s' Checking for Extend End from runConcurrentThread" % (dev.name))
                        self.processQueue.append((dev.id,'processEstablishState'))
    


    def checkTime(self, currentTime, checkTime):
        if (currentTime.time().hour == checkTime.hour) and (currentTime.time().minute == checkTime.minute):
            return True
        else:
            return False

    


    def runConcurrentThreadMethodE(self):  # 1 minute

        # Check Lime Protection
        self.handleLimeProtection()

    


    def runConcurrentThreadMethodF(self):  # 5 minutes

        # Check Lime Protection
        self.checkLimeProtectionStatus()

    


    def runConcurrentThreadMethodG(self):  # 30 minutes

        # Check Z-Wave Monitoring
        for dev in indigo.devices.iter("self"):
            if dev.deviceTypeId == "stellazType" and dev.enabled == True:
                if self.thermostats[dev.id]['zwaveEventCount'] == 0 and self.thermostats[dev.id]['zwaveWakeupDelay'] == True:
                    indigo.server.log(u"WARNING: Z-Wave monitoring may not be active for '%s' - Please check / set-up trigger for Stella-Z '%s' (see Plugin documentation)" % (dev.name, indigo.devices[self.thermostats[dev.id]['stellazId']].name), isError=True)
                elif self.thermostats[dev.id]['remoteId'] != 0 and self.thermostats[dev.id]['zwaveRemoteEventCount'] == 0 and self.thermostats[dev.id]['zwaveRemoteWakeupDelay'] == True:
                    indigo.server.log(u"WARNING: Z-Wave monitoring may not be fully active for '%s' - Please check / set-up trigger for Remote Thermostat '%s' (see Plugin documentation)" % (dev.name, indigo.devices[self.thermostats[dev.id]['remoteId']].name), isError=True)
    


    def runConcurrentThreadMethodH(self):  # 55 minutes

        # Check all heat sources - should they be on or off
        for key, value in self.heaters.iteritems():
            self.processKeepHeatSourceControllerAlive(key)

    


    def updateZwaveStatus(self, dev):

        try:

            if self.thermostats[dev.id]['zwaveEventCountPrevious'] == 0 and self.thermostats[dev.id]['zwaveEventCount'] == 1:
                indigo.server.log(u"'%s' [Stella-Z] Z-Wave activity detected and now being monitored" % (dev.name))

            if self.thermostats[dev.id]['zwaveEventCountPrevious'] != self.thermostats[dev.id]['zwaveEventCount']:
                self.thermostats[dev.id]['zwaveEventCountPrevious'] = self.thermostats[dev.id]['zwaveEventCount']
                dev.updateStateOnServer("lastupdated", self.thermostats[dev.id]['zwaveDatetime'][-8:])

            currentTime = indigo.server.getTime()

            delta = currentTime - autologdatetime.strptime(self.thermostats[dev.id]['zwaveDatetime'][0:19], '%Y-%m-%d %H:%M:%S')
            minutes, seconds = divmod(delta.seconds, 60)
            self.thermostats[dev.id]['zwaveDeltaCurrent'] = str("0" + str(minutes))[-2:] + ":" + str("0" + str(seconds))[-2:]       
            if minutes > int(self.thermostats[dev.id]['zwaveWakeupInterval']):
                delta = minutes - int(self.thermostats[dev.id]['zwaveWakeupInterval'])
                if self.thermostats[dev.id]['zwaveWakeupDelay'] == False:
                    self.thermostats[dev.id]['zwaveWakeupDelay'] = True
                    if self.thermostats[dev.id]['zwaveEventCount'] == 0:
                        indigo.server.log(u"WARNING: The Device was started %s minutes ago and no wakeups have been detected for '%s' [Stella-Z]. Wakeup interval is set to %s minutes." % (minutes, dev.name, self.thermostats[dev.id]['zwaveWakeupInterval']), isError=True)
                        indigo.server.log(u"WARNING: Z-Wave monitoring may not be active for '%s' - Please check / set-up trigger for Stella-Z '%s' (see Plugin documentation)" % (dev.name, indigo.devices[self.thermostats[dev.id]['stellazId']].name), isError=True)
                    else:
                        indigo.server.log(u"WARNING: At least one wakeup has now been missed for '%s' [Stella-Z]. Wakeup interval is set to %s minutes; last Z-Wave command processed %s minutes ago." % (dev.name, self.thermostats[dev.id]['zwaveWakeupInterval'], minutes), isError=True)


                    # Re-Send set heat setpoint for next wake-up (just in case)
                    indigo.thermostat.setHeatSetpoint(self.thermostats[dev.id]['stellazId'], value=float(self.thermostats[dev.id]['heatSetpointStellaz']))
                if delta > 1:
                    dev.updateStateOnServer(key='mode', value='Delay', uiValue='Delay ' + str(delta) + ' mins')
                    dev.updateStateImageOnServer(indigo.kStateImageSel.TimerOn)
                else:
                    dev.updateStateOnServer(key='mode', value='Delay', uiValue='Delay ' + str(delta) + ' min')    
                    dev.updateStateImageOnServer(indigo.kStateImageSel.TimerOn)
            else:
                if self.thermostats[dev.id]['zwaveWakeupDelay'] == True:
                    self.thermostats[dev.id]['zwaveWakeupDelay'] = False
                    indigo.server.log("'%s' [Stella-Z] has woken up but at least one wakeup was missed." % (dev.name))
            dev.updateStateOnServer("updatetime", self.thermostats[dev.id]['zwaveDeltaCurrent'] + ' [' + str(self.thermostats[dev.id]['zwaveWakeupInterval']) + ']')

        except StandardError, e:

            indigo.server.log(u"StandardError detected for '%s' with function '%s'. Line '%s' has error='%s'" % (indigo.devices[self.process[0]].name, self.process[1], sys.exc_traceback.tb_lineno, e), isError=True)   
        return
    


    def updateRemoteZwaveStatus(self, dev):

        if self.thermostats[dev.id]['zwaveRemoteEventCountPrevious'] == 0 and self.thermostats[dev.id]['zwaveRemoteEventCount'] == 1:
            indigo.server.log(u"'%s' [Remote Thermostat] Z-Wave activity detected and now being monitored" % (dev.name))

        if self.thermostats[dev.id]['zwaveRemoteEventCountPrevious'] != self.thermostats[dev.id]['zwaveRemoteEventCount']:
            self.thermostats[dev.id]['zwaveRemoteEventCountPrevious'] = self.thermostats[dev.id]['zwaveRemoteEventCount']
            dev.updateStateOnServer("updatetimestamp", self.thermostats[dev.id]['zwaveRemoteDatetime'][-8:])

        currentTime = indigo.server.getTime()

        delta = currentTime - autologdatetime.strptime(self.thermostats[dev.id]['zwaveRemoteDatetime'][0:19], '%Y-%m-%d %H:%M:%S')
        minutes, seconds = divmod(delta.seconds, 60)
        self.thermostats[dev.id]['zwaveRemoteDeltaCurrent'] = str("0" + str(minutes))[-2:] + ":" + str("0" + str(seconds))[-2:]       
        if minutes > int(self.thermostats[dev.id]['zwaveRemoteWakeupInterval']):
            delta = minutes - int(self.thermostats[dev.id]['zwaveRemoteWakeupInterval'])
            if self.thermostats[dev.id]['zwaveRemoteWakeupDelay'] == False:
                self.thermostats[dev.id]['zwaveRemoteWakeupDelay'] = True

                if self.thermostats[dev.id]['zwaveRemoteEventCount'] == 0:
                    indigo.server.log(u"WARNING: The Device was started %s minutes ago and no wakeups have been detected for '%s' [Remote Thermostat]. Wakeup interval is set to %s minutes." % (minutes, indigo.devices[self.thermostats[dev.id]['remoteId']].name, self.thermostats[dev.id]['zwaveRemoteWakeupInterval']), isError=True)
                    indigo.server.log(u"WARNING: Z-Wave monitoring may not be fully active for '%s' - Please check / set-up trigger for associated Remote Thermostat '%s' (see Plugin documentation)" % (dev.name, indigo.devices[self.thermostats[dev.id]['remoteId']].name), isError=True)
                else:
                    indigo.server.log(u"WARNING: At least one wakeup has now been missed for '%s' [Remote Thermostat associated with '%s']. Wakeup interval is set to %s minutes; last Z-Wave command processed %s minutes ago." % (indigo.devices[self.thermostats[dev.id]['remoteId']].name, dev.name, self.thermostats[dev.id]['zwaveRemoteWakeupInterval'], minutes), isError=True)

            if delta > 1:
                dev.updateStateOnServer(key='mode', value='Delay', uiValue='Delay ' + str(delta) + ' mins')
                dev.updateStateImageOnServer(indigo.kStateImageSel.TimerOn)
            else:
                dev.updateStateOnServer(key='mode', value='Delay', uiValue='Delay ' + str(delta) + ' min')    
                dev.updateStateImageOnServer(indigo.kStateImageSel.TimerOn)
        else:
            if self.thermostats[dev.id]['zwaveRemoteWakeupDelay'] == True:
                self.thermostats[dev.id]['zwaveRemoteWakeupDelay'] = False
                indigo.server.log("'%s' [Remote Thermosta] has woken up but at least one wakeup was missed." % (dev.name))
        dev.updateStateOnServer("timestamp", self.thermostats[dev.id]['zwaveRemoteDeltaCurrent'] + ' [' + str(self.thermostats[dev.id]['zwaveRemoteWakeupInterval']) + ']')

        return
    


    def processMonitorStellazZwave(self, pluginAction, dev):

        # pluginAction = 'processMonitorStellazZwaveActivity'
        #
        # dev = Stella-Z Thermostat Controller

        self.thermostats[dev.id]['zwaveEventCount'] += 1

        self.thermostats[dev.id]['zwaveDatetime'] = str(indigo.server.getTime())[0:19]

        self.processQueue.append((dev.id,'updateZwaveStatus'))  # Update Stella-Z Z-Wave status

        return
    


    def processMonitorRemoteZwave(self, pluginAction, dev):

        # pluginAction = 'processMonitorRemoteZwave'
        #
        # dev = Stella-Z Thermostat Controller

        # indigo.server.log(u"processMonitorRemoteZwave function entered for '%s'" % (dev.name))

        self.thermostats[dev.id]['zwaveRemoteEventCount'] += 1

        self.thermostats[dev.id]['zwaveRemoteDatetime'] = str(indigo.server.getTime())[0:19]

        self.processQueue.append((dev.id,'updateRemoteZwaveStatus'))  # Update Remote Thermostat Z-Wave status

        return
    


    def deviceUpdated(self, origDev, newDev):

        if int(newDev.id) in self.deviceUpdates.keys():  # Check if a Stella-Z or Remote Thermostat
            if indigo.devices[int(self.deviceUpdates[newDev.id]['autologDeviceId'])].enabled is True:
                self.autologDev = indigo.devices[int(self.deviceUpdates[newDev.id]['autologDeviceId'])]

                self.newTemp = 0
                try:
                    self.newTemp = float(newDev.temperatures[0])  # Stella-Z
                except AttributeError:
                    try:
                        self.newTemp = float(newDev.states['sensorValue'])  # Aeon 4 in 1
                    except (AttributeError, KeyError):
                        try:
                            self.newTemp = float(newDev.states['temperature'])  # Oregon Scientific Temp Sensor
                        except (AttributeError, KeyError):
                            try:
                                self.newTemp = float(newDev.states['Temperature'])  # Netatmo
                            except (AttributeError, KeyError):
                                indigo.server.log(u"'%s' is an unknown Remote Thermostat type - remote support disabled. [C]" % (newDev.name), isError=True)
                                del self.deviceUpdates[self.thermostats[self.autologDev.id]['remoteId']]  # Disable Remote Support
                                self.thermostats[self.autologDev.id]['remoteId'] = 0

                if self.deviceUpdates[newDev.id]['type'] == "stellaz":  
                    # Now check the wakeup interval in case it has changed
                    self.wakeupInterval = int(indigo.devices[self.thermostats[self.autologDev.id]['stellazId']].globalProps["com.perceptiveautomation.indigoplugin.zwave"]["zwWakeInterval"])
                    if int(self.thermostats[self.autologDev.id]['zwaveWakeupInterval']) != self.wakeupInterval:
                        indigo.server.log(u"'%s' [%s] wakeup interval changed from [%s] to [%s]." % (self.autologDev.name, newDev.name, self.thermostats[self.autologDev.id]['zwaveWakeupInterval'], self.wakeupInterval))
                        self.thermostats[self.autologDev.id]['zwaveWakeupInterval'] = self.wakeupInterval

                if  self.deviceUpdates[newDev.id]['type'] != "stellaz":
                    if self.thermostats[self.autologDev.id]['remoteHeatSetpointControl'] == True:
                        try:
                            if float(newDev.heatSetpoint) != float(self.thermostats[self.autologDev.id]['heatSetpointRemote']) != float(origDev.heatSetpoint):
                                indigo.server.log(u"'%s' Heat Setpoint changed. 'New' = %s, 'Original' = %s, 'Saved' = %s" % (newDev.name, newDev.heatSetpoint, origDev.heatSetpoint, self.thermostats[self.autologDev.id]['heatSetpointRemote']))  
                                self.thermostats[self.autologDev.id]['valueSetHeatSetpoint'] = float(newDev.heatSetpoint)
                                self.processQueue.append((self.autologDev.id,'processSetHeatSetpoint'))
                        except (AttributeError):
                            indigo.server.log(u"ATTRIBUTE ERROR: origDev='%s', newDev='%s'" % (origDev.name,newDev.name))  
 
        
                if self.newTemp != float(self.deviceUpdates[newDev.id]['temperature']):
                    if self.deviceUpdates[newDev.id]['type'] == "stellaz":
                        self.type = "Stella-Z"
                    else:
                        self.type = "Remote Thermostat"
                    if self.thermostats[self.autologDev.id]['hideTempBroadcast'] == False:
                        if float(self.deviceUpdates[newDev.id]['temperature']) == 0:
                            indigo.server.log(u"'%s' updated from %s [%s] with temperature %s following device start." % (self.autologDev.name, self.type, newDev.name, self.newTemp))
                        else:
                            indigo.server.log(u"'%s' updated from %s [%s] with changed temperature %s (was %s)" % (self.autologDev.name, self.type, newDev.name, self.newTemp, self.deviceUpdates[newDev.id]['temperature']))
                    self.deviceUpdates[newDev.id]['temperature'] = self.newTemp 
                    self._refreshStatesFromStellaz(indigo.devices[int(self.deviceUpdates[newDev.id]['autologDeviceId'])], False, False)
                    if self.limeProtectionActive == False:
                        # Only process device update if Lime Protection not active
                        self._processThermostat(indigo.devices[int(self.deviceUpdates[newDev.id]['autologDeviceId'])], 'processCheckTemperature')
        else:
            if newDev.model == "Stella-Z Thermostat Controller":
                if newDev.enabled is True and newDev.id in self.validateDeviceFlag:
                    if self.validateDeviceFlag[newDev.id]["edited"] == True:
                        self.validateDeviceFlag[newDev.id]["edited"] = False
                        indigo.server.log(u"'%s' [%s] has been edited and will be stopped and restarted" % (newDev.name, newDev.model))

        indigo.PluginBase.deviceUpdated(self, origDev, newDev)

        return
    

    def _refreshStatesFromStellaz(self, dev, logRefresh, commJustStarted):

        devId = dev.id

        self.thermostats[devId]['temperature'] = 0.0
        self.thermostats[devId]['temperatureRemote'] = 0.0
        self.thermostats[devId]['temperatureStellaz'] = 0.0

        if indigo.devices[int(self.thermostats[devId]['stellazId'])].enabled is True:
            if indigo.devices[int(self.thermostats[devId]['stellazId'])].temperatures[0] <= 0.0:
                pass
            else:
                self.thermostats[devId]['temperatureStellaz'] = float(indigo.devices[int(self.thermostats[devId]['stellazId'])].temperatures[0])
                self.thermostats[devId]['temperature'] = float(indigo.devices[int(self.thermostats[devId]['stellazId'])].temperatures[0])

                if self.thermostats[devId]['remoteId'] != 0:
                    if indigo.devices[int(self.thermostats[devId]['remoteId'])].enabled is True:
                        self.temperatureRemote = 0
                        try:
                            self.temperatureRemote = float(indigo.devices[int(self.thermostats[devId]['remoteId'])].temperatures[0])  # Stella-Z
                        except AttributeError:
                            try:
                                self.temperatureRemote = float(indigo.devices[int(self.thermostats[devId]['remoteId'])].states['sensorValue'])  # Aeon 4 in 1 / Fibaro FGMS-001
                            except (AttributeError, KeyError):
                                try:
                                    self.temperatureRemote = float(indigo.devices[int(self.thermostats[devId]['remoteId'])].states['temperature'])  # Oregon Scientific Temp Sensor
                                except (AttributeError, KeyError):
                                    try:
                                        self.temperatureRemote = float(indigo.devices[int(self.thermostats[devId]['remoteId'])].states['Temperature'])  # Netatmo
                                    except (AttributeError, KeyError):
                                        indigo.server.log(u"'%s' is an unknown Remote Thermostat type - remote support disabled." % (dev.name), isError=True)
                                        del self.deviceUpdates[self.thermostats[devId]['remoteId']]  # Disable Remote Support
                                        self.thermostats[devId]['remoteId'] = 0 
                        if self.temperatureRemote <= 0.0:
                            self.thermostats[devId]['temperatureRemote'] = 0.0
                        else:
                            self.thermostats[devId]['temperatureRemote'] = float(self.temperatureRemote)
                            self.thermostats[devId]['temperature'] = float(self.temperatureRemote)
                        if self.thermostats[devId]['remoteHeatSetpointControl'] == True:
                            try:
                                self.thermostats[devId]['heatSetpointRemote'] = float(indigo.devices[int(self.thermostats[devId]['remoteId'])].heatSetpoint)
                            except:
                                indigo.server.log(u"'%s' heatSetpointRemote error for Remote Thermostat." % (dev.name), isError=True)

        dev.updateStateOnServer("temperature", float(self.thermostats[devId]['temperature']))
        dev.updateStateOnServer("temperatureStellaz", float(self.thermostats[devId]['temperatureStellaz']))
        dev.updateStateOnServer("temperatureRemote", float(self.thermostats[devId]['temperatureRemote']))

        return
    


    def checkHeatingSourceStatus(self, heatingId):
        # Determine if heating should be started / ended 

        self.lock.acquire()
        try:
            #indigo.server.log(u"Check Heating Source: calling for heat = %s" % (self.heaters[heatingId]['callingForHeat']))
            if self.heaters[heatingId]['callingForHeat'] > 0:
                # if there are thermostats calling for heat, the heating needs to be 'on'
                indigo.variable.updateValue(self.variableId, value="true")  # Variable indicator to show that heating is being requested
                if self.heaters[heatingId]['deviceType'] == 1:
                    if not indigo.devices[heatingId].hvacMode == indigo.kHvacMode.Heat:  # Only turn heating 'on' if it is currently 'off'
                        #indigo.server.log(u"AAAAA")
                        indigo.thermostat.setHvacMode(heatingId, value=indigo.kHvacMode.Heat) # Turn heating 'on'
                elif self.heaters[heatingId]['deviceType'] == 2:
                    if indigo.devices[heatingId].onState == False:  # Only turn heating 'on' if it is currently 'off'
                        #indigo.server.log(u"AAAAA")
                        indigo.device.turnOn(heatingId) # Turn heating 'on'
                else:
                    pass  # ERROR SITUATION
            else:
                # if no thermostats are calling for heat, then the heating needs to be 'off'
                indigo.variable.updateValue(self.variableId, value="false")  # Variable indicator to show that heating is NOT being requested
                if self.heaters[heatingId]['deviceType'] == 1:
                    if not indigo.devices[heatingId].hvacMode == indigo.kHvacMode.Off:  # Only turn heating 'off' if it is currently 'on'
                        #indigo.server.log(u"BBBBB")
                        indigo.thermostat.setHvacMode(heatingId, value=indigo.kHvacMode.Off) # Turn heating 'off'
                elif self.heaters[heatingId]['deviceType'] == 2:        
                    if indigo.devices[heatingId].onState == True:  # Only turn heating 'off' if it is currently 'on'
                        #indigo.server.log(u"AAAAA")
                        indigo.device.turnOff(heatingId) # Turn heating 'off'
                else:
                    pass  # ERROR SITUATION
  
        finally:
            self.lock.release()

        return
    


    def processKeepHeatSourceControllerAlive(self, heatingId):

        self.lock.acquire()
        try:

            # Only needed for SSR302 / SSR303
            if indigo.devices[heatingId].model == "1 Channel Boiler Actuator (SSR303 / ASR-ZW)" or indigo.devices[heatingId].model ==  "2 Channel Boiler Actuator (SSR302)":
                # if the Heat Source Controller is currently 'on' - tell it to stay 'on'
                if indigo.devices[heatingId].hvacMode == indigo.kHvacMode.Heat:
                    indigo.thermostat.setHvacMode(heatingId, value=indigo.kHvacMode.Heat) # remind Heat Source Controller to stay 'on'

                # if the boiler is currently 'off' - tell it to stay 'off'
                if indigo.devices[heatingId].hvacMode == indigo.kHvacMode.Off:
                    indigo.thermostat.setHvacMode(heatingId, value=indigo.kHvacMode.Off) # remind Heat Source Controller to stay 'off'
        finally:
            self.lock.release()

        return
    


    def handleLimeProtection(self):

        if self.limeProtectionRequested == False and self.limeProtectionActive == False:
            return

        currentTime = indigo.server.getTime()

        if self.limeProtectionRequested == True:
            if self.limeProtectionActive == False:
                self.limeProtectionActive = True
                indigo.server.log("Lime Protection now in progress.")

                for dev in indigo.devices.iter("self"):
                    devId = dev.id
                    if dev.enabled == True and dev.configured == True:
                        if indigo.devices[self.thermostats[devId]['heatingId']].hvacMode == indigo.kHvacMode.Heat:
                            indigo.thermostat.setHvacMode(self.thermostats[devId]['heatingId'], value=indigo.kHvacMode.Off)  # Turn off Heating Source Controller for Thermostat (Note: May have more than one Heat Source Controller)
                        self.thermostats[devId]['processLimeProtection'] = 'off'
                        self.thermostats[devId]['processLimeProtection'] = 'starting'
                        self.thermostats[devId]['limeProtectionCheckTime'] = currentTime
                        self.thermostats[devId]['mode'] = 'Off'
                        self.thermostats[devId]['heatSetpointStellaz'] = 50.0
                        indigo.thermostat.setHeatSetpoint(self.thermostats[devId]['stellazId'], value=float(self.thermostats[devId]['heatSetpointStellaz']))  # Force Valve Open
                        indigo.server.log("Lime Protection waiting to start for '%s'" % (dev.name))

        else:
            if self.limeProtectionActive == True:
                self.limeProtectionActive = False
                self.limeProtectionRequested = False
                for dev in indigo.devices.iter("self"):
                    devId = dev.id
                    if dev.enabled == True and dev.configured == True:
                        if self.thermostats[devId]['processLimeProtection'] != 'off':
                            self.thermostats[devId]['heatSetpointStellaz'] = self.thermostats[devId]['heatSetpointOff']
                            indigo.thermostat.setHeatSetpoint(self.thermostats[devId]['stellazId'], value=float(self.thermostats[devId]['heatSetpointStellaz']))  # Force Valve Close
                            indigo.server.log("Lime Protection cancelled for '%s'" % (dev.name))
                            self.thermostats[devId]['processLimeProtection'] = 'off'
                indigo.server.log("Lime Protection cancelled.")

        if self.limeProtectionActive == True:
            for dev in indigo.devices.iter("self"):
                devId = dev.id
                if dev.enabled == True and dev.configured == True:
                    if self.thermostats[devId]['limeProtectionCheckTime'] < autologdatetime.strptime(self.thermostats[devId]['zwaveDatetime'], '%Y-%m-%d %H:%M:%S'):
                        self.thermostats[devId]['limeProtectionCheckTime'] = currentTime
                        if self.thermostats[devId]['processLimeProtection'] == 'starting':
                            self.thermostats[devId]['processLimeProtection'] = 'on'
                            indigo.server.log("Lime Protection now in progress for '%s'" % (dev.name))
                        elif self.thermostats[devId]['processLimeProtection'] == 'on':
                            self.thermostats[devId]['processLimeProtection'] = 'off'
                            indigo.server.log("Lime Protection now completing for '%s'" % (dev.name))
                            # As Lime Protection not active for this Thermostat - Set Turn Off setpoint
                            self.thermostats[devId]['heatSetpointStellaz'] = self.thermostats[devId]['heatSetpointOff']
                            indigo.thermostat.setHeatSetpoint(self.thermostats[devId]['stellazId'], value=float(self.thermostats[devId]['heatSetpointStellaz']))  # Force Valve Close

        return
    


    def checkLimeProtectionStatus(self):

        if self.limeProtectionRequested == False and self.limeProtectionActive == False:
            return

        self.limeProtectionCount = 0
        self.limeProtectionThermostatList = ""
        for dev in indigo.devices.iter("self"):
            devId = dev.id
            if dev.enabled == True and dev.configured == True:
                if self.thermostats[devId]['processLimeProtection'] != 'off':
                    self.limeProtectionCount += 1
                    if self.limeProtectionCount == 1:
                        self.limeProtectionThermostatList = str("'%s'" % (dev.name))
                    else:
                        self.limeProtectionThermostatList = str("%s, '%s'" % (self.limeProtectionThermostatList, dev.name))
        if self.limeProtectionCount > 0:
            if self.limeProtectionCount == 1:
                indigo.server.log("Lime Protection still in progress for thermostat %s" % (self.limeProtectionThermostatList))
            else:
                indigo.server.log("Lime Protection still in progress for %s thermostats: %s" % (self.limeProtectionCount, self.limeProtectionThermostatList))
        else:
            self.limeProtectionActive = False
            self.limeProtectionRequested = False
            indigo.server.log("Lime Protection now completed")

        return
    


    def validateActionConfigUi(self, valuesDict, typeId, actionId):

        self.validateActionFlag[actionId] = {}

        if typeId == "processSetHeatSetpoint":
            self.validateActionFlag[actionId]['valueSetHeatSetpoint'] = 0
            try:
                if "valueSetHeatSetpoint" in valuesDict:
                    self.validateActionFlag[actionId]['valueSetHeatSetpoint'] = float(valuesDict["valueSetHeatSetpoint"])
            except:
                pass
            if self.validateActionFlag[actionId]['valueSetHeatSetpoint'] <= 6 or self.validateActionFlag[actionId]['valueSetHeatSetpoint'] > 50 or self.validateActionFlag[actionId]['valueSetHeatSetpoint'] % 0.5 != 0:
                errorDict = indigo.Dict()
                errorDict["valueSetHeatSetpoint"] = "Temperature must be set between 7 and 50 (inclusive)"
                errorDict["showAlertText"] = "You must enter a valid heat setpoint temperature for the Stella-Z thermostat. It must be set between 7 and 50 (inclusive) and a multiple of 0.5."
                self.validateActionFlag.clear()
                return (False, valuesDict, errorDict)
            else:
                valuesDict['description'] = "Set Heat Setpoint to %s" % (self.validateActionFlag[actionId]['valueSetHeatSetpoint'])

        if typeId == "processIncreaseHeatSetpoint":
            self.validateActionFlag[actionId]['deltaIncreaseHeatSetpoint'] = 0
            try:
                if "deltaIncreaseHeatSetpoint" in valuesDict:
                    self.validateActionFlag[actionId]['deltaIncreaseHeatSetpoint'] = float(valuesDict["deltaIncreaseHeatSetpoint"])
            except:
                pass
            if self.validateActionFlag[actionId]['deltaIncreaseHeatSetpoint'] <= 0 or self.validateActionFlag[actionId]['deltaIncreaseHeatSetpoint'] > 5 or self.validateActionFlag[actionId]['deltaIncreaseHeatSetpoint'] % 0.5 != 0:
                errorDict = indigo.Dict()
                errorDict["deltaIncreaseHeatSetpoint"] = "Increase delta must be set between 1 and 5 (inclusive)"
                errorDict["showAlertText"] = "You must enter a valid increase delta (amount to increase temperature by) for the Stella-Z thermostat. It must be set between 1 and 5 (inclusive) and a multiple of 0.5"
                self.validateActionFlag.clear()
                return (False, valuesDict, errorDict)
            else:
                valuesDict['description'] = "Increase Heat Setpoint by %s" % (self.validateActionFlag[actionId]['deltaIncreaseHeatSetpoint'])

        if typeId == "processDecreaseHeatSetpoint":
            self.validateActionFlag[actionId]['deltaDecreaseHeatSetpoint'] = 0
            try:
                if "deltaDecreaseHeatSetpoint" in valuesDict:
                    self.validateActionFlag[actionId]['deltaDecreaseHeatSetpoint'] = float(valuesDict["deltaDecreaseHeatSetpoint"])
            except:
                pass
            if self.validateActionFlag[actionId]['deltaDecreaseHeatSetpoint'] <= 0 or self.validateActionFlag[actionId]['deltaDecreaseHeatSetpoint'] > 5 or self.validateActionFlag[actionId]['deltaDecreaseHeatSetpoint'] % 0.5 != 0:
                errorDict = indigo.Dict()
                errorDict["deltaDecreaseHeatSetpoint"] = "Decrease delta must be set between 1 and 5 (inclusive)"
                errorDict["showAlertText"] = "You must enter a valid decrease delta (amount to decrease temperature by) for the Stella-Z thermostat. It must be set between 1 and 5 (inclusive) and a multiple of 0.5"
                self.validateActionFlag.clear()
                return (False, valuesDict, errorDict)
            else:
                valuesDict['description'] = "Decrease Heat Setpoint by %s" % (self.validateActionFlag[actionId]['deltaDecreaseHeatSetpoint'])

        self.validateActionFlag.clear()

        return (True, valuesDict)
    

    
    def processLimeProtection(self, pluginAction):

        self.limeProtectionRequested = True

        return
    


    def processCancelLimeProtection(self, pluginAction):

        if self.limeProtectionActive == False:
            indigo.server.log("Lime Protection not active - Cancel request ignored.")
            return

        self.limeProtectionRequested = False

        return
    


    def processTurnOn(self, pluginAction, dev):

        self.processQueue.append((dev.id,'processSetHeatSetpointOn'))

        return
    


    def processTurnOff(self, pluginAction, dev):

        self.processQueue.append((dev.id,'processSetHeatSetpointOff'))

        return
    


    def processToggleTurnOnOff(self, pluginAction, dev):

        if float(self.thermostats[dev.id]['heatSetpoint']) == float(self.thermostats[dev.id]['heatSetpointOff']):
            self.processTurnOn(pluginAction, dev)
        else:
            self.processTurnOff(pluginAction, dev)
 
        return
    


    def processSetHeatSetpoint(self, pluginAction, dev):

        devId = dev.id
        try:
            self.thermostats[dev.id]['valueSetHeatSetpoint'] = float(pluginAction.props.get("valueSetHeatSetpoint"))
        except (ValueError, TypeError):
            indigo.server.log(u"set heat setpoint action to device \"%s\" - invalid setpoint value [%s]. Must be numeric." % (dev.name, pluginAction.props.get("valueSetHeatSetpoint")), isError=True)
            return

        if self.thermostats[dev.id]['valueSetHeatSetpoint'] <= 6 or self.thermostats[dev.id]['valueSetHeatSetpoint'] > 50 or self.thermostats[devId]['valueSetHeatSetpoint'] % 0.5 != 0:
            indigo.server.log(u"set heat setpoint action to device \"%s\" - invalid setpoint value [%s]. It must be between 7 and 50 (inclusive) and a multiple of 0.5." % (dev.name, pluginAction.props.get("valueSetHeatSetpoint")), isError=True)
            return

        self.processQueue.append((dev.id,'processSetHeatSetpoint'))

        return
    


    def processIncreaseHeatSetpoint(self, pluginAction, dev):

        try:
            self.thermostats[dev.id]['deltaIncreaseHeatSetpoint'] = float(pluginAction.props.get("deltaIncreaseHeatSetpoint"))
        except (ValueError, TypeError) as e:
            indigo.server.log(u"increase heat setpoint action to device \"%s\" - invalid increase delta value [%s]. Must be numeric." % (dev.name, pluginAction.props.get("deltaIncreaseHeatSetpoint")), isError=True)
            return

        if self.thermostats[dev.id]['deltaIncreaseHeatSetpoint'] < 0.5 or self.thermostats[dev.id]['deltaIncreaseHeatSetpoint'] > 5.0 or self.thermostats[dev.id]['deltaIncreaseHeatSetpoint'] % 0.5 != 0:
            indigo.server.log(u"increase heat setpoint action to device \"%s\" - invalid increase delta value [%s]. It must be between 0.5 and 5.0 (inclusive) and a multiple of 0.5." % (dev.name, pluginAction.props.get("deltaIncreaseHeatSetpoint")), isError=True)
            return

        if (float(self.thermostats[dev.id]['heatSetpoint']) + self.thermostats[dev.id]['deltaIncreaseHeatSetpoint']) > 50:
            indigo.server.log(u"increase heat setpoint action to device \"%s\" - invalid increase delta value [%s]. It must not cause heat setpoint to exceed 50.0 " % (dev.name, pluginAction.props.get("deltaIncreaseHeatSetpoint"), self.thermostats[dev.id]['heatSetpoint']), isError=True)
            return

        self.processQueue.append((dev.id,'processIncreaseHeatSetpoint'))

        return
    


    def processDecreaseHeatSetpoint(self, pluginAction, dev):

        try:
            self.thermostats[dev.id]['deltaDecreaseHeatSetpoint'] = float(pluginAction.props.get("deltaDecreaseHeatSetpoint"))
        except (ValueError, TypeError) as e:
            indigo.server.log(u"decrease heat setpoint action to device \"%s\" -- invalid decrease delta value [%s]. Must be numeric." % (dev.name, pluginAction.props.get("deltaDecreaseHeatSetpoint")), isError=True)
            return

        if self.thermostats[dev.id]['deltaDecreaseHeatSetpoint'] < 0.5 or self.thermostats[dev.id]['deltaDecreaseHeatSetpoint'] > 5.0 or self.thermostats[dev.id]['deltaDecreaseHeatSetpoint'] % 0.5 != 0:
            indigo.server.log(u"decrease heat setpoint action to device \"%s\" - invalid decrease delta value [%s]. It must be between 0.5 and 5.0 (inclusive) and a multiple of 0.5." % (dev.name, pluginAction.props.get("deltaDecreaseHeatSetpoint")), isError=True)
            return

        if (float(self.thermostats[dev.id]['heatSetpoint']) - self.thermostats[dev.id]['deltaDecreaseHeatSetpoint']) < 6.0:
            indigo.server.log(u"decrease heat setpoint action to device \"%s\" - applying delta value [-%s] will cause heat setpoint [%s] to be less than 6.0 - request ignored" % (dev.name, pluginAction.props.get("deltaDecreaseHeatSetpoint"), self.thermostats[dev.id]['heatSetpoint']), isError=False)
            return

        self.processQueue.append((dev.id,'processDecreaseHeatSetpoint'))
 
        return
    


    def processAdvance(self, pluginAction, dev):

        self.processQueue.append((dev.id,'processAdvance'))

        return
    


    def processCancelAdvance(self, pluginAction, dev):

        self.processQueue.append((dev.id,'processCancelAdvance'))

        return
    


    def processAdvanceToggle(self, pluginAction, dev):

        if self.thermostats[dev.id]['advanceStatus'] == "off":
            self.processAdvance(pluginAction, dev)
        else:
            self.processCancelAdvance(pluginAction, dev)

        return
    


    def processBoost(self, pluginAction, dev):

        self.processQueue.append((dev.id,'processBoost'))

        return
    


    def processCancelBoost(self, pluginAction, dev):

        self.processQueue.append((dev.id,'processCancelBoost'))

        return
    


    def processBoostToggle(self, pluginAction, dev):

        if self.thermostats[dev.id]['boostRequested'] == False:
            self.processBoost(pluginAction, dev)
        else:
            self.processCancelBoost(pluginAction, dev)

        return
    


    def processExtend(self, pluginAction, dev):

        indigo.server.log("Extend requested for '%s' - Initial logic" % (dev.name))
        self.processQueue.append((dev.id,'processExtend'))

        return
    


    def processCancelExtend(self, pluginAction, dev):

        indigo.server.log("Extend cancelled for '%s' - Initial logic" % (dev.name))
        self.processQueue.append((dev.id,'processCancelExtend'))

        return
    


    def processEstablishState(self, pluginAction, dev):

        self.processQueue.append((dev.id,'processEstablishState'))

        return
    

    def processShowSchedules(self, pluginAction):


        indigo.server.log(u"Heating Schedules")

        for dev in indigo.devices.iter("self"):
            if dev.enabled == True and dev.configured == True:
                devId = dev.id

                if self.thermostats[devId]['scheduleAmSetup'] == True:
                    self.amShow = str(self.thermostats[devId]['scheduleAmTimeOn'])[0:5] + ' - ' + str(self.thermostats[devId]['scheduleAmTimeOff'])[0:5]
                else:
                    self.amShow = "-------------"

                if self.thermostats[devId]['schedulePmSetup'] == True:
                    self.pmShow = str(self.thermostats[devId]['schedulePmTimeOn'])[0:5] + ' - ' + str(self.thermostats[devId]['schedulePmTimeOff'])[0:5]
                else:
                    self.pmShow = "-------------"

                indigo.server.log(u"'%s' AM = [%s], PM = [%s]" % (dev.name, self.amShow, self.pmShow))

        return
    

    def processShowStatus(self, pluginAction, dev):
 
        devId = dev.id
        indigo.server.log("Showing full internal status of '%s'" % (dev.name))
        for self.key in sorted(self.thermostats[devId].iterkeys()):
            indigo.server.log("'%s' %s = %s" % (dev.name, self.key, self.thermostats[devId][self.key]))

        indigo.server.log("Heat Source Controller '%s':  CallingForHeat = %s" % (indigo.devices[self.thermostats[devId]['heatingId']].name, self.heaters[self.thermostats[devId]['heatingId']]['callingForHeat']))
 

        return
    

    def processShowZwaveWakeupInterval(self, pluginAction):
 
        self.statusOptimize = {}
        for dev in indigo.devices.iter("self"):
            if dev.enabled == True and dev.configured == True:
                devId = dev.id

                if self.thermostats[devId]['zwaveDeltaCurrent'] != "[n/a]":
                    self.tempSplit = self.thermostats[devId]['zwaveDeltaCurrent'].split(':')
                    self.tempZwaveDeltaCurrent = int(self.tempSplit[0]) * 60 + int(self.tempSplit[1])
                    # self.tempZwaveDeltaCurrent = autologdatetime.strptime(self.thermostats[devId]['zwaveDeltaCurrent'], '%M:%S')
                    self.tempA, self.tempB = divmod(self.tempZwaveDeltaCurrent, 300)
                    self.statusOptimize[dev.name] = int(self.tempB)

        indigo.server.log(u"Z-wave wakeup intervals between Stella-Zs (in seconds):")
        self.optimizeDifference = 0
        self.sorted = sorted(self.statusOptimize.iteritems(), key=operator.itemgetter(1,0))
        for item1 in self.sorted:
            if self.optimizeDifference == 0:  # Ensure Intervals start at zero
                self.optimizeDifference = int(item1[1])
            self.optimizeDifferenceCalc = int(item1[1] - self.optimizeDifference)
            indigo.server.log("  %s = %s [Interval = %s]" % (item1[0], str("  " + str(item1[1]))[-3:], str("  " + str(self.optimizeDifferenceCalc))[-3:]))
            self.optimizeDifference = int(item1[1])


        return
    


    def _processThermostat(self, dev, processThermostatFunction):

        try:

            # if dev.name == "Thermostat-10" or dev.name == "Thermostat-11": 
            #     indigo.server.log(u"'%s': processThermostatFunction = %s" % (dev.name, processThermostatFunction))

            devId = dev.id

            self.currentTime = indigo.server.getTime()

            if int(self.thermostats[devId]['temperature']) <= 0:
                # ensureThermostatOff(thermostatBeingProcessed, thermostat_id)                              
                return

            if self.limeProtectionActive == True:
                if processThermostatFunction != 'updateZwaveStatus' and processThermostatFunction != 'updateRemoteZwaveStatus':
                    if self.thermostats[devId]['processLimeProtection'] != 'off':
                        indigo.server.log("Lime Protection still in progress for '%s', so '%s' command ignored." % (dev.name, processThermostatFunction))
                    else:
                        indigo.server.log("Lime Protection has completed for '%s' but '%s' command ignored as other thermostats still undergoing Lime Protection." % (dev.name, processThermostatFunction))
                return

            if processThermostatFunction == 'updateZwaveStatus':
                self.updateZwaveStatus(dev)  # Update Stella-Z Z-Wave status
                return
     
            if processThermostatFunction == 'updateRemoteZwaveStatus':
                self.updateRemoteZwaveStatus(dev)  # Update remote Thermostat Z-Wave status
                return
     
            #
            # Check for processSchedule & processEstablishState
            #
            if processThermostatFunction == 'processSchedule' or processThermostatFunction == 'processEstablishState':

                # Determine current schedule time - has to be derived as Indigo doesn't directly hold this value
                if self.thermostats[devId]['scheduleAmSetup'] == True:
                    self.amON = autologdatetime.combine(self.currentTime, self.thermostats[devId]['scheduleAmTimeOn'])
                    self.amOFF = autologdatetime.combine(self.currentTime, self.thermostats[devId]['scheduleAmTimeOff'])
                else:
                    self.amON = 0
                    self.amOFF = 0
                if self.thermostats[devId]['schedulePmSetup'] == True:
                    self.pmON = autologdatetime.combine(self.currentTime, self.thermostats[devId]['schedulePmTimeOn'])
                    self.pmOFF = autologdatetime.combine(self.currentTime, self.thermostats[devId]['schedulePmTimeOff'])
                else:
                    self.pmON = 0
                    self.pmOFF = 0
         
                self.thermostats[devId]['scheduleAmActive'] = False
                self.thermostats[devId]['schedulePmActive'] = False
                # Check if current server time is within an active 'ON' schedule
                if (self.amON != 0 and self.amOFF != 0) and (self.amON <= self.currentTime < self.amOFF):
                    # In the AM Schedule 
                    self.thermostats[devId]['heatSetpoint'] = float(self.thermostats[devId]['heatSetpointAm'])
                    self.thermostats[devId]['scheduleAmActive'] = True
                    indigo.server.log("'%s' AM [%s-%s] heating schedule now active" % (dev.name, str(self.amON)[11:16], str(self.amOFF)[11:16]))
                elif (self.pmON != 0 and self.pmOFF != 0) and (self.pmON <= self.currentTime < self.pmOFF):
                    # In the PM Schedule 
                    self.thermostats[devId]['heatSetpoint'] = float(self.thermostats[devId]['heatSetpointPm'])
                    self.thermostats[devId]['schedulePmActive'] = True
                    indigo.server.log("'%s' PM [%s-%s] heating schedule now active" % (dev.name, str(self.pmON)[11:16], str(self.pmOFF)[11:16]))
                else:
                    if processThermostatFunction == 'processSchedule':
                        indigo.server.log("'%s' heating schedule ended" % (dev.name))
                    if self.thermostats[devId]['boostRequested'] == False and self.thermostats[devId]['boostStatus'] == "off":
                        # Set Target Temperature to 'Off" value as not in active schedule and no boost requested or active
                        self.thermostats[devId]['heatSetpoint'] = float(self.thermostats[devId]['heatSetpointOff'])
                    else:
                        # Set Target Temperature to 'Boost" value as boost requested and active
                        self.thermostats[devId]['heatSetpoint'] = float(self.thermostats[devId]['heatSetpointBoost'])

            #
            # ##### End of processSchedule, processEstablishState #####


            #
            # ##### Check for processAdvance #####
            #
            if processThermostatFunction == 'processAdvance':

                # Cancel any active Boost or Extend
                if self.thermostats[devId]['boostRequested'] == True or self.thermostats[devId]['boostStatus'] == "on":
                    indigo.server.log("Boost cancelled as Advance requested for '%s'" % (dev.name))
                    self.thermostats[devId]['boostRequested'] = False

                if self.thermostats[devId]['extendRequested'] == True or self.thermostats[devId]['extendStatus'] == "on":
                    indigo.server.log("Extend cancelled as Advance requested for '%s'" % (dev.name))
                    self.thermostats[devId]['extendRequested'] = False


                if self.thermostats[devId]['advanceStatus'] != "on":
                    # Advance not currently active - Try and turn it 'On'     
                    self.thermostats[devId]['heatSetpointAdvance'] = float(self.thermostats[devId]['heatSetpointOff'])  # Default to 'off' advance heat setpoint
                    self.thermostats[devId]['advanceSetDatetime'] = self.currentTime - datetime.timedelta(minutes=1)

                    if self.thermostats[devId]['scheduleAmSetup'] == True:
                        self.amON = autologdatetime.combine(self.currentTime, self.thermostats[devId]['scheduleAmTimeOn'])
                        self.amOFF = autologdatetime.combine(self.currentTime, self.thermostats[devId]['scheduleAmTimeOff'])
                    else:
                        self.amON = 0
                        self.amOFF = 0
                    if self.thermostats[devId]['schedulePmSetup'] == True:
                        self.pmON = autologdatetime.combine(self.currentTime, self.thermostats[devId]['schedulePmTimeOn'])
                        self.pmOFF = autologdatetime.combine(self.currentTime, self.thermostats[devId]['schedulePmTimeOff'])
                    else:
                        self.pmON = 0
                        self.pmOFF = 0

                    if (self.amON != 0) and (self.amON > self.currentTime):
                        # Before AM ON = advance to AM schedule by setting AM Schedule 'ON' time to 'now'
                        self.thermostats[devId]['heatSetpointAdvance'] = float(self.thermostats[devId]['heatSetpointAm'])
                        self.thermostats[devId]['advanceStatus'] = "on"
                        self.thermostats[devId]['scheduleAmTimeOn'] = self.thermostats[devId]['advanceSetDatetime'].time()
                        self.amON = self.thermostats[devId]['advanceSetDatetime']
                        self.thermostats[devId]['scheduleAmActive'] = True
                        indigo.server.log("Schedule Advance actioned  for '%s' - Revised AM [%s-%s] heating schedule now active." % (dev.name, str(self.amON)[11:16], str(self.amOFF)[11:16]))
                    elif (self.amON != 0 and self.amOFF != 0) and (self.amON <= self.currentTime <= self.amOFF):
                        # AM Schedule active = advance to AM schedule End i.e. off
                        self.thermostats[devId]['heatSetpointAdvance'] = float(self.thermostats[devId]['heatSetpointOff'])
                        self.thermostats[devId]['advanceStatus'] = "on"
                        self.thermostats[devId]['scheduleAmTimeOff'] = self.thermostats[devId]['advanceSetDatetime'].time()
                        self.amOFF = self.thermostats[devId]['advanceSetDatetime']
                        self.thermostats[devId]['scheduleAmActive'] = False
                        indigo.server.log("Schedule Advance actioned for '%s' - AM schedule ended early" % (dev.name))
                    elif ((self.amOFF != 0 and self.pmON != 0) and (self.amOFF < self.currentTime < self.pmON)) or ((self.amOFF == 0 and self.pmON != 0) and (self.currentTime < self.pmON)):
                        # After AM OFF and before PM ON = advance to PM schedule
                        self.thermostats[devId]['heatSetpointAdvance'] = float(self.thermostats[devId]['heatSetpointPm'])
                        self.thermostats[devId]['advanceStatus'] = "on"
                        self.thermostats[devId]['schedulePmTimeOn'] = self.thermostats[devId]['advanceSetDatetime'].time()
                        self.pmON = self.thermostats[devId]['advanceSetDatetime']
                        self.thermostats[devId]['schedulePmActive'] = True
                        indigo.server.log("Schedule Advance actioned for '%s' - Revised PM [%s-%s] heating schedule now active." % (dev.name, str(self.pmON)[11:16], str(self.pmOFF)[11:16]))
                    elif (self.pmON != 0 and self.pmOFF != 0) and (self.pmON <= self.currentTime <= self.pmOFF):
                        # PM schedule active = advance to PM schedule End i.e. off
                        self.thermostats[devId]['heatSetpointAdvance'] = float(self.thermostats[devId]['heatSetpointOff'])
                        self.thermostats[devId]['advanceStatus'] = "on"
                        self.thermostats[devId]['schedulePmTimeOff'] = self.thermostats[devId]['advanceSetDatetime'].time()
                        self.pmOFF = self.thermostats[devId]['advanceSetDatetime']
                        self.thermostats[devId]['schedulePmActive'] = False
                        indigo.server.log("Schedule Advance actioned for '%s' - PM schedule now ended early." % (dev.name))
                    else:
                        #  No advance available as either 1) After PM off or 2) after AM (with no PM schedule set) or 3) no Am and PM schedule set
                        indigo.server.log("Schedule Advance ignored for '%s' - No schedule to advance to." % (dev.name))
                        self.thermostats[devId]['advanceStatus'] = "off"  # Just in case!
                        self.thermostats[devId]['scheduleAmTimeOn'] = self.thermostats[devId]['scheduleResetAmTimeOn']
                        self.thermostats[devId]['scheduleAmTimeOff'] = self.thermostats[devId]['scheduleResetAmTimeOff']
                        self.thermostats[devId]['schedulePmTimeOn'] = self.thermostats[devId]['scheduleResetPmTimeOn']
                        self.thermostats[devId]['schedulePmTimeOff'] = self.thermostats[devId]['scheduleResetPmTimeOff']
                        self.thermostats[devId]['heatSetpointAdvance'] = float(self.thermostats[devId]['heatSetpointOff'])
                    self.thermostats[devId]['heatSetpoint'] = float(self.thermostats[devId]['heatSetpointAdvance'])
                else:
                    # Advance currently active - Nothing to do
                    indigo.server.log("Schedule Advance request ignored as 'Advance' already active for '%s'" % (dev.name))
            #
            # ##### End of processAdvance #####


            #
            # ##### Check for processCancelAdvance #####
            #
            if processThermostatFunction == 'processCancelAdvance':
                if self.thermostats[devId]['advanceStatus'] == "on":
                    self.thermostats[devId]['advanceStatus'] = "off"
                    self.thermostats[devId]['scheduleAmTimeOn'] = self.thermostats[devId]['scheduleResetAmTimeOn']
                    self.thermostats[devId]['scheduleAmTimeOff'] = self.thermostats[devId]['scheduleResetAmTimeOff']
                    self.thermostats[devId]['schedulePmTimeOn'] = self.thermostats[devId]['scheduleResetPmTimeOn']
                    self.thermostats[devId]['schedulePmTimeOff'] = self.thermostats[devId]['scheduleResetPmTimeOff']
                    self.thermostats[devId]['heatSetpointAdvance'] = self.thermostats[devId]['heatSetpointOff']
                    self.thermostats[devId]['heatSetpoint'] = float(self.thermostats[devId]['heatSetpointAdvance'])
                    self.thermostats[devId]['advanceSetDatetime'] = "n/a"
                    self.processQueue.append((dev.id,'processEstablishState'))
                    indigo.server.log("Schedule Advance cancelled for '%s' - Normal schedule reset." % (dev.name))
                else:
                    indigo.server.log("Schedule Advance cancel request ignored as 'Advance' not active for '%s'" % (dev.name))
            #
            # ##### End of processCancelAdvance #####
            

            #
            #  ##### Check for processBoost #####
            #
            if processThermostatFunction == 'processBoost':
                indigo.server.log("Boost requested  for '%s'" % (dev.name))
                self.thermostats[devId]['boostRequested'] = True
                self.thermostats[devId]['boostDateTimeStart'] = self.currentTime
                # ###### Future requirement - Add logic to add in additional amount for time to next wakeup so that we get the full amount of boost ######
                self.thermostats[devId]['boostDateTimeEnd'] = self.currentTime + datetime.timedelta(minutes = int(self.thermostats[devId]['boostMinutes']))
            #
            # ##### End of processBoost #####


            #
            #  ##### Check for processCancelBoost #####
            #
            if processThermostatFunction == 'processCancelBoost':
                if self.thermostats[devId]['boostRequested'] == False and self.thermostats[devId]['boostStatus'] == "off":
                    indigo.server.log("Cancel boost requested ignored as boost not active for '%s'" % (dev.name))
                    return
                else:
                    indigo.server.log("Boost cancelled for '%s'" % (dev.name))
                    self.thermostats[devId]['boostRequested'] = False
            #
            # ##### End of processCancelBoost #####


            #
            #  ##### Handle active Boosts #####
            #
            if self.thermostats[devId]['boostRequested'] == True:
                if self.thermostats[devId]['boostStatus'] == "off":
                    self.thermostats[devId]['boostStatus'] = "on"
                    self.thermostats[devId]['heatSetpointBoost'] = float(self.thermostats[devId]['temperature']) + float(self.thermostats[devId]['boostDelta'])
                    self.thermostats[devId]['heatSetpoint'] = float(self.thermostats[devId]['heatSetpointBoost'])
                else:
                    # boost currently on - check whether it should be ended
                    self.testDateTime = self.thermostats[devId]['boostDateTimeEnd']
                    if self.testDateTime < self.currentTime:
                        self.thermostats[devId]['boostRequested'] = False

            if self.thermostats[devId]['boostRequested'] == False:  # NOTE: This test is needed as previous logic may have set the value to False
                if self.thermostats[devId]['boostStatus'] == "on":
                    # boost requested is false but boost is currently on = turn it off
                    self.thermostats[devId]['boostStatus'] = "off"

                    if self.thermostats[devId]['scheduleAmSetup'] == True:
                        self.amON = autologdatetime.combine(self.currentTime, self.thermostats[devId]['scheduleAmTimeOn'])
                        self.amOFF = autologdatetime.combine(self.currentTime, self.thermostats[devId]['scheduleAmTimeOff'])
                    else:
                        self.amON = 0
                        self.amOFF = 0
                    if self.thermostats[devId]['schedulePmSetup'] == True:
                        self.pmON = autologdatetime.combine(self.currentTime, self.thermostats[devId]['schedulePmTimeOn'])
                        self.pmOFF = autologdatetime.combine(self.currentTime, self.thermostats[devId]['schedulePmTimeOff'])
                    else:
                        self.pmON = 0
                        self.pmOFF = 0

                    # Check if current server time is within an active 'ON' schedule
                    if (self.amON != 0 and self.amOFF != 0) and (self.amON <= self.currentTime <= self.amOFF):
                        # In the AM Schedule
                        self.thermostats[devId]['heatSetpoint'] = self.thermostats[devId]['heatSetpointAm']
                        indigo.server.log("'%s' boost ended - AM Schedule is currently Active" % (dev.name))
                    elif (self.pmON != 0 and self.pmOFF != 0) and (self.pmON <= self.currentTime <= self.pmOFF):
                        # In the PM Schedule 
                        self.thermostats[devId]['heatSetpoint'] = self.thermostats[devId]['heatSetpointPm']
                        indigo.server.log("'%s' boost ended - PM Schedule is currently Active" % (dev.name))
                    else:
                        # Set Target Temperature to 'Off" value as not in active schedule and no boost requested or active
                        self.thermostats[devId]['heatSetpoint'] = self.thermostats[devId]['heatSetpointOff']
                        indigo.server.log("'%s' boost ended - no Schedule is currently Active" % (dev.name))

                    self.thermostats[devId]['boostDateTimeStart'] = "n/a"
                    self.thermostats[devId]['boostDateTimeEnd'] = "n/a"
            #
            # ##### End of Handle active Boosts #####


            #
            # ##### Check for processExtend #####
            #
            if processThermostatFunction == 'processExtend':
                indigo.server.log("Extend requested for '%s'." % (dev.name))
                if self.thermostats[devId]['extendRequested'] == False:
                    self.thermostats[devId]['extendRequested'] = True
                    self.thermostats[devId]['extendMinutes'] = 0
                self.thermostats[devId]['extendMinutes'] = self.thermostats[devId]['extendMinutes'] + self.thermostats[devId]['extendIncrementMinutes']
                if self.thermostats[devId]['extendMinutes'] > self.thermostats[devId]['extendMaximumMinutes']:
                    processThermostatFunction = 'processCancelExtend'
                else:
                    if self.thermostats[devId]['extendStatus'] == "off":
                        self.thermostats[devId]['extendStatus'] = "on"

                    if self.thermostats[devId]['scheduleAmSetup'] == True:
                        self.amON = autologdatetime.combine(self.currentTime, self.thermostats[devId]['scheduleAmTimeOn'])
                        self.amOFF = autologdatetime.combine(self.currentTime, self.thermostats[devId]['scheduleAmTimeOff'])
                    else:
                        self.amON = 0
                        self.amOFF = 0
                    if self.thermostats[devId]['schedulePmSetup'] == True:
                        self.pmON = autologdatetime.combine(self.currentTime, self.thermostats[devId]['schedulePmTimeOn'])
                        self.pmOFF = autologdatetime.combine(self.currentTime, self.thermostats[devId]['schedulePmTimeOff'])
                    else:
                        self.pmON = 0
                        self.pmOFF = 0
                    self.endOfday = autologdatetime.combine(self.currentTime, autologdatetime.strptime("23:59", '%H:%M').time())

                    # Check if current server time is within an active 'ON' schedule
                    if (self.amON != 0 and self.amOFF != 0) and (self.amON <= self.currentTime <= self.amOFF):
                        # In the AM Schedule
                        self.amOFF =  self.amOFF + datetime.timedelta(minutes = int(self.thermostats[devId]['extendIncrementMinutes']))
                        if self.pmON != 0 and  self.pmON <= self.amOFF:
                            self.amOFF = self.self.pmON - datetime.timedelta(minutes=2)
                        if self.amOFF > self.endOfday :
                            self.amOFF = self.endOfday
                        self.thermostats[devId]['scheduleAmTimeOff'] = self.amOFF.time()
                        self.thermostats[devId]['extendDateTimeEnd'] = self.amOFF    
                        self.thermostats[devId]['extendDateTimeStart'] = autologdatetime.combine(self.currentTime, self.thermostats[devId]['scheduleResetAmTimeOff'])
                        indigo.server.log("'%s' AM Schedule extended to '%s'" % (dev.name,self.thermostats[devId]['scheduleAmTimeOff']))
                    elif (self.pmON != 0 and self.pmOFF != 0) and (self.pmON <= self.currentTime <= self.pmOFF):
                        # In the PM Schedule
                        self.pmOFF = self.pmOFF + datetime.timedelta(minutes = int(self.thermostats[devId]['extendIncrementMinutes']))
                        if self.pmOFF > self.endOfday :
                            self.pmOFF = self.endOfday
                        self.thermostats[devId]['schedulePmTimeOff'] = self.pmOFF.time()    
                        self.thermostats[devId]['extendDateTimeEnd'] = self.pmOFF    
                        self.thermostats[devId]['extendDateTimeStart'] = autologdatetime.combine(self.currentTime, self.thermostats[devId]['scheduleResetPmTimeOff'])
                        indigo.server.log("'%s' PM Schedule extended to '%s'" % (dev.name,self.thermostats[devId]['schedulePmTimeOff']))
                    else:
                        # Set Target Temperature to standard 'On" value as not in active schedule
                        self.thermostats[devId]['heatSetpoint'] = self.thermostats[devId]['heatSetpointOn']
                        self.thermostats[devId]['extendDateTimeStart'] = self.currentTime
                        self.thermostats[devId]['extendDateTimeEnd'] = self.thermostats[devId]['extendDateTimeStart'] + datetime.timedelta(minutes = int(self.thermostats[devId]['extendMinutes']))
                        if self.thermostats[devId]['extendDateTimeEnd'] > self.endOfday :
                            self.thermostats[devId]['extendDateTimeEnd'] = self.endOfday
                        indigo.server.log("'%s' Extend period of %s minutes activated until '%s'" % (dev.name, self.thermostats[devId]['extendMinutes'], str(self.thermostats[devId]['extendDateTimeEnd'].time())[:5]))
                        # indigo.server.log("'%s' Extend period of %s minutes activated until '%s'" % (dev.name, self.thermostats[devId]['extendMinutes'], self.thermostats[devId]['extendDateTimeEnd'])
            #
            # ##### End of processExtend #####


            #
            # ##### Check for processCancelExtend #####
            #
            if processThermostatFunction == 'processCancelExtend':
                indigo.server.log("Cancel Extend request logic entered for '%s'." % (dev.name))
                if self.thermostats[devId]['extendStatus'] == "off" and self.thermostats[devId]['extendRequested'] == False:
                    indigo.server.log("Cancel Extend request ignored for '%s' as Extend not active." % (dev.name))
                else:
                    self.thermostats[devId]['extendRequested'] = False     
            #
            # ##### End of processCancelExtend #####


            #
            #  ##### Handle active Extends #####
            #
            if self.thermostats[devId]['extendStatus'] == "on":
                # extend currently on - check whether it should be ended
                if self.thermostats[devId]['extendDateTimeEnd'] < self.currentTime:
                    self.thermostats[devId]['extendRequested'] = False

                if self.thermostats[devId]['extendRequested'] == False:  # NOTE: This test is needed as previous logic may have set the value to False
                    # extend requested is false but extend is currently on = turn it off
                    self.thermostats[devId]['extendStatus'] = "off"

                    # Reset scheule time to default
                    # self.thermostats[devId]['scheduleAmTimeOn'] = self.thermostats[devId]['scheduleResetAmTimeOn']
                    self.thermostats[devId]['scheduleAmTimeOff'] = self.thermostats[devId]['scheduleResetAmTimeOff']
                    # self.thermostats[devId]['schedulePmTimeOn'] = self.thermostats[devId]['scheduleResetPmTimeOn']
                    self.thermostats[devId]['schedulePmTimeOff'] = self.thermostats[devId]['scheduleResetPmTimeOff']

                    if self.thermostats[devId]['scheduleAmSetup'] == True:
                        self.amON = autologdatetime.combine(self.currentTime, self.thermostats[devId]['scheduleAmTimeOn'])
                        self.amOFF = autologdatetime.combine(self.currentTime, self.thermostats[devId]['scheduleAmTimeOff'])
                    else:
                        self.amON = 0
                        self.amOFF = 0
                    if self.thermostats[devId]['schedulePmSetup'] == True:
                        self.pmON = autologdatetime.combine(self.currentTime, self.thermostats[devId]['schedulePmTimeOn'])
                        self.pmOFF = autologdatetime.combine(self.currentTime, self.thermostats[devId]['schedulePmTimeOff'])
                    else:
                        self.pmON = 0
                        self.pmOFF = 0

                    # Check if current server time is within an active 'ON' schedule
                    if (self.amON != 0 and self.amOFF != 0) and (self.amON <= self.currentTime <= self.amOFF):
                        # In the AM Schedule
                        self.thermostats[devId]['heatSetpoint'] = self.thermostats[devId]['heatSetpointAm']
                        indigo.server.log("'%s' extend ended - AM Schedule is currently Active" % (dev.name))
                    elif (self.pmON != 0 and self.pmOFF != 0) and (self.pmON <= self.currentTime <= self.pmOFF):
                        # In the PM Schedule 
                        self.thermostats[devId]['heatSetpoint'] = self.thermostats[devId]['heatSetpointPm']
                        indigo.server.log("'%s' extend ended - PM Schedule is currently Active" % (dev.name))
                    else:
                        # Set Target Temperature to 'Off" value as not in active schedule and no boost requested or active
                        self.thermostats[devId]['heatSetpoint'] = self.thermostats[devId]['heatSetpointOff']
                        indigo.server.log("'%s' extend ended - no Schedule is currently Active" % (dev.name))

                    self.thermostats[devId]['extendDateTimeStart'] = "n/a"
                    self.thermostats[devId]['extendDateTimeEnd'] = "n/a"
            #
            # ##### End of Handle active Extends #####


            #
            #  ##### Check for processSetHeatSetpoint #####
            #
            if processThermostatFunction == 'processSetHeatSetpoint':
                self.thermostats[devId]['heatSetpoint'] = float(self.thermostats[devId]['valueSetHeatSetpoint'])
                indigo.server.log("Heat setpoint altered to %s for '%s'" % (self.thermostats[devId]['valueSetHeatSetpoint'], dev.name))

            #
            # ##### End of processSetHeatSetpoint #####

            #
            #  ##### Check for processSetHeatSetpointOn #####
            #
            if processThermostatFunction == 'processSetHeatSetpointOn':
                self.thermostats[devId]['heatSetpoint'] = float(self.thermostats[devId]['heatSetpointOn'])
                indigo.server.log("Turn 'ON' requested  for '%s' - Heat Setpoint set to %s" % (dev.name, self.thermostats[devId]['heatSetpoint']))
            #
            # ##### End of processSetHeatSetpointOn #####


            #
            #  ##### Check for processSetHeatSetpointOff #####
            #
            if processThermostatFunction == 'processSetHeatSetpointOff':
                self.thermostats[devId]['heatSetpoint'] = float(self.thermostats[devId]['heatSetpointOff'])
                indigo.server.log("Turn 'OFF' requested  for '%s' - Heat Setpoint reset to %s" % (dev.name, self.thermostats[devId]['heatSetpoint']))

                # Cancel any active Boost or Extend
                if self.thermostats[devId]['boostRequested'] == True or self.thermostats[devId]['boostStatus'] == "on":
                    indigo.server.log("Boost cancelled as Turn 'OFF'  requested for '%s'" % (dev.name))
                    self.thermostats[devId]['boostRequested'] = False

                if self.thermostats[devId]['extendRequested'] == True or self.thermostats[devId]['extendStatus'] == "on":
                    indigo.server.log("Extend cancelled as Turn 'OFF'  requested for '%s'" % (dev.name))
                    self.thermostats[devId]['extendRequested'] = False
            #
            # ##### End of processSetHeatSetpointOn #####


            #
            #  ##### Check for processIncreaseHeatSetpoint #####
            #
            if processThermostatFunction == 'processIncreaseHeatSetpoint':
                self.thermostats[devId]['heatSetpoint'] = float(self.thermostats[devId]['heatSetpoint']) + float(self.thermostats[devId]['deltaIncreaseHeatSetpoint'])
                indigo.server.log("Heat setpoint increased by %s to %s for '%s'" % (self.thermostats[devId]['deltaIncreaseHeatSetpoint'], self.thermostats[devId]['heatSetpoint'], dev.name))
            #
            # ##### End of processIncreaseHeatSetpoint #####


            #
            #  ##### Check for processDecreaseHeatSetpoint #####
            #
            if processThermostatFunction == 'processDecreaseHeatSetpoint':
                self.thermostats[devId]['heatSetpoint'] = float(self.thermostats[devId]['heatSetpoint']) - float(self.thermostats[devId]['deltaDecreaseHeatSetpoint'])
                indigo.server.log("Heat setpoint decreased by %s to %s for '%s'" % (self.thermostats[devId]['deltaDecreaseHeatSetpoint'], self.thermostats[devId]['heatSetpoint'], dev.name))
            #
            # ##### End of processDecreaseHeatSetpoint #####

            #
            # ##### Now process Temperature target #####
            #
            if (self.thermostats[devId]['remoteId'] != 0) and (self.thermostats[devId]['remoteHeatSetpointControl'] == True) and (float(self.thermostats[devId]['heatSetpoint']) != float(self.thermostats[devId]['heatSetpointRemote'])):
                self.thermostats[devId]['heatSetpointRemote'] = float(self.thermostats[devId]['heatSetpoint'])
                indigo.thermostat.setHeatSetpoint(self.thermostats[devId]['remoteId'], value=float(self.thermostats[devId]['heatSetpointRemote']))  # Set Remote Heat Setpoint to Target Temperature

            if float(self.thermostats[devId]['heatSetpoint']) <= float(self.thermostats[devId]['temperature']):
                # As the required heat setpoint is not greater than the actual thermostat temperature, make sure the Stella-Z is off and not calling for heat
                if float(self.thermostats[devId]['heatSetpointStellaz']) != float(self.thermostats[devId]['heatSetpointOff']):
                    self.thermostats[devId]['heatSetpointStellaz'] = float(self.thermostats[devId]['heatSetpointOff']) # Set Heat Setpoint to Turned Off Temperature value
                    indigo.thermostat.setHeatSetpoint(self.thermostats[devId]['stellazId'], value=float(self.thermostats[devId]['heatSetpointStellaz']))

                self.lock.acquire()
                try:
                    if (self.thermostats[devId]['mode'] == "Heat On"): # Only decrement number of thermostats calling for heat if this thermostat currently calling for heat
                        self.thermostats[devId]['mode'] = "Off" 
                        if self.heaters[self.thermostats[devId]['heatingId']]['callingForHeat'] > 0:  # A check to prevent number going negative (just in case!)
                            self.heaters[self.thermostats[devId]['heatingId']]['callingForHeat'] -= 1  # Decrement number of thermostats calling for heat
                    elif (self.thermostats[devId]['mode'] == "Heat Pending"): # If heat pending - just turn off
                        self.thermostats[devId]['mode'] = "Off"
                finally:
                    self.lock.release()
            else:
                # Stella-Z should be turned on as its temperature is less than target Temperature
                self.remoteStellazDeltaMax = 0
                if self.thermostats[devId]['remoteId'] != 0:
                    self.remoteStellazDeltaMax = float(self.thermostats[devId]['remoteStellazDeltaMax'])

                if float(self.thermostats[devId]['heatSetpointStellaz']) != float(float(self.thermostats[devId]['heatSetpoint']) + float(self.remoteStellazDeltaMax)):  # + DELTA REMOTE
                    self.thermostats[devId]['heatSetpointStellaz'] = float(float(self.thermostats[devId]['heatSetpoint']) + float(self.remoteStellazDeltaMax)) # + DELTA REMOTE
                    if self.thermostats[devId]['heatSetpointStellaz'] > 50.0:
                        self.thermostats[devId]['heatSetpointStellaz'] = float(50.00)
                    indigo.thermostat.setHeatSetpoint(self.thermostats[devId]['stellazId'], value=float(self.thermostats[devId]['heatSetpointStellaz'])) # Set Stella-Z Heat Setpoint to Target Temperature + Remote Delta

                self.lock.acquire()
                try:
                    if self.thermostats[devId]['mode'] == "Off": # Only increment number of thermostats calling for heat if this thermostat not currently calling for heat
                        self.thermostats[devId]['mode'] = "Heat Pending"
                        self.thermostats[devId]['modeDatetimeChanged'] = self.currentTime
                finally:
                    self.lock.release()
            #
            # ##### End of process Temperature target #####

            #
            # ##### Now update Server states #####
            #
            if self.thermostats[devId]['scheduleAmSetup'] == True:
                self.amShow = str(self.thermostats[devId]['scheduleAmTimeOn'])[0:5] + ' - ' + str(self.thermostats[devId]['scheduleAmTimeOff'])[0:5]
            else:
                self.amShow = "(inactive)"
            dev.updateStateOnServer(key='scheduleAm', value=self.amShow)
            dev.updateStateOnServer(key='scheduleAmActive', value=self.thermostats[devId]['scheduleAmActive'])


            if self.thermostats[devId]['schedulePmSetup'] == True:
                self.pmShow = str(self.thermostats[devId]['schedulePmTimeOn'])[0:5] + ' - ' + str(self.thermostats[devId]['schedulePmTimeOff'])[0:5]
            else:
                self.pmShow = "(inactive)"
            dev.updateStateOnServer(key='schedulePm', value=self.pmShow)
            dev.updateStateOnServer(key='schedulePmActive', value=self.thermostats[devId]['schedulePmActive'])


            if indigo.devices[devId].states['advance'] != self.thermostats[devId]['advanceStatus']:
                dev.updateStateOnServer(key='advance', value=self.thermostats[devId]['advanceStatus'])

            if indigo.devices[devId].states['boost'] != self.thermostats[devId]['boostStatus']:    
                dev.updateStateOnServer(key='boost', value=self.thermostats[devId]['boostStatus'])
            if indigo.devices[devId].states['boostRequested'] != self.thermostats[devId]['boostRequested']:
                dev.updateStateOnServer(key="boostRequested", value=self.thermostats[devId]['boostRequested'])
            if str(self.thermostats[devId]['boostDateTimeEnd']) == "n/a":
                self.boostInfo = "off"
            else:
                self.boostInfo = str("%s-%s" % (str(self.thermostats[devId]['boostDateTimeStart'])[11:16], str(self.thermostats[devId]['boostDateTimeEnd'])[11:16]))
            if indigo.devices[devId].states['boostInfo'] != self.boostInfo:    
                dev.updateStateOnServer(key="boostInfo", value=self.boostInfo)


            if indigo.devices[devId].states['extend'] != self.thermostats[devId]['extendStatus']:    
                dev.updateStateOnServer(key='extend', value=self.thermostats[devId]['extendStatus'])
            if indigo.devices[devId].states['extendRequested'] != self.thermostats[devId]['extendRequested']:
                dev.updateStateOnServer(key="extendRequested", value=self.thermostats[devId]['extendRequested'])
            if str(self.thermostats[devId]['extendDateTimeEnd']) == "n/a":
                self.extendInfo = "off"
            else:
                self.extendInfo = str("%s-%s [%s]" % (str(self.thermostats[devId]['extendDateTimeStart'])[11:16], str(self.thermostats[devId]['extendDateTimeEnd'])[11:16], str(self.thermostats[devId]['extendMinutes'])))
            if indigo.devices[devId].states['extendInfo'] != self.extendInfo:    
                dev.updateStateOnServer(key="extendInfo", value=self.extendInfo)

            if indigo.devices[devId].states['heatSetpoint'] != float(self.thermostats[devId]['heatSetpoint']):
                dev.updateStateOnServer(key="heatSetpoint", value=float(self.thermostats[devId]['heatSetpoint']))
            if indigo.devices[devId].states['stellazHeatSetPoint'] != float(self.thermostats[devId]['heatSetpointStellaz']):
                dev.updateStateOnServer(key="stellazHeatSetPoint", value=float(self.thermostats[devId]['heatSetpointStellaz']))
            #
            # ##### End of update Server states #####

            return
        except StandardError, e:
            indigo.server.log(u"StandardError detected for '%s' with function '%s'. Line '%s' has error='%s'" % (indigo.devices[self.process[0]].name, self.process[1], sys.exc_traceback.tb_lineno, e), isError=True)   
    


    def startup(self):

        indigo.server.log(u"Autolog Plugin 'Stella-Z Thermostat Controller' initializing")
        self.sleep(5) # Give time for z-Wave interface to start (just in case)

        self.lock = Lock()
        self.runConcurrentProcess =""
        self.runConcurrentQueue = deque()
        self.processQueue = deque()
        self.thermostats = {}
        self.heaters = {}
        self.deviceUpdates = {}
        self.validateDeviceFlag = {}
        self.validateActionFlag = {}

        self.scheduleFrequencyCount = 0 # Used to control frequency of schedule checking

        self.limeProtectionEnabled = bool(self.pluginPrefs.get("limeProtection", True))
        self.limeProtectionScheduleId = int(self.pluginPrefs.get("limeProtectionScheduleId", 0))
        self.limeProtectionRequested = False
        self.limeProtectionActive = False
        self.limeProtectionThermostatList = ""

        self.variableFolderName = "STELLAZ"
        if (self.variableFolderName not in indigo.variables.folders):
            self.variableFolder = indigo.variables.folder.create(self.variableFolderName)
        self.variableFolderId = indigo.variables.folders.getId(self.variableFolderName)


        try:
            self.variable_callingForHeat = indigo.variables["Stella_Z_Calling_For_Heat"]
        except StandardError, e:
            try:
                self.variable_callingForHeat = indigo.variable.create("Stella_Z_Calling_For_Heat", value="false", folder=self.variableFolderId)
            except StandardError, e:
                indigo.server.log(u"StandardError detected in Plugin Startup. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e), isError=True)
        self.variableId = self.variable_callingForHeat.id   


        indigo.devices.subscribeToChanges()
        # indigo.schedules.subscribeToChanges()
        indigo.server.log(u"Autolog Plugin 'Stella-Z Thermostat Controller' initialization complete")

    


    def shutdown(self):

        self.debugLog(u"shutdown called")

    


    def heatSourceControllerDevices(self, filter="", valuesDict=None, typeId="", targetId=0):
        self.myArray = []
        for device in sorted(indigo.devices):
            if self.bypassHeatSourceControllerTypeValidation == True:
                self.myArray.append((device.id, device.name))
            else:
                if device.model == "1 Channel Boiler Actuator (SSR303 / ASR-ZW)":
                    self.myArray.append((device.id, device.name))
                elif device.model == "2 Channel Boiler Actuator (SSR302)":
                    self.myArray.append((device.id, device.name))
        # indigo.server.log(u"E = %s" % (self.myArray))

        return self.myArray


    def validateDeviceConfigUi(self, valuesDict, typeId, devId):

        self.validateDeviceFlag[devId] = {}
        self.validateDeviceFlag[devId]["edited"] = False

        self.currentTime = indigo.server.getTime()


 
        # Validate Stella-Z Thermostat
        self.validateDeviceFlag[devId]['stellazId'] = 0
        try:
            if "stellazId" in valuesDict:
                self.validateDeviceFlag[devId]['stellazId'] = int(valuesDict["stellazId"])
                if indigo.devices[self.validateDeviceFlag[devId]['stellazId']].model == "Thermostat (Stella Z)" or indigo.devices[self.validateDeviceFlag[devId]['stellazId']].model == "Setpoint Thermostat":
                    pass
                else:
                    self.validateDeviceFlag[devId]['stellazId'] = 0
        except:
            pass

        if self.validateDeviceFlag[devId]['stellazId'] == 0:
            errorDict = indigo.Dict()
            errorDict["stellazId"] = "Select a Stella-Z thermostat device"
            errorDict["showAlertText"] = "You must select a Stella-Z thermostat to monitor."
            return (False, valuesDict, errorDict)

        # Validate Heat Source Controller
        self.validateDeviceFlag[devId]['heatingId'] = 0
        try:
            if "heatingId" in valuesDict:
                self.validateDeviceFlag[devId]['heatingId'] = int(valuesDict["heatingId"])
                if self.bypassHeatSourceControllerTypeValidation == False:
                    if indigo.devices[self.validateDeviceFlag[devId]['heatingId']].model == "1 Channel Boiler Actuator (SSR303 / ASR-ZW)":
                        pass
                    elif indigo.devices[self.validateDeviceFlag[devId]['heatingId']].model ==  "2 Channel Boiler Actuator (SSR302)":
                        pass
                    else:
                        self.validateDeviceFlag[devId]['heatingId'] = 0
        except:
            pass

        if self.validateDeviceFlag[devId]['heatingId'] == 0:
            errorDict = indigo.Dict()
            errorDict["heatingId"] = "Select a Heat Source Controller device"
            errorDict["showAlertText"] = "You must select a Heat Source Controller to provide heat for the Stella-Z thermostat."
            return (False, valuesDict, errorDict)

        # Check whether to validate Remote Thermostat
        self.validateDeviceFlag[devId]['remoteSetup'] = False
        try:
            if "remoteSetup" in valuesDict:
                self.validateDeviceFlag[devId]['remoteSetup'] = bool(valuesDict["remoteSetup"])
            else:
                pass
        except:
            pass

        if self.validateDeviceFlag[devId]['remoteSetup'] == False:
            self.validateDeviceFlag[devId]['remoteId'] = 0
        else:
            # Validate Remote Thermostat
            self.validateDeviceFlag[devId]['remoteId'] = 0
            try:
                if "remoteId" in valuesDict:
                    self.validateDeviceFlag[devId]['remoteId'] = int(valuesDict["remoteId"])
            except:
                pass

            if self.validateDeviceFlag[devId]['remoteId'] == 0:
                errorDict = indigo.Dict()
                errorDict["remoteId"] = "Select a Remote thermostat device"
                errorDict["showAlertText"] = "You must select a Remote thermostat to control the Stella-Z thermostat."
                return (False, valuesDict, errorDict)

            # Validate Remote Setpoint
            self.validateDeviceFlag[devId]['remoteHeatSetpointControl'] = False
            try:
                if "remoteHeatSetpointControl" in valuesDict:
                    self.validateDeviceFlag[devId]['remoteHeatSetpointControl'] = bool(valuesDict["remoteHeatSetpointControl"])
            except:
                pass
            self.validateDeviceFlag[devId]['remoteHeatSetpointControl'] = False  # TEMPORARY (UNTIL FUNCTION FULLY IMPLEMENTED)    

            # Validate Remote Stella-Z Delta Maximum
            self.validateDeviceFlag[devId]['remoteStellazDeltaMax'] = 99
            try:
                if "remoteStellazDeltaMax" in valuesDict:
                    self.validateDeviceFlag[devId]['remoteStellazDeltaMax'] = int(valuesDict["remoteStellazDeltaMax"])
            except:
                pass

            if self.validateDeviceFlag[devId]['remoteStellazDeltaMax'] < 0 or self.validateDeviceFlag[devId]['remoteStellazDeltaMax'] > 10 or self.validateDeviceFlag[devId]['remoteStellazDeltaMax'] % 0.5 != 0:
                errorDict = indigo.Dict()
                errorDict["remoteStellazDeltaMax"] = "Delta Max must be set between 0 and 10 (inclusive)"
                errorDict["showAlertText"] = "You must enter a valid maximum number of degrees to exceed the Stella-Z Heat Setpoint for the remote thermostat. It must be set between 0 and 10 (inclusive) and a multiple of 0.5."
                return (False, valuesDict, errorDict)

        # Validate default ON temperature
        self.validateDeviceFlag[devId]['heatSetpointOn'] = 0
        try:
            if "heatSetpointOn" in valuesDict:
                self.validateDeviceFlag[devId]['heatSetpointOn'] = float(valuesDict["heatSetpointOn"])
        except:
            pass

        if self.validateDeviceFlag[devId]['heatSetpointOn'] <= 6 or self.validateDeviceFlag[devId]['heatSetpointOn'] > 50 or self.validateDeviceFlag[devId]['heatSetpointOn'] % 0.5 != 0:
            errorDict = indigo.Dict()
            errorDict["heatSetpointOn"] = "Temperature must be set between 7 and 50 (inclusive)"
            errorDict["showAlertText"] = "You must enter a valid Turn On temperature for the Stella-Z thermostat. It must be set between 7 and 50 (inclusive) and a multiple of 0.5."
            return (False, valuesDict, errorDict)

        # Validate default OFF temperature
        self.validateDeviceFlag[devId]['heatSetpointOff'] = 0
        try:
            if "heatSetpointOff" in valuesDict:
                self.validateDeviceFlag[devId]['heatSetpointOff'] = float(valuesDict["heatSetpointOff"])
        except:
            pass

        if self.validateDeviceFlag[devId]['heatSetpointOff'] <= 0 or self.validateDeviceFlag[devId]['heatSetpointOff'] > 6 or self.validateDeviceFlag[devId]['heatSetpointOff'] % 0.5 != 0:
            errorDict = indigo.Dict()
            errorDict["heatSetpointOff"] = "Temperature must be set between 1 and 6 (inclusive)"
            errorDict["showAlertText"] = "You must enter a valid Turn Off temperature for the Stella-Z thermostat. It must be set between 1 and 6 (inclusive) and a multiple of 0.5."
            return (False, valuesDict, errorDict)

        # Validate extend increment minutes
        self.validateDeviceFlag[devId]['extendIncrementMinutes'] = 0
        try:
            if "extendIncrementMinutes" in valuesDict:
                self.validateDeviceFlag[devId]['extendIncrementMinutes'] = int(valuesDict["extendIncrementMinutes"])
                if self.validateDeviceFlag[devId]['extendIncrementMinutes'] < 15 or self.validateDeviceFlag[devId]['extendIncrementMinutes'] > 60:
                    errorDict = indigo.Dict()
                    errorDict["extendIncrementMinutes"] = "The Extend Increment Minutes must be set between 15 and 60 (inclusive)"
                    errorDict["showAlertText"] = "You must enter a valid Extend Increment Minutes (length of time to increase extend by) for the Stella-Z thermostat. It must be set between 15 and 60 (inclusive)."
                    return (False, valuesDict, errorDict)
        except:
            errorDict = indigo.Dict()
            errorDict["extendIncrementMinutes"] = "The Extend Increment Minutes must be zero or a whole number of minutes"
            errorDict["showAlertText"] = str("The Extend Increment Minutes [%s] must be zero or a whole number of minutes." % (valuesDict["extendIncrementMinutes"]))
            return (False, valuesDict, errorDict)





        # Validate extend increment minutes
        self.validateDeviceFlag[devId]['extendMaximumMinutes'] = 0
        try:
            if "extendMaximumMinutes" in valuesDict:
                self.validateDeviceFlag[devId]['extendMaximumMinutes'] = int(valuesDict["extendMaximumMinutes"])
                if self.validateDeviceFlag[devId]['extendIncrementMinutes'] < 15 or self.validateDeviceFlag[devId]['extendIncrementMinutes'] > 180:
                    errorDict = indigo.Dict()
                    errorDict["extendIncrementMinutes"] = "The Extend Maximum Minutes must be set between 15 and 180 (inclusive)"
                    errorDict["showAlertText"] = "You must enter a valid Extend Maximum Minutes (maximum length of time to extend by) for the Stella-Z thermostat. It must be set between 15 and 180 (inclusive)."
                    return (False, valuesDict, errorDict)
        except:
            errorDict = indigo.Dict()
            errorDict["extendMaximumMinutes"] = "The Extend Maximum Minutes must be whole number of minutes"
            errorDict["showAlertText"] = str("The Extend Maximum Minutes [%s] must be a whole number of minutes." % (valuesDict["extendMaximumMinutes"]))
            return (False, valuesDict, errorDict)

        # Check extend values are consistent

        tempIncrement = self.validateDeviceFlag[devId]['extendIncrementMinutes']
        tempMaximum = self.validateDeviceFlag[devId]['extendMaximumMinutes']
        if tempMaximum != 0 and tempIncrement != 0:
            quotient, remainder = divmod(tempMaximum, tempIncrement)
            if remainder != 0:
                errorDict = indigo.Dict()
                errorDict["extendIncrementMinutes"] = "The Extend Increment Minutes must be an exact multiple of Extend Maximum Minutes"
                errorDict["extendMaximumMinutes"] = "The Extend Maximum Minutes must be exactly divisible by the Extend Increment Minutes"
                errorDict["showAlertText"] = str("The Extend Maximum Minutes [%s] must be exactly divisible by the Extend Increment Minutes [%s] - it isn't!." % (str(tempMaximum), str(tempIncrement)))
                return (False, valuesDict, errorDict)
            else:
                if tempIncrement > tempMaximum:
                    errorDict = indigo.Dict()
                    errorDict["extendIncrementMinutes"] = "The Extend Increment Minutes must not be greater than the Extend Maximum Minutes"
                    errorDict["extendMaximumMinutes"] = "The Extend Maximum Minutes must not be less than the Extend Increment Minutes"
                    errorDict["showAlertText"] = str("The Extend Increment Minutes [%s] must not be greater than the Extend Maximum Minutes [%s]." % (str(tempIncrement), str(tempMaximum)))
                    return (False, valuesDict, errorDict)
        else:
            if tempMaximum == 0 and tempIncrement == 0:
                pass
            else:
                if tempMaximum == 0:
                    errorDict = indigo.Dict()
                    errorDict["extendIncrementMinutes"] = "The Extend Increment Minutes is defined but the Extend Maximum Minutes is zero minutes"
                    errorDict["extendMaximumMinutes"] = "The Extend Maximum Minutes is zero but the Extend Increment Minutes is defined"
                    errorDict["showAlertText"] = str("The Extend Maximum Minutes [%s] is zero minutes but must be specified as the Extend Increment Minutes [%s] is defined. Both must be defined or zero." % (str(tempMaximum), str(tempIncrement)))
                    return (False, valuesDict, errorDict)

                else:
                    errorDict = indigo.Dict()
                    errorDict["extendIncrementMinutes"] = "The Extend Increment Minutes is zero minutes but the Extend Maximum Minutes is defined"
                    errorDict["extendMaximumMinutes"] = "The Extend Maximum Minutes is defined but the Extend Increment Minutes is zero minutes"
                    errorDict["showAlertText"] = str("The Extend Increment Minutes [%s] is zero minutes but must be specified as the Extend Maximum Minutes [%s] is defined. Both must be defined or zero." % (str(tempIncrement), str(tempMaximum)))
                    return (False, valuesDict, errorDict)



        # Validate Boost Delta temperature
        self.validateDeviceFlag[devId]['boostDelta'] = 0
        try:
            if "boostDelta" in valuesDict:
                self.validateDeviceFlag[devId]['boostDelta'] = float(valuesDict["boostDelta"])
        except:
            pass

        if self.validateDeviceFlag[devId]['boostDelta'] <= 0 or self.validateDeviceFlag[devId]['boostDelta'] > 5 or self.validateDeviceFlag[devId]['boostDelta'] % 0.5 != 0:
            errorDict = indigo.Dict()
            errorDict["boostDelta"] = "Boost Delta must be set between 1 and 5 (inclusive)"
            errorDict["showAlertText"] = "You must enter a valid Boost Delta (amount to increase temperature by) for the Stella-Z thermostat. It must be set between 1 and 5 (inclusive) and a multiple of 0.5"
            return (False, valuesDict, errorDict)

        # Validate Boost Minutes
        self.validateDeviceFlag[devId]['boostMinutes'] = 0
        try:
            if "boostMinutes" in valuesDict:
                self.validateDeviceFlag[devId]['boostMinutes'] = int(valuesDict["boostMinutes"])
                if self.validateDeviceFlag[devId]['boostMinutes'] < 10 or self.validateDeviceFlag[devId]['boostMinutes'] > 180:
                    errorDict = indigo.Dict()
                    errorDict["boostMinutes"] = "Boost Minutes must be set between 10 and 180 (inclusive)"
                    errorDict["showAlertText"] = "You must enter a valid Boost Minutes (length of time for boost to run) for the Stella-Z thermostat. It must be set between 10 and 180 (inclusive)."
                    return (False, valuesDict, errorDict)
        except:
            errorDict = indigo.Dict()
            errorDict["boostMinutes"] = "The Boost Minutes must be a whole number of minutes"
            errorDict["showAlertText"] = str("The Boost Minutes [%s] must be a whole number of minutes." % (valuesDict["extendIncrementMinutes"]))
            return (False, valuesDict, errorDict)

        # Check whether to validate AM Schedule
        self.validateDeviceFlag[devId]['scheduleAmSetup'] = False
        try:
            if "scheduleAmSetup" in valuesDict:
                self.validateDeviceFlag[devId]['scheduleAmSetup'] = bool(valuesDict["scheduleAmSetup"])
        except:
            pass

        self.validateDeviceFlag[devId]['scheduleAmTimeOn'] = 0
        self.validateDeviceFlag[devId]['scheduleAmTimeOff'] = 0
        self.validateDeviceFlag[devId]['heatSetpointAm'] = 0

        if self.validateDeviceFlag[devId]['scheduleAmSetup'] == True:
            # Validate Schedule AM ON
            try:
                if "scheduleAmTimeOn" in valuesDict:
                    self.validateDeviceFlag[devId]['scheduleAmTimeOn'] = autologdatetime.strptime(valuesDict["scheduleAmTimeOn"], '%H:%M')
            except:
                pass

            if self.validateDeviceFlag[devId]['scheduleAmTimeOn'] == 0:
                errorDict = indigo.Dict()
                errorDict["scheduleAmTimeOn"] = "Select an AM ON Time (hh:mm)"
                errorDict["showAlertText"] = "You must enter a time (hh:mm) for when the Stella-Z thermostat will turn ON."
                return (False, valuesDict, errorDict)

            # Validate Schedule AM OFF
            try:
                if "scheduleAmTimeOff" in valuesDict:
                    self.validateDeviceFlag[devId]['scheduleAmTimeOff'] = autologdatetime.strptime(valuesDict["scheduleAmTimeOff"], '%H:%M')
            except:
                pass

            if self.validateDeviceFlag[devId]['scheduleAmTimeOff'] == 0:
                errorDict = indigo.Dict()
                errorDict["scheduleAmTimeOff"] = "Select an AM OFF Time (hh:mm)"
                errorDict["showAlertText"] = "You must enter a time (hh:mm) for when the Stella-Z thermostat will turn OFF."
                return (False, valuesDict, errorDict)

            # Validate AM Heat Setpoint
            self.validateDeviceFlag[devId]['heatSetpointAm'] = 0
            try:
                if "heatSetpointAm" in valuesDict:
                    self.validateDeviceFlag[devId]['heatSetpointAm'] = float(valuesDict["heatSetpointAm"])
            except:
                pass

            if self.validateDeviceFlag[devId]['heatSetpointAm'] <= 6 or self.validateDeviceFlag[devId]['heatSetpointAm'] > 50 or self.validateDeviceFlag[devId]['heatSetpointAm'] % 0.5 != 0:
                errorDict = indigo.Dict()
                errorDict["heatSetpointAm"] = "Temperature must be set between 7 and 50 (inclusive)"
                errorDict["showAlertText"] = "You must enter a valid AM heat setpoint for the Stella-Z thermostat. It must be set between 7 and 50 (inclusive) and a multiple of 0.5."
                return (False, valuesDict, errorDict)

            # Check AM Schedule Times consistent

            tempOn = autologdatetime.combine(self.currentTime, self.validateDeviceFlag[devId]['scheduleAmTimeOn'].time())
            tempOff = autologdatetime.combine(self.currentTime, self.validateDeviceFlag[devId]['scheduleAmTimeOff'].time())
            if tempOff > tempOn:
                tempDelta = tempOff - tempOn
                minutes, seconds = divmod(tempDelta.seconds, 60)
            else:
                minutes = 0
        
            if minutes < 10:
                errorDict = indigo.Dict()
                errorDict["scheduleAmTimeOn"] = "The AM heating On time must be at least 10 minutes before the Off time"
                errorDict["scheduleAmTimeOff"] = "The AM heating Off time must be at least 10 minutes after the On time"
                errorDict["showAlertText"] = str("The On time [%s] must be before the Off time [%s] and there must be at least 10 minutes between the On and Off time for the AM heating period for the Stella-Z thermostat." % (str(tempOn)[11:16], str(tempOff)[11:16]))
                return (False, valuesDict, errorDict)

            self.validateDeviceFlag[devId]['scheduleAmSetup'] = True

        # Check whether to validate PM Schedule
        self.validateDeviceFlag[devId]['schedulePmSetup'] = False
        try:
            if "schedulePmSetup" in valuesDict:
                self.validateDeviceFlag[devId]['schedulePmSetup'] = bool(valuesDict["schedulePmSetup"])
        except:
            pass

        self.validateDeviceFlag[devId]['schedulePmTimeOn'] = 0
        self.validateDeviceFlag[devId]['schedulePmTimeOff'] = 0
        self.validateDeviceFlag[devId]['heatSetpointPm'] = 0

        if self.validateDeviceFlag[devId]['schedulePmSetup'] == True:
            # Validate Schedule PM ON
            try:
                if "schedulePmTimeOn" in valuesDict:
                    self.validateDeviceFlag[devId]['schedulePmTimeOn'] = autologdatetime.strptime(valuesDict["schedulePmTimeOn"], '%H:%M')
            except:
                pass

            if self.validateDeviceFlag[devId]['schedulePmTimeOn'] == 0:
                errorDict = indigo.Dict()
                errorDict["schedulePmTimeOn"] = "Select a PM ON Time (hh:mm)"
                errorDict["showAlertText"] = "You must enter a time (hh:mm) for when the Stella-Z thermostat will turn ON."
                return (False, valuesDict, errorDict)

            # Validate Schedule AM OFF
            try:
                if "schedulePmTimeOff" in valuesDict:
                    self.validateDeviceFlag[devId]['schedulePmTimeOff'] = autologdatetime.strptime(valuesDict["schedulePmTimeOff"], '%H:%M')
            except:
                pass

            if self.validateDeviceFlag[devId]['schedulePmTimeOff'] == 0:
                errorDict = indigo.Dict()
                errorDict["schedulePmTimeOff"] = "Select a PM OFF Time (hh:mm)"
                errorDict["showAlertText"] = "You must enter a time (hh:mm) for when the Stella-Z thermostat will turn OFF."
                return (False, valuesDict, errorDict)

            # Validate AM Heat Setpoint
            self.validateDeviceFlag[devId]['heatSetpointPm'] = 0
            try:
                if "heatSetpointPm" in valuesDict:
                    self.validateDeviceFlag[devId]['heatSetpointPm'] = float(valuesDict["heatSetpointPm"])
            except:
                pass

            if self.validateDeviceFlag[devId]['heatSetpointPm'] <= 6 or self.validateDeviceFlag[devId]['heatSetpointPm'] > 50 or self.validateDeviceFlag[devId]['heatSetpointPm'] % 0.5 != 0:
                errorDict = indigo.Dict()
                errorDict["heatSetpointPm"] = "Temperature must be set between 7 and 50 (inclusive)"
                errorDict["showAlertText"] = "You must enter a valid PM heat setpoint for the Stella-Z thermostat. It must be set between 7 and 50 (inclusive) and a multiple of 0.5."
                return (False, valuesDict, errorDict)

            # Check PM Schedule Times consistent

            tempOn = autologdatetime.combine(self.currentTime, self.validateDeviceFlag[devId]['schedulePmTimeOn'].time())
            tempOff = autologdatetime.combine(self.currentTime, self.validateDeviceFlag[devId]['schedulePmTimeOff'].time())
            if tempOff > tempOn:
                tempDelta = tempOff - tempOn
                minutes, seconds = divmod(tempDelta.seconds, 60)
            else:
                minutes = 0
        
            if minutes < 10:
                errorDict = indigo.Dict()
                errorDict["schedulePmTimeOn"] = "The PM heating On time must be at least 10 minutes before the Off time"
                errorDict["schedulePmTimeOff"] = "The PM heating Off time must be at least 10 minutes after the On time"
                errorDict["showAlertText"] = str("The On time [%s] must be before the Off time [%s] and there must be at least 10 minutes between the On and Off time for the PM heating period for the Stella-Z thermostat." % (str(tempOn)[11:16], str(tempOff)[11:16]))
                return (False, valuesDict, errorDict)

            self.validateDeviceFlag[devId]['schedulePmSetup'] = True
 
            # If both AM and PM schedules specified - Check Schedule Times consistent
            if self.validateDeviceFlag[devId]['scheduleAmSetup'] == True and self.validateDeviceFlag[devId]['schedulePmSetup'] == True:
                tempOff = autologdatetime.combine(self.currentTime, self.validateDeviceFlag[devId]['scheduleAmTimeOff'].time())  # AM Off
                tempOn = autologdatetime.combine(self.currentTime, self.validateDeviceFlag[devId]['schedulePmTimeOn'].time())    # PM on
                if tempOff > tempOn:
                    errorDict = indigo.Dict()
                    errorDict["scheduleAmOffId"] = "The AM heating Off time must end before the PM heating On time"
                    errorDict["schedulePmOnId"] = "The PM heating On time must start after the AM heating Off time"
                    errorDict["showAlertText"] = str("The AM heating Off time [%s] must be before the PM heating On time [%s] for the Stella-Z thermostat." % (str(tempOff)[11:16], str(tempOn)[11:16]))
                    return (False, valuesDict, errorDict)

        self.validateDeviceFlag[devId]["edited"] = True

        return (True, valuesDict)
    


    def deviceStartComm(self, dev):

        self.currentTime = indigo.server.getTime()

        devId = dev.id

        self.validateDeviceFlag[devId] = {}
        self.validateDeviceFlag[devId]["edited"] = False

        self.thermostats[devId] = {}
        self.thermostats[devId]["datetimeStarted"] = self.currentTime
        # indigo.server.log(u"Starting '%s' at %s" % (dev.name, self.thermostats[devId]["datetimeStarted"]))

        try:
            self.thermostats[devId]['hideTempBroadcast'] = bool(dev.pluginProps['hideTempBroadcast'])  # Hide Temperature Broadcast in Event Log Flag
        except:
            self.thermostats[devId]['hideTempBroadcast'] = False

        self.thermostats[devId]['stellazId'] = int(dev.pluginProps['stellazId'])  # ID of Stella-Z Thermostat device
        self.thermostats[devId]['heatingId'] = int(dev.pluginProps['heatingId'])  # ID of Heat Source Controller device

        if self.thermostats[devId]['heatingId'] not in self.heaters.keys():
            self.heaters[self.thermostats[devId]['heatingId']] = {}
            self.heaters[self.thermostats[devId]['heatingId']]['callingForHeat'] = 0

            self.heaters[self.thermostats[devId]['heatingId']]['deviceType'] = 0
            try:
                # indigo.server.log(u"Info [A] from Autolog Plugin deviceStartComm [%s]=%s" % (dev.name, self.thermostats[devId]['heatingId']),)
                indigo.devices[self.thermostats[devId]['heatingId']].hvacMode
                self.heaters[self.thermostats[devId]['heatingId']]['deviceType'] = 1  # hvac
            #  except NameError:
            except AttributeError,e:
                # indigo.server.log(u"Error [A] detected in Autolog Plugin deviceStartComm [%s]" % (dev.name), isError=True)
                # indigo.server.log(u"  Error message: '%s'" % (e), isError=True)   
                try:
                    # indigo.server.log(u"Info [B] from Autolog Plugin deviceStartComm [%s]=%s" % (dev.name, self.thermostats[devId]['heatingId']),)
                    indigo.devices[self.thermostats[devId]['heatingId']].onState
                    self.heaters[self.thermostats[devId]['heatingId']]['deviceType'] = 2  # relay device
                #  except NameError:
                except AttributeError,e:
                    # indigo.server.log(u"Error [B] detected in Autolog Plugin deviceStartComm [%s]" % (dev.name), isError=True)
                    # indigo.server.log(u"  Error message: '%s'" % (e), isError=True)
                    indigo.server.log(u"Error detected in Autolog Plugin deviceStartComm for device [%s] - Unknown Heating Source Device Type, ID=%s" % (dev.name, self.thermostats[devId]['heatingId']), isError=True)
                    pass
                                 
        self.thermostats[devId]['remoteSetup'] = dev.pluginProps['remoteSetup']
        if self.thermostats[devId]['remoteSetup'] == False:
            self.thermostats[devId]['remoteId'] = 0
        else:
            try:
                self.thermostats[devId]['remoteId'] = int(dev.pluginProps['remoteId'])   # ID of Remote Thermostat device
            except:
                self.thermostats[devId]['remoteId'] = 0


        # testSchedule = [[['06:45','07:30'],['12:15','13:45'],['19:00','22:45']],[['06:45','07:30'],['12:15','13:45'],['19:00','22:45']],[['06:45','07:30'],['12:15','13:45'],['19:00','22:45']],[['06:45','07:30'],['12:15','13:45'],['19:00','22:45']],[['06:45','07:30'],['12:15','13:45'],['19:00','22:45']],[['06:45','07:30'],['12:15','13:45'],['19:00','22:45']],[['06:45','07:30'],['12:15','13:45'],['19:00','22:45']]]




        self.thermostats[devId]['heatSetpointOn'] = float(dev.pluginProps['heatSetpointOn'])
        self.thermostats[devId]['heatSetpointOff'] = float(dev.pluginProps['heatSetpointOff'])
        self.thermostats[devId]['boostDelta'] = float(dev.pluginProps['boostDelta'])
        self.thermostats[devId]['boostMinutes'] = int(dev.pluginProps['boostMinutes'])

        self.thermostats[devId]['scheduleAmSetup'] = dev.pluginProps['scheduleAmSetup']
        if self.thermostats[devId]['scheduleAmSetup'] == False:
            self.thermostats[devId]['scheduleAmTimeOn'] = 0
            self.thermostats[devId]['scheduleAmTimeOff'] = 0
            self.thermostats[devId]['heatSetpointAm'] = 0.0
            dev.updateStateOnServer(key='heatSetpointAm', value="")
        else:
            try:
                self.thermostats[devId]['scheduleAmTimeOn'] = autologdatetime.strptime(dev.pluginProps['scheduleAmTimeOn'], '%H:%M').time()
                self.thermostats[devId]['scheduleAmTimeOff'] = autologdatetime.strptime(dev.pluginProps['scheduleAmTimeOff'], '%H:%M').time()
                self.thermostats[devId]['heatSetpointAm'] = float(dev.pluginProps['heatSetpointAm'])
                dev.updateStateOnServer(key='heatSetpointAm', value=str("%s C" % (self.thermostats[devId]['heatSetpointAm'])))
            except:
                self.thermostats[devId]['scheduleAmSetup'] = False
                self.thermostats[devId]['scheduleAmTimeOn'] = 0
                self.thermostats[devId]['scheduleAmTimeOff'] = 0
                self.thermostats[devId]['heatSetpointAm'] = 0.0
                dev.updateStateOnServer(key='heatSetpointAm', value="")
                
        self.thermostats[devId]['schedulePmSetup'] = dev.pluginProps['schedulePmSetup']
        if self.thermostats[devId]['schedulePmSetup'] == False:
            self.thermostats[devId]['schedulePmTimeOn'] = 0
            self.thermostats[devId]['schedulePmTimeOff'] = 0
            self.thermostats[devId]['heatSetpointPm'] = 0.0
            dev.updateStateOnServer(key='heatSetpointPm', value="")
        else:
            try:
                self.thermostats[devId]['schedulePmTimeOn'] = autologdatetime.strptime(dev.pluginProps['schedulePmTimeOn'], '%H:%M').time()
                self.thermostats[devId]['schedulePmTimeOff'] = autologdatetime.strptime(dev.pluginProps['schedulePmTimeOff'], '%H:%M').time()
                self.thermostats[devId]['heatSetpointPm'] = float(dev.pluginProps['heatSetpointPm'])
                dev.updateStateOnServer(key='heatSetpointPm', value=str("%s C" % (self.thermostats[devId]['heatSetpointPm'])))
            except:
                self.thermostats[devId]['schedulePmSetup'] = False
                self.thermostats[devId]['schedulePmTimeOn'] = 0
                self.thermostats[devId]['schedulePmTimeOff'] = 0
                self.thermostats[devId]['heatSetpointPm'] = 0.0
                dev.updateStateOnServer(key='heatSetpointPm', value="")

        self.thermostats[devId]['scheduleResetAmTimeOn']  = self.thermostats[devId]['scheduleAmTimeOn'] 
        self.thermostats[devId]['scheduleResetAmTimeOff'] = self.thermostats[devId]['scheduleAmTimeOff'] 
        self.thermostats[devId]['scheduleResetPmTimeOn']  = self.thermostats[devId]['schedulePmTimeOn'] 
        self.thermostats[devId]['scheduleResetPmTimeOff'] = self.thermostats[devId]['schedulePmTimeOff'] 

        self.thermostats[devId]['scheduleAmFired'] = False
        self.thermostats[devId]['schedulePmFired'] = False
        self.thermostats[devId]['scheduleAmActive'] = False
        self.thermostats[devId]['schedulePmActive'] = False

        self.thermostats[devId]['advanceStatus'] = "off"
        dev.updateStateOnServer(key='advance', value=self.thermostats[devId]['advanceStatus'])
        self.thermostats[devId]['advanceSetDatetime'] = 0

        self.thermostats[devId]['boostDateTimeEnd'] = "n/a"
        self.thermostats[devId]['boostDateTimeStart'] = "n/a"
        self.thermostats[devId]['boostRequested'] = False
        self.thermostats[devId]['boostStatus'] = "off"

        self.thermostats[devId]['deviceStartDatetime'] = str(self.currentTime)

        self.thermostats[devId]['extendIncrementMinutes'] = int(dev.pluginProps['extendIncrementMinutes']) 
        self.thermostats[devId]['extendMaximumMinutes'] = int(dev.pluginProps['extendMaximumMinutes'])
        self.thermostats[devId]['extendMinutes'] = 0
        self.thermostats[devId]['extendRequested'] = False
        self.thermostats[devId]['extendDateTimeEnd'] = "n/a"
        self.thermostats[devId]['extendDateTimeStart'] = "n/a"
        self.thermostats[devId]['extendStatus'] = "off"

        self.thermostats[devId]['heatSetpoint'] = 0                
        self.thermostats[devId]['heatSetpointAdvance'] = 0
        self.thermostats[devId]['heatSetpointBoost'] = 0
        self.thermostats[devId]['heatSetpointStellaz'] = 0
        self.thermostats[devId]['mode'] = "Off"
        self.thermostats[devId]['modeDatetimeChanged'] = self.currentTime

        self.thermostats[devId]['temperatureStellaz'] = float(indigo.devices[int(self.thermostats[devId]['stellazId'])].temperatures[0])

        self.thermostats[devId]['temperatureRemote'] = float(0.0)
        if self.thermostats[devId]['remoteId'] != 0:
            try:
                self.thermostats[devId]['temperatureRemote'] = float(indigo.devices[int(self.thermostats[devId]['remoteId'])].temperatures[0])
            except AttributeError:
                try:
                    self.thermostats[devId]['temperatureRemote'] = float(indigo.devices[int(self.thermostats[devId]['remoteId'])].states['sensorValue'])  # Aeon 4 in 1 / Fibaro FGMS-001
                except (AttributeError, KeyError):
                    try:
                        self.thermostats[devId]['temperatureRemote'] = float(indigo.devices[int(self.thermostats[devId]['remoteId'])].states['temperature'])  # Oregon Scientific Temp Sensor
                    except (AttributeError, KeyError):
                        try:
                            self.thermostats[devId]['temperatureRemote'] = float(indigo.devices[int(self.thermostats[devId]['remoteId'])].states['Temperature'])  # Netatmo
                        except (AttributeError, KeyError):
                            indigo.server.log(u"'%s' is an unknown Remote Thermostat type - remote support disabled." % (indigo.devices[self.thermostats[devId]['remoteId']].name), isError=True)
                            self.thermostats[devId]['remoteId'] = 0  # Disable Remote Support 

        try:
            self.thermostats[devId]['remoteHeatSetpointControl'] = dev.pluginProps['remoteHeatSetpointControl']
        except:
            self.thermostats[devId]['remoteHeatSetpointControl'] = False

        self.thermostats[devId]['heatSetpointRemote'] = 0
        if self.thermostats[devId]['remoteId'] == 0:
            self.thermostats[devId]['remoteHeatSetpointControl'] = False
            self.thermostats[devId]['temperature'] = float(self.thermostats[devId]['temperatureStellaz'])
        else:
            self.thermostats[devId]['temperature'] = float(self.thermostats[devId]['temperatureRemote'])
            self.thermostats[devId]['remoteStellazDeltaMax'] = float(dev.pluginProps['remoteStellazDeltaMax'])
            if self.thermostats[devId]['remoteHeatSetpointControl'] == True:
                try:
                    self.thermostats[devId]['heatSetpointRemote'] = float(indigo.devices[int(self.thermostats[devId]['remoteId'])].heatSetpoint)
                except:
                    self.thermostats[devId]['remoteHeatSetpointControl'] = False     

        self.thermostats[devId]['temperatureHistory'] = ""

        self.thermostats[devId]['zwaveEventCount'] = 0
        self.thermostats[devId]['zwaveEventCountPrevious'] = 0
        self.thermostats[devId]['zwaveDeltaCurrent'] = "[n/a]"
        dev.updateStateOnServer("updatetime", self.thermostats[devId]['zwaveDeltaCurrent'])
        self.thermostats[devId]['zwaveDatetime'] = str(self.currentTime)[0:19]
        dev.updateStateOnServer("lastupdated", self.thermostats[devId]['zwaveDatetime'][-8:])
        self.thermostats[devId]['zwaveWakeupDelay'] = False
        self.thermostats[devId]['zwaveWakeupInterval'] = int(indigo.devices[self.thermostats[devId]['stellazId']].globalProps["com.perceptiveautomation.indigoplugin.zwave"]["zwWakeInterval"])

        
        self.thermostats[devId]['zwaveRemoteMonitoringEnabled'] = False  # Set to TRUE in device spec?
        self.thermostats[devId]['zwaveRemoteEventCount'] = 0
        self.thermostats[devId]['zwaveRemoteEventCountPrevious'] = 0
        self.thermostats[devId]['zwaveRemoteDeltaCurrent'] = "[n/a]"
        dev.updateStateOnServer("timestamp", self.thermostats[devId]['zwaveRemoteDeltaCurrent'])
        self.thermostats[devId]['zwaveRemoteDatetime'] = str(self.currentTime)[0:19]
        dev.updateStateOnServer("updatetimestamp", self.thermostats[devId]['zwaveRemoteDatetime'][-8:])
        self.thermostats[devId]['zwaveRemoteWakeupDelay'] = False
        if self.thermostats[devId]['remoteId'] != 0:
            if indigo.devices[self.thermostats[devId]['remoteId']].protocol == indigo.kProtocol.ZWave:
                try:
                    self.thermostats[devId]['zwaveRemoteWakeupInterval'] = int(indigo.devices[self.thermostats[devId]['remoteId']].globalProps["com.perceptiveautomation.indigoplugin.zwave"]["zwWakeInterval"])
                except:
                    self.thermostats[devId]['zwaveRemoteWakeupInterval'] = int(0)
            else:
                # indigo.server.log("Protocol for device %s is '%s'" % (indigo.devices[self.thermostats[devId]['remoteId']].name, indigo.devices[self.thermostats[devId]['remoteId']].protocol))
                self.thermostats[devId]['zwaveRemoteWakeupInterval'] = int(0)
        else:
            self.thermostats[devId]['zwaveRemoteWakeupInterval'] = int(0)
        self.thermostats[devId]['processLimeProtection'] = 'off'
        self.thermostats[devId]['limeProtectionCheckTime'] = 0
        self.thermostats[devId]['valueSetHeatSetpoint'] = 0.0
        self.thermostats[devId]['deltaIncreaseHeatSetpoint'] = 0.0
        self.thermostats[devId]['deltaIDecreaseHeatSetpoint'] = 0.0

        self.lock.acquire()
        try:
            if int(self.thermostats[devId]['stellazId']) not in self.deviceUpdates.keys():
                self.deviceUpdates[self.thermostats[devId]['stellazId']] = {}

            self.deviceUpdates[self.thermostats[devId]['stellazId']]['type'] = 'stellaz'
            self.deviceUpdates[self.thermostats[devId]['stellazId']]['autologDeviceId'] = int(devId)
            self.deviceUpdates[self.thermostats[devId]['stellazId']]['temperature'] = float(self.thermostats[devId]['temperatureStellaz'])

            if self.thermostats[devId]['remoteId'] != "" and int(self.thermostats[devId]['remoteId']) != 0:
                if int(self.thermostats[devId]['remoteId']) not in self.deviceUpdates.keys():
                    self.deviceUpdates[self.thermostats[devId]['remoteId']] = {}
                self.deviceUpdates[self.thermostats[devId]['remoteId']]['type'] = 'remote'
                self.deviceUpdates[self.thermostats[devId]['remoteId']]['autologDeviceId'] = int(devId)
                self.deviceUpdates[self.thermostats[devId]['remoteId']]['temperature'] = float(self.thermostats[devId]['temperatureRemote'])
        finally:
            self.lock.release()

        self._processThermostat(indigo.devices[devId], 'processEstablishState')

        try:
            if self.thermostats[devId]['remoteId'] != "" and int(self.thermostats[devId]['remoteId']) != 0:
                indigo.server.log(u"Started '%s': Controlling Stella-Z '%s'; Remote thermostat '%s'; Heat Source '%s'" % (dev.name, indigo.devices[int(self.thermostats[devId]['stellazId'])].name,indigo.devices[int(self.thermostats[devId]['remoteId'])].name,indigo.devices[int(self.thermostats[devId]['heatingId'])].name))
            else:
                indigo.server.log(u"Started '%s': Controlling Stella-Z '%s'; Heat Source '%s'" % (dev.name, indigo.devices[int(self.thermostats[devId]['stellazId'])].name,indigo.devices[int(self.thermostats[devId]['heatingId'])].name))
        except:
            indigo.server.log("StellazProps ERROR AGAIN!!!!", isError=True)

        self._refreshStatesFromStellaz(dev, False, False)

        return

    


    def deviceStopComm(self, dev):

        indigo.server.log("Stopping '%s'" % (dev.name))

    


