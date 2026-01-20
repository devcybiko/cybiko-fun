import time
import pigpio

# --- GPIO Pin Configuration (BCM numbering) ---
# !!! IMPORTANT !!!
# You MUST change these pin numbers to match your wiring.
SCK_PIN  = 11  # Serial Clock (SCK_AVR)
DATA_PIN = 9   # Serial Data (RX_AVR / MISO)

# --- Protocol Settings ---
CLOCK_EDGE = pigpio.RISING_EDGE # Or pigpio.FALLING_EDGE
BITS_PER_BYTE = 8
GAP_MS = 20 # Milliseconds without a clock signal = end of transmission

# --- Global State Variables ---
pi = None
callback = None
byte_buffer = bytearray()
current_byte = 0
bit_count = 0
last_clock_tick = 0

def format_hexdump(data: bytes):
    """Creates aligned hex and ASCII strings for printing."""
    hex_str = " ".join(f"{b:02x}" for b in data)
    ascii_str = "".join(chr(b) if 32 <= b <= 126 else '.' for b in data)
    return hex_str, ascii_str

def clock_callback(gpio, level, tick):
    """
    This function is called on every clock edge.
    It reads the data bit and assembles the bytes.
    """
    global current_byte, bit_count, byte_buffer, last_clock_tick

    # Read the data bit at the exact moment of the clock pulse
    data_bit = pi.read(DATA_PIN)

    # Shift the new bit into our current byte
    # We shift left and add the new bit.
    current_byte = (current_byte << 1) | data_bit
    bit_count += 1

    # If we have a full byte, add it to the buffer and reset
    if bit_count == BITS_PER_BYTE:
        byte_buffer.append(current_byte)
        current_byte = 0
        bit_count = 0

    # Record the time of this clock tick
    last_clock_tick = tick

def main():
    global pi, callback, last_clock_tick

    print("Starting SPI sniffer...")
    print(f"Clock Pin: {SCK_PIN}, Data Pin: {DATA_PIN}")

    try:
        pi = pigpio.pi()
        if not pi.connected:
            print("Error: Could not connect to pigpiod. Is it running?")
            print("Start it with: sudo systemctl enable --now pigpiod")
            return

        # Set up GPIO modes
        pi.set_mode(SCK_PIN, pigpio.INPUT)
        pi.set_mode(DATA_PIN, pigpio.INPUT)

        # Optional: Set pull-downs if the lines are floating
        # pi.set_pull_up_down(SCK_PIN, pigpio.PUD_DOWN)
        # pi.set_pull_up_down(DATA_PIN, pigpio.PUD_DOWN)

        # Create the callback that will fire on each clock pulse
        callback = pi.callback(SCK_PIN, CLOCK_EDGE, clock_callback)
        last_clock_tick = pi.get_current_tick()
        print("Sniffer running. Waiting for data... (Ctrl-C to stop)")

        while True:
            # Check if there's been a gap in communication
            if byte_buffer:
                # pigpio ticks are microseconds.
                # Compare time difference in microseconds.
                tick_diff = pigpio.tickDiff(last_clock_tick, pi.get_current_tick())
                if tick_diff > (GAP_MS * 1000):
                    print(f"\n--- Packet Captured ({len(byte_buffer)} bytes) ---")
                    hex_out, ascii_out = format_hexdump(byte_buffer)
                    print(f"HEX:  {hex_out}")
                    print(f"ASCII: {ascii_out}")
                    byte_buffer.clear()

            time.sleep(0.01) # Main loop sleep

    except KeyboardInterrupt:
        print("\nStopping sniffer...")
    finally:
        if callback:
            callback.cancel()
        if pi and pi.connected:
            pi.stop()
        print("Cleanup complete. Exiting.")

if __name__ == "__main__":
    main()
