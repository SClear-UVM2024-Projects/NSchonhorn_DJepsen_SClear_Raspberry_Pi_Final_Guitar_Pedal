#Import libraries needed to make everything work
import RPi.GPIO as GPIO
import time
from pyo import *

#Set up GPIO pins for pedal input and LED output
INPUT_PIN = 17
INPUT_PIN_2 = 22
OUTPUT_PIN = 27

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(INPUT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(INPUT_PIN_2, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(OUTPUT_PIN, GPIO.OUT)

lastButtonState = False
currentButtonState = False
lastButtonState2 = False
currentButtonState2 = False

#Start Pyo server to open audio inputs and get ready to pass through Pyo classes
s = Server()
s.setInputDevice(1)
s.setOutputDevice(1)
s.boot()
s.start()

delayRate = 0.0

#Flanger class implementation adapted from here: http://ajaxsoundstudio.com/pyodoc/tutorials/pyoobject2.html
class Flanger(PyoObject):
    def __init__(self, input, depth=0.75, lfofreq=0.2, feedback=0.5, mul=1, add=0):
        #Initialize PyoObject basic attributes
        PyoObject.__init__(self)

        #Keep references of arguments
        self._input = input
        self._depth = depth
        self._lfofreq = lfofreq
        self._feedback = feedback

        #Using InputFader to manage input allows crossfade when changing sources
        self._in_fader = InputFader(input)

        #Convert args to lists
        in_fader, depth, lfofreq, feedback, mul, add, lmax = convertArgsToLists(self._in_fader, depth, lfofreq, feedback, mul, add)

        #Apply processing
        self._modamp = Sig(depth, mul=0.005)
        self._mod = Sine(freq=lfofreq, mul=self._modamp, add=0.005)
        self._dls = Delay(in_fader, delay=self._mod, feedback=feedback)
        self._flange = Interp(in_fader, self._dls, mul=mul, add=add)

        #Set up audio output
        self._base_objs = self._flange.getBaseObjects()

    def setInput(self, x, fadetime=0.05):
        #Replaces the input attribute
        self._input = x
        self._in_fader.setInput(x, fadetime)

    def setDepth(self, x):
        #Replaces the depth attribute
        self._depth = x
        self._modamp.value = x

    def setLfoFreq(self, x):
        #Replaces lfofreq attribute
        self._lfofreq = x
        self._mod.freq = x

    def setFeedback(self, x):
        #Replaces feedback attribute
        self._feedback = x
        self._dls.feedback = x

    #Getters and setters for all of the member variables
    @property
    def input(self):
        return self._input
    @input.setter
    def input(self, x):
        self.setInput(x)

    @property
    def depth(self):
        return self._depth
    @depth.setter
    def depth(self, x):
        self.setDepth(x)

    @property
    def lfofreq(self):
        return self._lfofreq
    @lfofreq.setter
    def lfofreq(self, x):
        self.setLfoFreq(x)

    @property
    def feedback(self):
        return self._feedback
    @feedback.setter
    def feedback(self, x):
        self.setFeedback(x)

    #Overriden methods from the base PyoObject to make sure that everything is workingh correctly.
    #This one is to make sure controls work properly when used from the GUI, not relevant to headless usage sadly
    def ctrl(self, map_list=None, title=None, wxnoserver=False):
        self._map_list = [SLMap(0., 1., "lin", "depth", self._depth), SLMap(0.001, 20., "log", "lfofreq", self._lfofreq), SLMap(0., 1., "lin", "feedback", self._feedback), SLMapMul(self._mul)]
        PyoObject.ctrl(self, map_list, title, wxnoserver)

    #The following three methods are reponsible for starting and stopping audio output
    def play(self, dur=0, delay=0):
        self._modamp.play(dur, delay)
        self._mod.play(dur, delay)
        self.dls.play(dur, delay)
        return PyoObject.play(self, dur, delay)

    def stop(self, wait=0):
        self._modamp.stop(wait)
        self._mod.stop(wait)
        self._dls.stop(wait)
        return PyoObject.stop(self, wait)

    def out(self, chnl=0, inc=1, dur=0, delay=0):
        self._modamp.play(dur, delay)
        self._mod.play(dur, delay)
        self._dls.play(dur, delay)
        return PyoObject.out(self, chnl, inc, dur, delay)

#Initialize the clean channel, and all "PyoObject"s needed to make the effects work
#This is a combo of straight forward effects from the Pyo library, custom classes, and PyoObjects used to control inputs on some of the effects
a = Input(chnl=0).out()
b = Input(chnl=0)
chorus = Chorus(b, depth=1.2, feedback=.6, bal=0.5).out()
distr = Disto(b, slope=.3, mul=.65).out()
reverb = STRev(b, revtime=1.8, roomSize=1.2).out()
delay = Delay(b, delay=.6, feedback=.3, maxdelay=.8).out()
freqShift = FreqShift(b, shift=200, mul=1).out()
flanger = Flanger(b, depth=.875, lfofreq=.325).out()
fol = Follower(b, freq=30, mul=4000, add=40)
envelope = Biquad(b, freq=fol, q=5, type=2).out()
tremfreq = Sine(freq=6)
tremolo = Chorus(b, depth=.1, feedback=.2, bal=0.5, mul=tremfreq).out()
freq = FreqShift(b, shift=fol, mul=1, add=0).out()

#Stop everything before outputting so that there are no issues when the
#program drops into the main loop
a.out()
chorus.stop()
distr.stop()
reverb.stop()
delay.stop()
freqShift.stop()
flanger.stop()
envelope.stop()
tremolo.stop()
freq.stop()

#Throw all of the output effects into an array to index through and toggle the selected effect
effectList = [chorus, distr, reverb, delay, flanger, envelope, tremolo, freq]
effectCtrl = [False, False, False, False, False, False, False, False]

#Counter for the currently selected effect
effectIndex = 0

counter = 0 

ledState = False
sfxOn = False

#Main loop
while (True):
    #Update button status variables
    lastButtonState = currentButtonState
    currentButtonState = GPIO.input(INPUT_PIN)
    lastButtonState2 = currentButtonState2
    currentButtonState2 = GPIO.input(INPUT_PIN_2)

    #Check for any changes in the button press state
    if ((lastButtonState != currentButtonState) and lastButtonState == GPIO.HIGH):
        #When the first button is pressed, toggle the effect on / off, depending upon previous state.
        print("press 1")
        ledState = not ledState
        sfxOn = not sfxOn
        effectCtrl[effectIndex] = not effectCtrl[effectIndex]
        print(counter)

    if ((lastButtonState2 != currentButtonState2) and lastButtonState2 == GPIO.HIGH):
        #When the second button is pressed, update the effect index
        #If it goes past the bounds of the indexable list, it wraps back around to zero.
        print("press 2")
        ledState = not ledState
        effectIndex += 1
        if (effectIndex > len(effectList) - 1):
            effectIndex = 0
        print(counter)
        print("current effect: " + str(effectIndex))
        
    #Update the state of the LED
    if (ledState):
        GPIO.output(OUTPUT_PIN, GPIO.HIGH)
    else:
        GPIO.output(OUTPUT_PIN, GPIO.LOW)

    #If the effects were turned on, stop all of the PyoObjects from outputting, and play the currently
    #selected effect at the given index
    if (sfxOn):
        a.stop()
        distr.stop()
        chorus.stop()
        reverb.stop()
        delay.stop()
        freqShift.stop()
        flanger.stop()
        envelope.stop()
        tremolo.stop()
        freq.stop()
        effectList[effectIndex].out()
    #If the effects were turned off, play the clean channel and stop all of the special effects
    else:
        a.out()
        distr.stop()
        chorus.stop()
        reverb.stop()
        delay.stop()
        freqShift.stop()
        flanger.stop()
        envelope.stop()
        tremolo.stop()
        freq.stop()
        effectList[effectIndex].stop()
        

    counter += 1
    if (counter > 10000):
        counter = 0 

    #Sleeps for a tenth of a second so there's less of a load on the CPU
    #for polling the buttons
    time.sleep(.100)
