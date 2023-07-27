import ctypes as c

class DeformableMirror:
    '''
    Class for controlling a single deformable mirror. For now it only hooks to 
    the first mirror.
    '''

    lib:...
    libX:...
    instrumentHandle = c.c_ulong()
    deviceCount = c.c_int()
    initd = False
    segmentCount = c.c_uint32()
    mirrorPattern = (c.c_double*(segmentCount.value))()
    flagDict = dict(zip([2**x for x in range(12)],
                    ["Ast45", "Def", "Ast0", "TreY", "ComX", "ComY", "TreX", "TetY", "SAstY", "SAb3", "SAstX", "TetX"]))

    def __init__(self):
        # load libraries
        try:
            self.lib = c.cdll.LoadLibrary("C:\Program Files\IVI Foundation\VISA\Win64\Bin\TLDFM_64.dll")
            self.libX = c.cdll.LoadLibrary("C:\Program Files\IVI Foundation\VISA\Win64\Bin\TLDFMX_64.dll")
        except:
            print("Missing library files.")
            return
        
        # check for present devices
        self.lib.TLDFM_get_device_count(self.instrumentHandle, c.byref(self.deviceCount))
        if self.deviceCount.value < 1:
            print("No DMP40 devices found.")
        
    def initDevice(self):
        # make sure a device exists
        if self.deviceCount.value < 1:
            print("No DMP40 devices found.")
            return
        
        # get the resource value and then init as a tldfmx to get the extended function set
        resource = c.c_char_p(b"")
        self.lib.TLDFM_get_device_information(self.instrumentHandle, 0, 0, 0, 0, 0, resource)
        if (0 != self.libX.TLDFMX_init(resource.value, True, False, c.byref(self.instrumentHandle))):
            print("Error with initialization.")
            return

        self.initd = True
        self.relaxDevice()
        
    def relaxDevice(self, part=c.c_uint32(2)):
        # part corresponds to which part of the mirror is relaxed
        # 0: only mirror, 1: only bimorph tilt arms, 2: both

        # check if device is initialized
        if not(self.initd):
            print("Device must first be initialized")
            return
        
        isFirstStep = c.c_bool(True)
        reload = c.c_bool(False)
        # Determine how many segments the mirror has and how many tilt arms.
        self.segmentCount = c.c_uint32()
        self.lib.TLDFM_get_segment_count(self.instrumentHandle, c.byref(self.segmentCount))
        self.mirrorPattern = (c.c_double*(self.segmentCount.value))()
        tiltCount = c.c_uint32()
        self.lib.TLDFM_get_tilt_count(self.instrumentHandle, c.byref(tiltCount))
        # Create arrays for the mirror segment and tilt arm patterns
        relaxPatternMirror = (c.c_double*(self.segmentCount.value))()
        relaxPatternArms = (c.c_double*(tiltCount.value))()

        remainingSteps = c.c_int32()
        counter = 1

        # First relax step.
        print("Relaxing the DMP40")
        self.libX.TLDFMX_relax(self.instrumentHandle, part, isFirstStep, reload,
                    relaxPatternMirror, relaxPatternArms, c.byref(remainingSteps))

        self.lib.TLDFM_set_segment_voltages(self.instrumentHandle, relaxPatternMirror)
        self.lib.TLDFM_set_tilt_voltages(self.instrumentHandle, relaxPatternArms)
        counter = counter + 1

        isFirstStep = c.c_bool(False)

        # The following relax steps are made in a loop until the relaxation is complete.
        while remainingSteps.value > 0:
            self.libX.TLDFMX_relax(self.instrumentHandle, part, isFirstStep, reload,
                    relaxPatternMirror, relaxPatternArms, c.byref(remainingSteps))
            self.lib.TLDFM_set_segment_voltages(self.instrumentHandle, relaxPatternMirror)
            self.lib.TLDFM_set_tilt_voltages(self.instrumentHandle, relaxPatternArms)
        print("Relaxing completed\n")

    def setSingleZernikeStrength(self, zernikeBitfield:c.c_uint32, amplitude:c.c_double, verbose=False):
        # the zernike bitfields are as follows:
        #     Z_Ast45_Flag = 0x00000001, // Z4   
        #     Z_Def_Flag   = 0x00000002, // Z5   
        #     Z_Ast0_Flag  = 0x00000004, // Z6   
        #     Z_TreY_Flag  = 0x00000008, // Z7   
        #     Z_ComX_Flag  = 0x00000010, // Z8   
        #     Z_ComY_Flag  = 0x00000020, // Z9   
        #     Z_TreX_Flag  = 0x00000040, // Z10  
        #     Z_TetY_Flag  = 0x00000080, // Z11  
        #     Z_SAstY_Flag = 0x00000100, // Z12  
        #     Z_SAb3_Flag  = 0x00000200, // Z13  
        #     Z_SAstX_Flag = 0x00000400, // Z14  
        #     Z_TetX_Flag  = 0x00000800, // Z15
        # the amplitude ranges from [-1.0,1.0]

        # check if device is initialized
        if not(self.initd):
            print("Device must first be initialized")
            return
        
        # check amplitude rangeDeformable Mirror
        if not(amplitude.value>=-1.0 and amplitude.value<=1.0):
            print("Amplitude must be in the range [-1.0,1.0]")
            return
        
        print(f'Setting {self.flagDict[zernikeBitfield.value]} to {amplitude.value}')
        
        # calculate the zernike pattern and then set the voltages
        self.libX.TLDFMX_calculate_single_zernike_pattern(self.instrumentHandle, 
                                    zernikeBitfield, amplitude, self.mirrorPattern)
        self.lib.TLDFM_set_segment_voltages(self.instrumentHandle, 
                                                                self.mirrorPattern)
        
        if verbose: 
            self.getState()
        
    def setZernikeStrength(self, zernikeBitfield:c.c_uint32, amplitudes:list[c.c_double], verbose=False):
        # set multiple zernike polynomials at once. The list of amplitudes will
        # always have a size of 12, and the amplitudes go in order of the bitfields:
        #     Z_Ast45_Flag = 0x00000001, // Z4   
        #     Z_Def_Flag   = 0x00000002, // Z5   
        #     Z_Ast0_Flag  = 0x00000004, // Z6   
        #     Z_TreY_Flag  = 0x00000008, // Z7   
        #     Z_ComX_Flag  = 0x00000010, // Z8   
        #     Z_ComY_Flag  = 0x00000020, // Z9   
        #     Z_TreX_Flag  = 0x00000040, // Z10  
        #     Z_TetY_Flag  = 0x00000080, // Z11  
        #     Z_SAstY_Flag = 0x00000100, // Z12  
        #     Z_SAb3_Flag  = 0x00000200, // Z13  
        #     Z_SAstX_Flag = 0x00000400, // Z14  
        #     Z_TetX_Flag  = 0x00000800, // Z15
        # the amplitudes range from [-1.0,1.0]

        # check if device is initialized
        if not(self.initd):
            print("Device must first be initialized")
            return
        
        # check amplitude size 
        if not(len(amplitudes)==12):
            print("Amplitude list length must be 12")
            return
        
        # check amplitude values
        if min(amplitudes) < -1.0 or max(amplitudes) > 1.0:
            print("Amplitudes must be in the range [-1.0,1.0]")
            return

        print(f"Setting the following amplitudes (in order):")
        print(f'{[amplitudes[x] for x in range(12)]}')
        
        # calculate the zernike pattern and then set the voltages
        self.libX.TLDFMX_calculate_zernike_pattern(self.instrumentHandle, 
                                    zernikeBitfield, amplitudes, self.mirrorPattern)
        self.lib.TLDFM_set_segment_voltages(self.instrumentHandle, 
                                                                self.mirrorPattern)
        
        if verbose:
            self.getState()

    def getState(self):
        # prints the current voltage on all segments for debugging purposes

        # check if device is initialized
        if not(self.initd):
            print("Device must first be initialized")
            return
        
        for x in range(self.segmentCount.value):
            print("Segment voltage in segment", x+1, ": ", self.mirrorPattern[x])

    def disconnect(self):
        # check if device is initialized
        if not(self.initd):
            print("Device must first be initialized")
            return
        
        self.libX.TLDFMX_close(self.instrumentHandle)