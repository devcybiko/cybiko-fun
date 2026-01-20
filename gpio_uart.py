import pigpio

class GpioUart:
    DATA_PIN = 9   # The GPIO pin to analyze (e.g., RX_AVR)
    BITS = 11
    WORD = 8
    LONG_WORD = BITS * WORD
    GAP_MS = 10

    def __init__(self, pi, data_pin: int):
        self.pi = pi
        self.data_pin = data_pin
        self.pi = None
        self.callback = None
        self.transitions = []
        self.capturing = False
        self.last_event_tick = 0
        self.last_idle_tick = 0
        self.transitions = []

    def init_pigpio(self):
        def data_callback(gpio, level, tick):
            if not self.capturing:
                if level == 0: 
                    # Measure from the last time it went HIGH until NOW (the falling edge)
                    if pigpio.tickDiff(self.last_idle_tick, tick) > (self.GAP_MS * 1000):
                        self.transitions = [(0, tick)]
                        self.capturing = True
                else:
                    # Mark the time the line went HIGH
                    self.last_idle_tick = tick
            else:
                self.transitions.append((level, tick))
                self.last_event_tick = tick

        self.pi = pigpio.pi()
        if not self.pi.connected:
            print("Error: Could not connect to pigpiod. Is it running?", flush=True)
            print("Start it with: sudo systemctl enable --now pigpiod", flush=True)
            raise SystemExit(1)

        # Set up GPIO mode
        self.pi.set_mode(self.data_pin, pigpio.INPUT)
        self.pi.set_pull_up_down(self.data_pin, pigpio.PUD_OFF) 

        # Set a glitch filter to ignore noise pulses shorter than 15 microseconds
        # self.pi.set_glitch_filter(self.data_pin, 2)
        # print("Glitch filter set to 15 us.", flush=True)

        # Create the callback that will fire on each signal change
        self.callback = self.pi.callback(self.data_pin, pigpio.EITHER_EDGE, data_callback)
        self.last_event_tick = self.pi.get_current_tick()
        self.last_idle_tick = self.pi.get_current_tick() - (self.GAP_MS * 2000)
        print(f"Initialized GPIO UART on pin {self.data_pin}.", flush=True)

    def decode_uart(self, bits, nbits=8, nparity=1, nstop=2):
        frame_len = 1 + nbits + nparity + nstop # 12
        values = []
        
        for i in range(0, len(bits), frame_len):
            frame = bits[i:i+frame_len]
            if len(frame) < frame_len: break
            
            # Start Bit must be 0
            if frame[0] == 0:
                val = 0
                # Data Bits (1 to 8)
                for shift in range(nbits):
                    if frame[shift + 1]:
                        val |= (1 << shift)
                
                # Control/Parity Bit (Index 9)
                if nparity > 0 and frame[1 + nbits]:
                    val |= (1 << nbits) # Bit 8 (0x100)
                
                values.append(val)
            else:
                print(f"Framing error at index {i}", flush=True)

        return values

    def analyze_transitions(self, snapshot):
        if len(snapshot) < 2:
            print("No transitions captured.", flush=True)
            return []
        
        durations = []
        for i in range(len(snapshot) - 1):
            level = snapshot[i][0]
            duration = pigpio.tickDiff(snapshot[i][1], snapshot[i+1][1])
            durations.append((level, duration))
        return durations

    def decode_bitstream(self, durations, baud=38400):
        BIT_US = 1000000.0 / baud
        SAMPLE_OFFSET = BIT_US * 0.70
        
        timeline = []
        t_abs = 0
        for level, dur in durations:
            timeline.append((t_abs, level))
            t_abs += dur

        bits = []
        t = 0
        ptr = 0 
        
        def get_level_fast(target_t):
            nonlocal ptr
            # Compare against timeline[ptr+1][0] (the timestamp)
            while ptr + 1 < len(timeline) and timeline[ptr+1][0] <= target_t:
                ptr += 1
            return timeline[ptr][1] # Return only the level (0 or 1)

        # Corrected check: if the first recorded transition starts at Level 0
        if durations and durations[0][0] == 0:
            start_edge = 0
            for i in range(12):
                bits.append(get_level_fast(start_edge + (i * BIT_US) + SAMPLE_OFFSET))
            t = start_edge + (BIT_US * 11)

        while t < (t_abs - (BIT_US * 12)):
            if get_level_fast(t) == 1 and get_level_fast(t + 1) == 0:
                start_edge = t + 1
                for i in range(12):
                    # sample_t = start_edge + (i * BIT_US) + SAMPLE_OFFSET
                    # bits.append(get_level_fast(sample_t))
                    # Sample at 55%, 60%, and 65% of the bit
                    mid_sample = 0.65
                    t1 = start_edge + (i * BIT_US) + (BIT_US * (mid_sample - 0.05))
                    t2 = start_edge + (i * BIT_US) + (BIT_US * mid_sample)
                    t3 = start_edge + (i * BIT_US) + (BIT_US * (mid_sample + 0.05))
                    
                    v1 = get_level_fast(t1)
                    v2 = get_level_fast(t2)
                    v3 = get_level_fast(t3)
                    
                    # Majority vote
                    bits.append(1 if (v1 + v2 + v3) >= 2 else 0)

                t = start_edge + (BIT_US * 11.2)
            else:
                t += 1
                
        return bits



    def split_durations_by_long_idle(self, durations, baud=38400, threshold_bits=32):
        """
        Splits the list of (level, duration) tuples into arrays of (level, duration) tuples, separated by long durations (idle).
        Returns a list of duration-lists (each a list of (level, duration)).
        threshold_bits: number of bits (at baud rate) to consider a 'long' duration (default: 32 bits)
        """
        BIT_US = int(1_000_000 / baud)
        threshold_us = threshold_bits * BIT_US
        streams = []
        current = []
        for level, dur in durations:
            if dur >= threshold_us:
                if current:
                    streams.append(current)
                    current = []
                continue
            current.append((level, dur))
        if current:
            streams.append(current)
        return streams

    def decode_fixed(self, durations, baud=38400):
        BIT_US = 1000000.0 / baud
        HALF_BIT = BIT_US / 2.0
        
        # 1. Convert to absolute timeline
        timeline = []
        t = 0
        for level, dur in durations:
            timeline.append((t, level))
            t += dur
        
        def get_level_at(time):
            for edge_t, level in reversed(timeline):
                if edge_t <= time:
                    return level
            return 1

        decoded_bytes = []
        curr_t = 0
        
        # 2. Hunt and Re-sync loop
        while curr_t < t - (BIT_US * 12):
            # Hunt for Falling Edge (1 -> 0)
            if get_level_at(curr_t) == 1 and get_level_at(curr_t + 2) == 0:
                start_bit_edge = curr_t + 2 # Found the transition
                
                # Sample bits at 1.5, 2.5, 3.5... bit widths from the edge
                # This ensures we hit the DEAD CENTER of every bit
                bits = []
                for i in range(12):
                    sample_t = start_bit_edge + (BIT_US * i) + HALF_BIT
                    bits.append(get_level_at(sample_t))
                
                # Extract 8 data bits (LSB first)
                data_bits = bits[1:9]
                byte_val = 0
                for shift, bit in enumerate(data_bits):
                    if bit: byte_val |= (1 << shift)
                
                ascii = chr(byte_val & 0x7f) if 32 <= byte_val <= 126 else '.'
                decoded_bytes.append(f"0x{byte_val:02X} ('{ascii}')")
                
                # Jump ahead to the end of the frame (Stop Bits)
                curr_t = start_bit_edge + (BIT_US * 11)
            else:
                curr_t += 2 # Move in 2us increments to find the edge
                
        return decoded_bytes
