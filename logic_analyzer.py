import time
import pigpio

# --- GPIO Pin Configuration (BCM numbering) ---
# !!! IMPORTANT !!!
# You MUST change this pin number to match your wiring.
DATA_PIN = 9   # The GPIO pin to analyze (e.g., RX_AVR)


# --- Analysis Settings ---
# Time in milliseconds with no signal change to be considered a gap
GAP_MS = 10

# Bit/word grouping for output formatting
BITS = 11
WORD = 8
LONG_WORD = BITS * WORD

# --- Global State Variables ---
global pi, callback, capturing, last_event_tick, last_idle_tick, transitions
pi = None
callback = None
transitions = []
capturing = False
last_event_tick = 0
last_idle_tick = 0
transitions = []

def first_frame(bits, nbits, nparitybits, nstopbits):
    """
    Scan bits and return the index of the first valid UART frame.
    A valid frame has start bit 0 and all stop bits 1.
    Returns the index or None if not found.
    """
    frame_len = 1 + nbits + nparitybits + nstopbits
    for idx in range(len(bits) - frame_len + 1):
        frame = bits[idx:idx+frame_len]
        start = frame[0]
        stop = frame[1+nbits+nparitybits:]
        if start == 0 and all(s == 1 for s in stop):
            return idx
    return None

def print_bitstream(bits, group_size):
    """
    Print the bitstream in groups, skipping long runs of 1s as '1xN'.
    group_size: number of bits per group (for spacing)
    """
    print(f"\nDecoded bits: ({len(bits)} @ {group_size})", flush=True)
    ONES_THRESHOLD = 32
    LONG_WORD = group_size * 8
    i = 0
    while i < len(bits):
        if bits[i] == 1:
            run = 1
            while (i + run < len(bits)) and (bits[i + run] == 1):
                run += 1
            if run > ONES_THRESHOLD:
                print(f"1x{run}", flush=True)
                i += run
                continue
        line_bits = bits[i:i+LONG_WORD]
        out = []
        j = 0
        while j < len(line_bits):
            if line_bits[j] == 1:
                run = 1
                while (j + run < len(line_bits)) and (line_bits[j + run] == 1):
                    run += 1
                if run > ONES_THRESHOLD:
                    break
                else:
                    out.extend(['1'] * run)
                    j += run
            else:
                out.append('0')
                j += 1
        grouped = []
        k = 0
        while k < len(out):
            grouped.append(''.join(out[k:k+group_size]))
            k += group_size
        if grouped:
            print(' '.join(grouped), flush=True)
        i += len(out)

def decode_uart(bits, baud=38400, nbits=8, nparity=1, nstop=2):
    """
    Decodes a bitstream into hex bytes using a fixed-frame window.
    Validates Start, Parity, and Stop bits for the 8E2 (or custom) protocol.
    """
    # frame_len for 8E2 is 1 (start) + 8 (data) + 1 (parity) + 2 (stop) = 12
    frame_len = 1 + nbits + nparity + nstop
    bytes_found = []

    # Process bits in chunks of frame_len
    for i in range(0, len(bits), frame_len):
        frame = bits[i : i + frame_len]
        
        # Ensure we have a complete frame to work with
        if len(frame) < frame_len:
            break
            
        # 1. Validate Start Bit (always 0) and Stop Bits (always 1)
        # For 8E2, frame[-1] and frame[-2] must be 1
        start_ok = (frame[0] == 0)
        stop_ok = all(bit == 1 for bit in frame[frame_len - nstop : frame_len])
        
        if start_ok and stop_ok:
            # 2. Extract Data Bits (Least Significant Bit First)
            # Data usually starts at index 1 and goes for nbits
            data_bits = frame[1 : 1 + nbits]
            
            byte_val = 0
            for shift, bit in enumerate(data_bits):
                if bit:
                    byte_val |= (1 << shift)
            
            # 3. Optional: Parity Validation
            # In 8E2 (Even), (sum of data bits + parity bit) % 2 should be 0
            if nparity > 0:
                parity_bit = frame[1 + nbits]
                actual_parity = (sum(data_bits) + parity_bit) % 2
                if actual_parity != 0:
                    # You can log a parity error here if needed
                    pass

            bytes_found.append(f"0x{byte_val:02X}")
        else:
            # Framing error - likely out of sync or noise
            # bytes_found.append("??") 
            pass

    if bytes_found:
        print(f"Decoded {len(bytes_found)} bytes: {' '.join(bytes_found)}", flush=True)
        
    return bytes_found

def decode_uart(bits, nbits=8, nparity=1, nstop=2):
    frame_len = 1 + nbits + nparity + nstop # 12
    bytes_found = []
    
    for i in range(0, len(bits), frame_len):
        frame = bits[i:i+frame_len]
        if len(frame) < frame_len: break
        
        # Standard UART: Start(0), Data(8), Parity(1), Stop(2)
        # Data is index 1 to 8. We MUST use LSB-first.
        data_bits = frame[1:9] 
        byte_val = 0
        for shift, bit in enumerate(data_bits):
            if bit:
                byte_val |= (1 << shift)
        
        bytes_found.append(byte_val)
    return bytes_found

def decode_uart(bits, nbits=8, nparity=1, nstop=2):
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

def analyze_transitions(snapshot):
    if len(snapshot) < 2:
        print("No transitions captured.", flush=True)
        return []
    
    durations = []
    for i in range(len(snapshot) - 1):
        level = snapshot[i][0]
        duration = pigpio.tickDiff(snapshot[i][1], snapshot[i+1][1])
        durations.append((level, duration))
    return durations

def decode_bitstream(durations, baud=38400):
    BIT_US = 1000000.0 / baud
    HALF_BIT = BIT_US / 2.0
    
    # Create absolute timeline
    timeline = []
    t_abs = 0
    for level, dur in durations:
        timeline.append((t_abs, level))
        t_abs += dur

    def get_level(t):
        for edge_t, level in reversed(timeline):
            if edge_t <= t: return level
        return 1

    bits = []
    t = 0
    # Hunt for Start Bit (1 -> 0 transition)
    while t < (t_abs - (BIT_US * 12)):
        # Look for falling edge
        if get_level(t) == 1 and get_level(t + 2) == 0:
            start_edge = t + 2
            # Sample 12 bits at their midpoints
            for i in range(12):
                sample_t = start_edge + (i * BIT_US) + HALF_BIT
                bits.append(get_level(sample_t))
            
            # Jump to the end of the frame (roughly 11 bits in) 
            # to hunt for the NEXT start bit
            t = start_edge + (BIT_US * 11)
        else:
            t += 2 # Slide 2us and hunt
    return bits

def decode_bitstream(durations, baud=38400):
    BIT_US = 1000000.0 / baud
    # SAMPLE_OFFSET = BIT_US / 2.0
    SAMPLE_OFFSET = BIT_US * 0.4 
    
    timeline = []
    t_abs = 0
    for level, dur in durations:
        timeline.append((t_abs, level))
        t_abs += dur

    def get_level(t):
        for edge_t, level in reversed(timeline):
            if edge_t <= t: return level
        return 1

    bits = []
    t = 0

    # NEW: Force-check the very first sample. 
    # If durations[0] is level 0, it's our first start bit!
    if durations and durations[0][0] == 0:
        start_edge = 0
        for i in range(12):
            sample_t = start_edge + (i * BIT_US) + SAMPLE_OFFSET
            bits.append(get_level(sample_t))
        t = start_edge + (BIT_US * 11)

    # Continue hunting for the rest of the stream
    while t < (t_abs - (BIT_US * 12)):
        if get_level(t) == 1 and get_level(t + 2) == 0:
            start_edge = t + 2
            for i in range(12):
                sample_t = start_edge + (i * BIT_US) + SAMPLE_OFFSET
                bits.append(get_level(sample_t))
            t = start_edge + (BIT_US * 11)
        else:
            t += 2 
    return bits

def decode_bitstream(durations, baud=38400):
    BIT_US = 1000000.0 / baud
    HALF_BIT = BIT_US / 2.0
    
    # 1. Convert to absolute timeline
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
        # Move pointer forward to the correct edge
        while ptr + 1 < len(timeline) and timeline[ptr+1][0] <= target_t:
            ptr += 1
        return timeline[ptr][1]

    # 2. Logic to handle the very first byte if it starts at 0
    if durations and durations[0][0] == 0:
        start_edge = 0
        for i in range(12):
            bits.append(get_level_fast(start_edge + (i * BIT_US) + HALF_BIT))
        t = start_edge + (BIT_US * 11)

    # 3. Efficient Hunt and Sample
    while t < (t_abs - (BIT_US * 12)):
        # Efficient hunt: Find next 1 -> 0 transition
        # We step by half-bits during the hunt for speed, then refine
        if get_level_fast(t) == 1 and get_level_fast(t + 2) == 0:
            # We found a falling edge, refine to the exact microsecond
            start_edge = t
            while start_edge < t + 5 and get_level_fast(start_edge) == 1:
                start_edge += 1
            
            # Sample 12 bits (Start + 8 Data + 1 Control + 2 Stop)
            for i in range(12):
                bits.append(get_level_fast(start_edge + (i * BIT_US) + HALF_BIT))
            
            # Jump forward
            t = start_edge + (BIT_US * 11.5)
        else:
            t += 2 # Move faster through idle
            
    return bits

def decode_bitstream(durations, baud=38400):
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
                t1 = start_edge + (i * BIT_US) + (BIT_US * 0.55)
                t2 = start_edge + (i * BIT_US) + (BIT_US * 0.60)
                t3 = start_edge + (i * BIT_US) + (BIT_US * 0.65)
                
                v1 = get_level_fast(t1)
                v2 = get_level_fast(t2)
                v3 = get_level_fast(t3)
                
                # Majority vote
                bits.append(1 if (v1 + v2 + v3) >= 2 else 0)

            t = start_edge + (BIT_US * 11.2)
        else:
            t += 1
            
    return bits

def data_callback(gpio, level, tick):
    global transitions, capturing, last_event_tick, last_idle_tick

    if not capturing:
        if level == 0: 
            # Measure from the last time it went HIGH until NOW (the falling edge)
            if pigpio.tickDiff(last_idle_tick, tick) > (GAP_MS * 1000):
                transitions = [(0, tick)]
                capturing = True
        else:
            # Mark the time the line went HIGH
            last_idle_tick = tick
    else:
        transitions.append((level, tick))
        last_event_tick = tick


def split_durations_by_long_idle(durations, baud=38400, threshold_bits=32):
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

def decode_fixed(durations, baud=38400):
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

def print_hex_data(data_bytes, n=16):
    """
    Prints four columns: 
    Address, Hex, ASCII (raw), and ASCII (masked 0x7F).
    """
    if not data_bytes:
        return

    # Convert to integers
    ints = [int(b, 16) if isinstance(b, str) else b for b in data_bytes]

    # Header
    hex_header = "Hex Values".ljust(n * 4)
    print(f"{'Address':<8} {hex_header} | {'ASCII':<{n}} | {'Masked ASCII'}", flush=True)
    print("-" * (10 + (n * 4) + (n * 2) + 6), flush=True)

    for i in range(0, len(ints), n):
        chunk = ints[i : i + n]
        
        # 1. Address
        addr = f"{i:04X}: "
        
        # 2. Hex values
        hex_vals = " ".join(f"{b:03X}" for b in chunk).ljust(n * 4)
        
        # 3. Raw ASCII
        raw_ascii = "".join((chr(b & 0xff) if 32 <= (b & 0xff) <= 126 else ".") for b in chunk).ljust(n)
        
        # 4. Masked ASCII (b & 0x7F)
        masked_ascii = "".join((chr(b & 0x7F) if 32 <= (b & 0x7F) <= 126 else ".") for b in chunk)
        
        print(f"{addr} {hex_vals} | {raw_ascii} | {masked_ascii}", flush=True)

def main():
    global pi, callback, capturing, last_event_tick, last_idle_tick, transitions

    print(f"Starting Logic Analyzer on GPIO {DATA_PIN}...", flush=True)
    transitions = []              # Clear the global for the next burst

    try:
        pi = pigpio.pi()
        if not pi.connected:
            print("Error: Could not connect to pigpiod. Is it running?", flush=True)
            print("Start it with: sudo systemctl enable --now pigpiod", flush=True)
            return

        # Set up GPIO mode
        pi.set_mode(DATA_PIN, pigpio.INPUT)
        pi.set_pull_up_down(DATA_PIN, pigpio.PUD_OFF) 

        # Set a glitch filter to ignore noise pulses shorter than 15 microseconds
        # pi.set_glitch_filter(DATA_PIN, 2)
        # print("Glitch filter set to 15 us.", flush=True)

        # Create the callback that will fire on each signal change
        callback = pi.callback(DATA_PIN, pigpio.EITHER_EDGE, data_callback)
        last_event_tick = pi.get_current_tick()
        last_idle_tick = pi.get_current_tick() - (GAP_MS * 2000) 

        print("Waiting for signal changes... (Ctrl-C to stop)", flush=True)
        print("Trigger the Cybiko to send data now.", flush=True)

        while True:
            if len(transitions) > 0:
                now = pi.get_current_tick()
                # How long since the last bit?
                silence_duration = pigpio.tickDiff(last_event_tick, now)
                print(f"Silence duration: {silence_duration} us", flush=True)

                if silence_duration > (GAP_MS * 1000):
                    # 1. LOCK the thread by copying the data immediately
                    # Do NOT reset 'capturing' yet, let the callback finish its thought
                    raw_snapshot = list(transitions)
                    transitions = [] 
                    capturing = False # Tell the callback we are ready for a fresh start bit

                    # 2. Re-anchor the snapshot with a final virtual transition
                    # This 'closes' the last bit duration so the decoder can see it
                    if raw_snapshot:
                        last_level, _ = raw_snapshot[-1]
                        raw_snapshot.append((last_level, now))
                    else:
                        print("No transitions captured in snapshot.", flush=True)
                        capturing = False
                        continue

                    # 3. Process the snapshot
                    durations = analyze_transitions(raw_snapshot)
                    if durations:
                        # Use a small threshold for internal byte gaps
                        streams = split_durations_by_long_idle(durations, baud=38400, threshold_bits=20)
                        for idx, stream in enumerate(streams):
                            bits = decode_bitstream(stream, baud=38400)
                            print_bitstream(bits, 12)
                            decoded_bytes = decode_uart(bits, 8, 1, 2) # 8E2
                            # decoded_bytes = decode_fixed(stream, baud=38400)
                            print(f"\n--- Stream {idx+1}: {len(decoded_bytes)} bytes ---", flush=True)
                            print_hex_data(decoded_bytes, 16)
                    else:
                        print("No durations to analyze.", flush=True)

                    # 4. Ready for next packet
                    capturing = False 
                    print("--- Transaction Complete ---", flush=True)
            else:
                # print("Idle...", flush=True)
                pass

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nStopping analyzer...", flush=True)
    finally:
        if callback:
            callback.cancel()
        if pi and pi.connected:
            pi.stop()
        print("Cleanup complete. Exiting.", flush=True)

if __name__ == "__main__":
    main()
