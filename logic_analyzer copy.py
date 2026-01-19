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
pi = None
callback = None
transitions = []
capturing = False
last_event_tick = 0

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


def decode_uart(bits, baud, nbits, nparitybits, nstopbits):
    """
    Decode a bitstream as UART frames.
    bits: list of 0/1 bits (LSB first per UART frame)
    baud: baud rate (for info only, not used here)
    nbits: number of data bits per frame (e.g., 8)
    nparitybits: number of parity bits per frame (0 or 1)
    nstopbits: number of stop bits per frame (usually 1 or 2)
    Prints decoded bytes and frame info.
    """
    frame_len = 1 + nbits + nparitybits + nstopbits
    print(f"\nUART decode: baud={baud}, nbits={nbits}, nparitybits={nparitybits}, nstopbits={nstopbits} frames={len(bits) // frame_len}", flush=True)
    start_idx = first_frame(bits, nbits, nparitybits, nstopbits)
    if start_idx is None:
        print("No va:qlid frame found in bitstream.", flush=True)
        return
    print(f"First valid frame found at bit index {start_idx}", flush=True)
    i = start_idx
    frame_count = 0
    while i <= len(bits) - frame_len:
        frame = bits[i:i+frame_len]
        start = frame[0]
        data = frame[1:1+nbits]
        parity = frame[1+nbits:1+nbits+nparitybits] if nparitybits else []
        stop = frame[1+nbits+nparitybits:]
        value = 0
        for j, b in enumerate(data):
            value |= (b << j)
        parity_str = ''.join(str(b) for b in parity) if parity else ''
        data_msb_first = list(reversed(data))
        if 32 <= value <= 126:
            ascii_char = chr(value)
        else:
            ascii_char = '.'
        if start == 0 and all(s == 1 for s in stop):
            print(f"Frame {frame_count} (start={i}): 0x{value:02X} (data={data_msb_first}, parity={parity_str}, stop={stop}) '{ascii_char}' 0x{value:02X}", flush=True)
        else:
            print(f"  Frame {frame_count} (start={i}): framing error (start={start}, stop={stop}) 0x{value:02X} (data={data_msb_first}, parity={parity_str}, stop={stop}) '{ascii_char}' 0x{value:02X}", flush=True)
        frame_count += 1
        i += frame_len

def analyze_transitions():
    """Processes the recorded transitions and prints an analysis."""
    global transitions
    if not transitions:
        return

    # Add a final "now" tick to calculate the duration of the last level
    final_tick = transitions[-1][1]
    transitions.append((transitions[-1][0], final_tick + 1))

    # Prepare list of (level, duration) tuples
    durations = []
    for i in range(len(transitions) - 1):
        level = transitions[i][0]
        start_tick = transitions[i][1]
        end_tick = transitions[i+1][1]
        duration = pigpio.tickDiff(start_tick, end_tick)
        durations.append((level, duration))

    # Call decode function with durations
    bits = decode_bitstream(durations)
    print_bitstream(bits, 12)
    decode_uart(bits, 38400, 8, 1, 2)


def decode_bitstream(durations):
    """
    Attempt to decode a bitstream (0/1) from a list of (level, duration) tuples.
    This is a stub for now; implement decoding logic based on timing thresholds.
    """
    print(f"Decoding {len(durations)} transitions...", flush=True)
    # Use 38400 baud to determine bit duration threshold
    if not durations:
        print("No durations to decode.", flush=True)
        return

    # 38400 baud = 1/38400 seconds per bit = ~26.04 us per bit
    BIT_US = int(1_000_000 / 38400)  # 26 us per bit
    # For a '1' bit, expect a duration close to BIT_US; for a '0', could be protocol-specific
    # If protocol uses NRZ, each transition is a bit; if UART, need to decode start/stop bits

    # For now, classify any duration within 50% of BIT_US as a bit, longer as multiple bits
    tolerance = BIT_US // 2

    bits = []
    MIN_BIT_US = int(BIT_US * 0.7)
    # MAX_BIT_US = int(BIT_US * 1.3 * 16)  # allow up to 16 bits in a long run
    for level, dur in durations:
        # Ignore durations that are too short (likely noise)
        # if dur < MIN_BIT_US:
        #     continue
        nbits = int((dur + tolerance) // BIT_US)
        if nbits < 1:
            continue
        bits.extend([level] * nbits)

    # --- Bitstream shift option ---
    SHIFT_BITS = True  # Set to True to insert a 1 at the head for bit alignment
    if SHIFT_BITS:
        # bits = bits[1:]
        # bits = bits[1:]
        # bits = bits[1:]
        # bits = bits[1:]
        # bits = [0] + bits
        # bits = [0] + bits
        pass

    print(f"{len(bits)} bits: Used bit duration: {BIT_US} us (38400 baud)", flush=True)
    return bits

def data_callback(gpio, level, tick):
    """
    This function is called on every signal change (edge).
    It records the level and the microsecond timestamp.
    """
    global transitions, capturing, last_event_tick

    # On the first edge, record the initial state and start capturing
    if not capturing:
        # Get the level *before* this transition
        # initial_level = 1 if level == 0 else 0
        initial_level = 1
        # Find the tick right before the first edge
        initial_tick = tick - 1 
        transitions.append((initial_level, initial_tick))
        capturing = True

    transitions.append((level, tick))
    last_event_tick = tick

def main():
    global pi, callback, capturing, last_event_tick

    print(f"Starting Logic Analyzer on GPIO {DATA_PIN}...", flush=True)
    
    try:
        pi = pigpio.pi()
        if not pi.connected:
            print("Error: Could not connect to pigpiod. Is it running?", flush=True)
            print("Start it with: sudo systemctl enable --now pigpiod", flush=True)
            return

        # Set up GPIO mode
        pi.set_mode(DATA_PIN, pigpio.INPUT)

        # Set a glitch filter to ignore noise pulses shorter than 15 microseconds
        pi.set_glitch_filter(DATA_PIN, 15)
        print("Glitch filter set to 15 us.", flush=True)

        # Create the callback that will fire on each signal change
        callback = pi.callback(DATA_PIN, pigpio.EITHER_EDGE, data_callback)
        last_event_tick = pi.get_current_tick()
        
        print("Waiting for signal changes... (Ctrl-C to stop)", flush=True)
        print("Trigger the Cybiko to send data now.", flush=True)

        while True:
            # If we are capturing, check for a gap to end the capture
            if capturing:
                tick_diff = pigpio.tickDiff(last_event_tick, pi.get_current_tick())
                if tick_diff > (GAP_MS * 1000):
                    analyze_transitions()
                    capturing = False
                    print("Capture finished. Waiting for new signal changes...", flush=True)
            
            time.sleep(0.01) # Main loop sleep

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
