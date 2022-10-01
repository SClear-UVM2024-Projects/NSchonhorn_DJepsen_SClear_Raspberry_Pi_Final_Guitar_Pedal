# Import libraries needed to make everything work
import RPi.GPIO as GPIO
import time
from pyo import *

# Set up GPIO pins for pedal input and LED output
INPUT_PIN = 17
INPUT_PIN_2 = 22
OUTPUT_PIN = 27

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Setting the internal resistors on the given GPIO pins to pull low,
# so that the program responds correctly when a high signal is emitted by a button press
GPIO.setup(INPUT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN) 
GPIO.setup(INPUT_PIN_2, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(OUTPUT_PIN, GPIO.OUT)

# Booleans to keep track of current and previous values of the button input,
# to determine if there's been a button press or not.
lastButtonState = False
currentButtonState = False
lastButtonState2 = False
currentButtonState2 = False

# Start Pyo server to open audio inputs and get ready to pass through Pyo classes
s = Server()
s.setInputDevice(1)
s.setOutputDevice(1)
s.boot()
s.start()

# The class tutorial using the Flanger class as a representation of the structure used in a PyoObject. This was 
# used as inspiration to creating the structure of the different effect classes to either override the original 
# methods in the function, or act as getter, setter, or other methods to interact with the aspects of the 
# audiowave, while the modulation effects created in the pedal were created from our custom combinations and 
# implementations of the Pyo library.

# Flanger class implementation adapted from here: http://ajaxsoundstudio.com/pyodoc/tutorials/pyoobject2.html
class Flanger(PyoObject):
    def __init__(self, input, depth=0.75, lfofreq=0.2, feedback=0.5, mul=1, add=0):
        # Initialize PyoObject basic attributes
        PyoObject.__init__(self)

        # Keep references of arguments
        self._input = input
        self._depth = depth
        self._lfofreq = lfofreq
        self._feedback = feedback

        # Using InputFader to create a fade between different effects when changing sources
        self._in_fader = InputFader(input)

        # Convert each var into lists
        in_fader, depth, lfofreq, feedback, mul, add, lmax = convertArgsToLists(self._in_fader, depth, lfofreq, feedback, mul, add)

        # In the heart of the class lies the guitar effects, which controls the modulation of the audio passed into the class.
        # Each of the aspects of the Flanger effect are created here, with the sweeping delayed audio which follows the original guitar
        # audio created from the signal, LFO, and Delay objects. The switching of each of the signal effects, created from switching 
        # between audio signals using alternating Sine object loops. Finally, each of the audio signals are placed into a Mixer 
        # object to allow for us to place multiple effects into the same audiostream, along with change the presence of each effect
        # in the audio stream.
        self._amplitudemodulation = Sig(depth, mul=0.005)
        self._wavechange = LFO(freq=lfofreq * 2, sharp=0.3, type=7, add=0.005, mul=self._amplitudemodulation)
        self._flangedelay = SDelay(in_fader, delay=self._wavechange, maxdelay=1.5, mul=1, add=0)
        self._alternatewave = Sin(self._flangedelay, mul=1, add=0)
        self._alternateinput = Sin(self._input, mul=-1, add=0)
        self._flange = Mixer(outs=2, chnls=2, time=0.05, mul=1.02, add=0.01)
        self._flange.addInput(voice=0, input=self._input)
        self._flange.addInput(voice=1, input=self._flangedelay)

        self._flange.setAmp(0, 1, 1)
        self._flange.setAmp(1, 1, 0.9)
        
        # Exports each of the objects from the Flanger class to the created Flanger guitar effect object
        self._base_objs = self._flange.getBaseObjects()

    def setInput(self, x, fadetime=0.05):
        # Replaces the input attribute, then returns the reference of the input object to the guitar audio to ensure the reference is 
        # updated
        self._input = x
        self._in_fader.setInput(x, fadetime)

    def setDepth(self, x):
        # Replaces the depth attribute with the given value, then updates the value inside the guitar objects created
        self._depth = x
        self._amplitudemodulation.value = x

    def setLfoFreq(self, x):
        # Replaces the lfofreq attribute, then updates the value in the LFO oscilating object effect
        self._lfofreq = x
        self._wavechange.freq = x * 2

    def setFeedback(self, x):
        # Replaces feedback attribute, then updates the attribute in the flangedelay object
        self._feedback = x
        self._flangedelay.feedback = x

    # Getter and Setter methods to allow users to interact with the different parameters of the object directly outside of the object
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

    # Overriding the methods from the base PyoObject to create the utilize the new flanger modulations
    # This method makes sure controls work properly when used from the GUI, not relevant to headless usage sadly
    def ctrl(self, map_list=None, title=None, wxnoserver=False):
        self._map_list = []
        PyoObject.ctrl(self, map_list, title, wxnoserver)

    # The following three methods are responsible for starting and stopping audio output
    # Play and Out methods are both methods that play all of the audio effects when called and returns the modulating 
    # guitar effect object
    def play(self, dur=0, delay=0):
        self._amplitudemodulation.play(dur, delay)
        self._wavechange.play(dur, delay)
        self._flangedelay.play(dur, delay)
        return PyoObject.play(self, dur, delay)

    def out(self, chnl=0, inc=1, dur=0, delay=0):
        self._amplitudemodulation.play(dur, delay)
        self._wavechange.play(dur, delay)
        self._flangedelay.play(dur, delay)
        return PyoObject.out(self, chnl, inc, dur, delay)

    # Stop method halts all audio effects of the current object and returns the object to the call
    def stop(self, wait=0):
        self._amplitudemodulation.stop(wait)
        self._wavechange.stop(wait)
        self._flangedelay.stop(wait)
        return PyoObject.stop(self, wait)

# The Vibrato object increases and decreases the pitch of the sound very quickly, creating a light wobbling effect on the Guitar or Bass pitch    
class Vibrato(PyoObject):
    def __init__(self, input, depth=0.5, mul=1, add=0):
        # Initialize PyoObject basic attributes
        PyoObject.__init__(self)

        # The reference of the arguments are saved
        self._input = input
        self._depth = depth

        # InputFader is applied to the input audio stream to allow for crossfading between internal input devices, such as when switching between 
        # different guitar or bass effects, along with different guitars or basses
        self._in_fader = InputFader(input)

        in_fader, depth, mul, add, lmax = convertArgsToLists(self._in_fader, depth, mul, add)

        # Here, the sound effects of the modulation are applied to the object. First, the Sine wave and Signal objects create an oscillating 
        # signals at a frequency of the given depth. Then, the Frequency Shift object slightly oscillates the frequency over the course of the 
        # object being active.
        self._sinewave = Sine(freq=depth, mul=5, add=3)
        self._wavesig = Sig(self._sinewave, mul=2)
        self._vibrato = FreqShift(in_fader, self._wavesig, mul=mul, add=add).out()

        # Set the effects to the given audio output
        self._base_objs = self._vibrato.getBaseObjects()

    def setInput(self, x, fadetime=0.05):
        # Replaces the input attribute, then returns the reference of the input object to the guitar audio to ensure the reference is 
        # updated
        self._input = x
        self._in_fader.setInput(x, fadetime)

    def setDepth(self, x):
        # Replaces the depth attribute with the given value, then updates the value inside the guitar objects created
        self._depth = x
        self._wavesig.value = x

    # Getter and Setter methods to allow users to interact with the different parameters of the object outside of the object
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

    # Overriding the methods from the base PyoObject to create the utilize the new vibrato modulations
    # This method makes sure controls work properly when used from the GUI, not relevant to headless usage sadly    
    def ctrl(self, map_list=None, title=None, wxnoserver=False):
        self._map_list = []
        PyoObject.ctrl(self, map_list, title, wxnoserver)

    # The following three methods are responsible for starting and stopping audio output
    # Play and Out methods are both methods that play all of the audio effects when called and returns the modulating 
    # guitar effect object
    def play(self, dur=0, delay=0):
        self._wavesig.play(dur, delay)
        self._sinewave.play(dur, delay)
        self._vibrato.play(dur, delay)
        return PyoObject.play(self, dur, delay)

    def out(self, chnl=0, inc=1, dur=0, delay=0):
        self._wavesig.play(dur, delay)
        self._sinewave.play(dur, delay)
        self._vibrato.play(dur, delay)
        return PyoObject.out(self, chnl, inc, dur, delay)

    # Stop method halts all audio effects of the current object and returns the object to the call 
    def stop(self, wait=0):
        self._wavesig.stop(wait)
        self._sinewave.stop(wait)
        self._vibrato.stop(wait)
        return PyoObject.stop(self, wait)
        
# The Tremolo effect acts similarly to Vibrato, with the volume of the guitar audio wobbling instead of the pitch
class Tremolo(PyoObject):
    def __init__(self, input, freq=6, mul=1, add=0):
        # Initialize basic guitar object parameters, as well as the change in frequency from the Tremolo effect, as well as the 
        # InputFader function applied to the imput signal for fading into different effects or devices, such as switching 
        # between different guitar or bass effects or devices
        PyoObject.__init__(self)
        
        self._input = input
        self._freq = freq
        
        self._in_fader = InputFader(input)

        in_fader, freq, mul, add, lmax = convertArgsToLists(self._in_fader, freq, mul, add)

        # Sound effects are applied to the input guitar or bass audio. The given frequency of the tremolo is oscillated using the Sine 
        # object, as well as the volume control in the Chorus object, while the delay of the chorus effect is nullified to solely utilize the 
        # volume change of the Tremolo effect
        self._tremosc = Sine(freq=self._freq, mul=mul)
        self._tremolo = Chorus(input, depth=.1, feedback=0, bal=0.5, mul=self._tremosc, add=add)

        self._base_objs = self._tremolo.getBaseObjects()

    # Getter and Setter methods to allow users to interact with the different parameters of the object directly outside of the object
    def setInput(self, x, fadetime=0.05):
        # Replaces the input attribute, then returns the reference of the input object to the guitar audio to ensure the reference is 
        # updated
        self._input = x
        self._in_fader.setInput(x, fadetime)

    def setFreq(self, x):
        # Replaces the frequency attribute of the function in the class, along with updating the frequency within the the Tremolo 
        # oscillation object "tremosc" 
        self._freq = x
        self._tremosc.freq = x

    # Getter and Setter methods to allow users to interact with the different parameters of the object outside of the object
    @property
    def input(self):
        return self._input
    @input.setter
    def input(self, x):
        self.setInput(x)

    @property
    def freq(self):
        return self._freq
    @freq.setter
    def freq(self, x):
        self.setFreq(x)

    # Overriding the methods from the base PyoObject to create the utilize the new tremolo modulations
    # This method makes sure controls work properly when used from the GUI, not relevant to headless usage sadly   
    def ctrl(self, map_list=None, title=None, wxnoserver=False):
        self._map_list = []
        PyoObject.ctrl(self, map_list, title, wxnoserver)

    # The following three methods are responsible for starting and stopping audio output
    # Play and Out methods are both methods that play all of the audio effects when called and returns the modulating 
    # guitar effect object
    def play(self, dur=0, delay=0):
        self._tremosc.play(dur, delay)
        return PyoObject.play(self, dur, delay)

    def out(self, chnl=0, inc=1, dur=0, delay=0):
        self._tremosc.play(dur, delay)
        return PyoObject.out(self, chnl, inc, dur, delay)

    # Stop method halts all audio effects of the current object and returns the object to the call 
    def stop(self, wait=0):
        self._tremosc.stop(wait)
        return PyoObject.stop(self, wait)

# The Leslie Speaker guitar effect acts as a combination of multiple effects to create a sound similar to a fan in 
# front of a speaker. 
class Leslie(PyoObject):
    def __init__(self, input, depth=1, pitdepth=3, mul=1, add=0):
        # Each of the basic methods for the PyoObject are current method parameters, as well as the parameters of 
        # the object being initialized into references which are converted into lists to contain either one or multiple 
        # values from different modulation effects, such as Sine's frequency variable and Phaser's frequency variable. 
        # Additionally, the guitar signal is converted through the InputFader function to allow for the signal to fade 
        # in between the switching of effects or input devices, such as the guitar or the bass
        PyoObject.__init__(self)

        self._input = input
        self._depth = depth

        self._in_fader = InputFader(input)

        in_fader, mul, add, lmax = convertArgsToLists(self._in_fader, mul, add)

        # Now to the Key Guitar Effect of the project. The Leslie effect combines Tremolo, Phaser, and Vibrato sound effects 
        # to create the sound of a Leslie speaker. First, the two sine waves of the Phaser effect are creating using the Sine 
        # objects, which are imported into the initialized Phaser object. Second, the Tremolo effect created previously is 
        # implemented using the given guitar audio. Thirdly, the Phaser effect is initialized, modulating the given guitar 
        # audio along with the given oscillating frequency and spread values from the sine wave objects "lfofreq" and "lfospread."
        # Fourthly, a Vibrato effect is created using the guitar audio and oscillating the pitch slightly by the given depth value
        # Finally, each of the sound effects are inputted into the Mixer object to allow for future users to control which audio 
        # devices each effect is sent through and the prominence of each effect in the signal. In our default settings for this 
        # effect, the entire Leslie speaker effect outputs on a single speaker with each part of the effect outputted equally.
        self._lfofreq = Sine(freq=[.2,.20],mul=70,add=200)
        self._lfospread = Sine(freq=[.16 * self._depth, .13 * self._depth], mul=.6, add=1.5)
        self._tremolo = Tremolo(input, freq=4).out()
        self._phaser = Phaser(input, freq=self._lfofreq, spread=self._lfospread, q=1, feedback=.5, num=18, mul=.1).out()
        self._vibrato = Vibrato(input, depth=6).out()
        self._leslie = Mixer(outs=3, chnls=3, time=0.5, mul=mul, add=add).out()
        self._leslie.addInput(voice=0, input=self._tremolo)
        self._leslie.addInput(voice=1, input=self._phaser)
        self._leslie.addInput(voice=2, input=self._vibrato)

        self._leslie.setAmp(0, 1, 1)
        self._leslie.setAmp(1, 1, 1)
        self._leslie.setAmp(2, 1, 1)
        
        self._base_objs = self._leslie.getBaseObjects()

    # Getter and Setter methods to allow users to interact with the different parameters of the object directly outside of the object
    def setInput(self, x, fadetime=0.05):
        # Replaces the input attribute, then returns the reference of the input object to the guitar audio to ensure the reference is 
        # updated
        self._input = x
        self._in_fader.setInput(x, fadetime)

    # Getter and Setter methods to allow users to interact with the different parameters of the object outside of the object    
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
    
    # Overriding the methods from the base PyoObject to create the utilize the new leslie modulation
    # This method makes sure controls work properly when used from the GUI, not relevant to headless usage sadly  
    def ctrl(self, map_list=None, title=None, wxnoserver=False):
        self._map_list = []
        PyoObject.ctrl(self, map_list, title, wxnoserver)

    # The following three methods are responsible for starting and stopping audio output
    # Play and Out methods are both methods that play all of the audio effects when called and returns the modulating 
    # guitar effect object 
    def play(self, dur=0, delay=0):
        self._tremolo.play(dur, delay)
        self._phaser.play(dur, delay)
        self._vibrato.play(dur, delay)
        return PyoObject.play(self, dur, delay)

    def out(self, chnl=0, inc=1, dur=0, delay=0):
        self._tremolo.play(dur, delay)
        self._phaser.play(dur, delay)
        self._vibrato.play(dur, delay)
        return PyoObject.out(self, chnl, inc, dur, delay)

    # Stop method halts all audio effects of the current object and returns the object to the call    
    def stop(self, wait=0):
        self._tremolo.stop(wait)
        self._phaser.stop(wait)
        self._vibrato.stop(wait)
        return PyoObject.stop(self, wait)

# To begin the loop, first each of the guitar effects are initialized with their fine-tuned parameters for each specific effects. This list 
# includes of two input objects to act as the pure audio from the guitar and as the input audio for each of the guitar effects. Next, each of the 
# special guitar effects are initialized. These effects include of fine-tuned classic effects created from PyoObjects such as Chorus, Delay, and 
# Distortion, multilayered or multichained effects created from inputting value manipulation or audio modulations effects into other created 
# guitar effect objects to create a single effect such as FrequencyShift, and each of the initialized custom class effects of Vibrato, Tremolo, 
# and the Leslie speaker effect
a = Input(chnl=0).out()
b = Input(chnl=0)
chorus = Chorus(b, depth=1.2, feedback=.6, bal=0.5).out()
distr = Disto(b, slope=.3, mul=.65).out()
reverb = STRev(b, revtime=1.8, roomSize=1.2).out()
delay = Delay(b, delay=.6, feedback=.3, maxdelay=.8).out()
freqShift = FreqShift(b, shift=200, mul=1).out()
flanger = Flanger(b, depth=.875, lfofreq=.545).out()
fol = Follower(b, freq=45, mul=4200, add=35)
# Envelope / Autowah implementation adapted from here: https://www.matthieuamiguet.ch/blog/diy-guitar-effects-python
envelope = Biquad(b, freq=fol, q=7, type=0).out()
tremfreq = Sine(freq=6)
tremolo = Chorus(b, depth=.1, feedback=.2, bal=0.5, mul=tremfreq).out()
tremolo1 = Tremolo(b, freq=6, mul=1, add=0)
freq = FreqShift(b, shift=fol, mul=1, add=0).out()
vibrato = Vibrato(b, depth=10).out()
lfo1 = Sine(freq=[.1,.15], mul=65, add=200)
lfo2 = Sine(freq=[.18, .15], mul=.6, add=1.5)
phaser = Phaser(b, freq=lfo1, spread=lfo2, q=1, feedback=.5, num=20).out()
leslie = Leslie(b, mul=.7).out()

# Stop all special guitar effects before outputting so that there are no issues playing standard guitar audio when 
# program drops into the main loop
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
vibrato.stop()
phaser.stop()
leslie.stop()

# Throw all of the output effects into an array to index through and toggle the selected effect
effectList = [chorus, distr, reverb, delay, flanger, envelope, tremolo1, vibrato, phaser, leslie, freq]
effectNameList = ["Chorus", "Distortion", "Reverb", "Delay", "Flanger", "Envelope Filter", "Tremolo", "Vibrato", "Phaser", "Leslie Speaker", "FreqShift"]
effectCtrl = [False, False, False, False, False, False, False, False, False, False, False, False]

# Index for the currently selected effect
effectIndex = 0 

ledState = False
sfxOn = False

# Main loop
while (True):
    # Update button status variables
    lastButtonState = currentButtonState
    currentButtonState = GPIO.input(INPUT_PIN)
    lastButtonState2 = currentButtonState2
    currentButtonState2 = GPIO.input(INPUT_PIN_2)

    #C heck for any changes in the button press state
    if ((lastButtonState != currentButtonState) and lastButtonState == GPIO.HIGH):
        #W hen the first button is pressed, toggle the effect on / off, depending upon previous state.
        if (not sfxOn):
            print("Toggle On")
        if (sfxOn):
            print("Toggle Off")
        ledState = not ledState
        sfxOn = not sfxOn
        effectCtrl[effectIndex] = not effectCtrl[effectIndex]

    if ((lastButtonState2 != currentButtonState2) and lastButtonState2 == GPIO.HIGH):
        # When the second button is pressed, update the effect index
        # If it goes past the bounds of the indexable list, it wraps back around to zero.
        print("Changing Effect")
        ledState = not ledState
        effectIndex += 1
        if (effectIndex > len(effectList) - 1):
            effectIndex = 0
        print("Current effect: " + effectNameList[effectIndex])
        
    # Update the state of the LED, to indicate button presses
    if (ledState):
        GPIO.output(OUTPUT_PIN, GPIO.HIGH)
    else:
        GPIO.output(OUTPUT_PIN, GPIO.LOW)

    # If the effects were turned on, stop all of the PyoObjects from outputting, and play the currently
    # selected effect at the given index
    if (sfxOn):
        a.stop()
        distr.stop()
        chorus.stop()
        reverb.stop()
        delay.stop()
        freqShift.stop()
        flanger.stop()
        envelope.stop()
        tremolo1.stop()
        freq.stop()
        vibrato.stop()
        phaser.stop()
        leslie.stop()
        effectList[effectIndex].out()

    # If the effects were turned off, play the clean channel and stop all of the special effects
    else:
        a.out()
        distr.stop()
        chorus.stop()
        reverb.stop()
        delay.stop()
        freqShift.stop()
        flanger.stop()
        envelope.stop()
        tremolo1.stop()
        freq.stop()
        vibrato.stop()
        phaser.stop()
        leslie.stop()
        effectList[effectIndex].stop()

    # Sleeps for a tenth of a second so there's less of a load on the CPU
    # for polling the buttons
    time.sleep(.100)
