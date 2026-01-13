import time
import serial
import pigpio

# --- First Port (Hardware UART) ---
HW_UART_DEV = "/dev/ttyAMA0"
BAUD = 38400
SER_TIMEOUT = 0.002

# ... other settings ...
ser_hw = serial.Serial(HW_UART_DEV, BAUD, timeout=SER_TIMEOUT,
                    bytesize=serial.EIGHTBITS, parity=serial.PARITY_MARK,
                    stopbits=serial.STOPBITS_ONE)

# --- Second Port (Software UART via pigpio) ---
SW_RX_PIN = 23 # The GPIO pin you connect the second line to
GAP_SEC = 0.010 # 10ms gap => end of burst/frame

pi = pigpio.pi()
if not pi.connected:
    # ... handle error ...
    print("ERROR")

# Buffers and timestamps for each port
buf_hw = bytearray()
last_rx_hw = None
buf_sw = bytearray()
last_rx_sw = None

# Configure the software serial port
pi.set_mode(SW_RX_PIN, pigpio.INPUT)
pi.bb_serial_read_open(SW_RX_PIN, BAUD, 9) # Use 9 data bits for 8M1 protocol

print("Listening on two ports...")

def format_hexdump(data: bytes):
    """
    Creates aligned hex and ASCII strings for printing,
    similar to a hexdump.
    """
    hex_str = " ".join(f"{b:02x}" for b in data)
    
    # Pad each ASCII char to align with the 2-char hex value and its space
    ascii_str = " ".join(f"{(chr(b) if 32 <= b <= 126 else '.'):<2}" for b in data)
    
    return hex_str, ascii_str

t0 = time.monotonic()

def ms():
    """Returns the number of milliseconds since the script started."""
    return (time.monotonic() - t0) * 1000.0

last_print_time = time.monotonic()

try:
    while True:
        now = time.monotonic()
        data_received = False

        # --- Check Hardware Port ---
        data_hw = ser_hw.read(256)
        if data_hw:
            buf_hw.extend(data_hw)
            last_rx_hw = now
            data_received = True

        # --- Check Software Port ---
        (count, data_sw) = pi.bb_serial_read(SW_RX_PIN)
        if count > 0:
            # The data from the software serial port appears to have its MSB inverted.
            # We correct this by performing a bitwise XOR with 0x80 on each byte.
            actual_data = bytearray()
            for i in range(0, len(data_sw), 2):
                word = (data_sw[i+1] << 8) | data_sw[i]
                byte = word & 0xFF
                corrected_byte = byte ^ 0x80
                actual_data.append(corrected_byte)
            
            buf_sw.extend(actual_data)
            last_rx_sw = now
            data_received = True

        # --- Process buffers if there's a gap in transmission ---
        if not data_received:
            if buf_hw and last_rx_hw and (now - last_rx_hw) >= GAP_SEC:
                frame = bytes(buf_hw)
                hex_out, ascii_out = format_hexdump(frame)
                print_time = time.monotonic()
                delta_ms = (print_time - last_print_time) * 1000.0
                last_print_time = print_time
                print(f">>> [{ms():9.3f} ms] HW Port (Cybiko TX): [{len(frame)} bytes] [+{delta_ms:7.3f} ms]")
                print(f"  {hex_out}")
                print(f"  {ascii_out}\n")
                buf_hw.clear()
                last_rx_hw = None

            if buf_sw and last_rx_sw and (now - last_rx_sw) >= GAP_SEC:
                frame = bytes(buf_sw)
                hex_out, ascii_out = format_hexdump(frame)
                print_time = time.monotonic()
                delta_ms = (print_time - last_print_time) * 1000.0
                last_print_time = print_time
                print(f"<<< [{ms():9.3f} ms] SW Port (Cybiko RX): [{len(frame)} bytes] [+{delta_ms:7.3f} ms]")
                print(f"  {hex_out}")
                print(f"  {ascii_out}\n")
                buf_sw.clear()
                last_rx_sw = None
        
        time.sleep(0.001)

except KeyboardInterrupt:
    pi.bb_serial_read_close(SW_RX_PIN)
    pi.stop()
    ser_hw.close()