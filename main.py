import time
import serial
from typing import Dict, Any, Optional
import pigpio
from gpio_uart import GpioUart
from hard_uart import HardUart

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
    gpio_uart = GpioUart(pigpio.pi(), data_pin=9)
    hard_uart = HardUart(port='/dev/ttyAMA5', baud=38400, gap_sec=0.01)
    print(f"Starting Logic Analyzer on GPIO {gpio_uart.DATA_PIN}...", flush=True)
    transitions = []              # Clear the global for the next burst

    try:
        gpio_uart.init_pigpio() 

        print("Waiting for signal changes... (Ctrl-C to stop)", flush=True)
        print("Trigger the Cybiko to send data now.", flush=True)

        while True:
            hard_uart.read_bytes()  # Read from hardware UART
            hard_uart.process_burst()  # Process any complete frames

            if len(gpio_uart.transitions) > 0:
                now = gpio_uart.pi.get_current_tick()
                # How long since the last bit?
                silence_duration = pigpio.tickDiff(gpio_uart.last_event_tick, now)
                print(f"Silence duration: {silence_duration} us", flush=True)

                if silence_duration > (gpio_uart.GAP_MS * 1000):
                    # 1. LOCK the thread by copying the data immediately
                    # Do NOT reset 'capturing' yet, let the callback finish its thought
                    raw_snapshot = list(gpio_uart.transitions)
                    gpio_uart.transitions = [] 
                    gpio_uart.capturing = False # Tell the callback we are ready for a fresh start bit

                    # 2. Re-anchor the snapshot with a final virtual transition
                    # This 'closes' the last bit duration so the decoder can see it
                    if raw_snapshot:
                        last_level, _ = raw_snapshot[-1]
                        raw_snapshot.append((last_level, now))
                    else:
                        print("No transitions captured in snapshot.", flush=True)
                        gpio_uart.capturing = False
                        continue

                    # 3. Process the snapshot
                    durations = gpio_uart.analyze_transitions(raw_snapshot)
                    if durations:
                        # Use a small threshold for internal byte gaps
                        streams = gpio_uart.split_durations_by_long_idle(durations, baud=38400, threshold_bits=20)
                        for idx, stream in enumerate(streams):
                            bits = gpio_uart.decode_bitstream(stream, baud=38400)
                            print_bitstream(bits, 12)
                            decoded_bytes = gpio_uart.decode_uart(bits, 8, 1, 2) # 8E2
                            # decoded_bytes = decode_fixed(stream, baud=38400)
                            print(f"\n--- Stream {idx+1}: {len(decoded_bytes)} bytes ---", flush=True)
                            print_hex_data(decoded_bytes, 16)
                    else:
                        print("No durations to analyze.", flush=True)

                    # 4. Ready for next packet
                    gpio_uart.capturing = False 
                    print("--- Transaction Complete ---", flush=True)
            else:
                # print("Idle...", flush=True)
                pass

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nStopping analyzer...", flush=True)
    finally:
        if gpio_uart.callback:
            gpio_uart.callback.cancel()
        if gpio_uart.pi and gpio_uart.pi.connected:
            gpio_uart.pi.stop()
        print("Cleanup complete. Exiting.", flush=True)

if __name__ == "__main__":
    main()
