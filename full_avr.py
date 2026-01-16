import time
import serial
import pigpio

UART_DEV = "/dev/ttyAMA0"
BAUD = 38400            # set to whatever is now confirmed working
SER_TIMEOUT = 0.002

RST_PIN = 17            # BCM
GAP_SEC = 0.010       # 20ms gap => end of burst/frame

pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("pigpio not running (start with: sudo systemctl enable --now pigpiod)")

pi.set_mode(RST_PIN, pigpio.INPUT)
pi.set_pull_up_down(RST_PIN, pigpio.PUD_UP)
pi.set_pull_up_down(15, pigpio.PUD_OFF) # Disable pull on RX pin

# ser = serial.Serial(UART_DEV, BAUD, timeout=SER_TIMEOUT,
#                     bytesize=serial.EIGHTBITS, parity=serial.PARITY_MARK,
#                     stopbits=serial.STOPBITS_ONE)
ser = serial.Serial(UART_DEV, BAUD, timeout=SER_TIMEOUT,
                    bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE)
t0 = time.monotonic()
buf = bytearray()
last_rx = None

def ms():
    return (time.monotonic() - t0) * 1000.0

def strip_msb(frame: bytes) -> bytes:
    """Strips the most significant bit from each byte in the frame."""
    return bytes(b & 0x7F for b in frame)

def extract_msbs(frame: bytes) -> str:
    """Extracts the most significant bit from each byte and returns a string of '1's and '.'s."""
    return "".join('1' if b & 0x80 else '.' for b in frame)

def print_frame(frame: bytes | str):
    """Prints the frame in a classic hexdump format."""
    is_bytes = isinstance(frame, bytes)
    for i in range(0, len(frame), 16):
        chunk = frame[i:i+16]
        
        # Address
        addr = f"{i:08x}"
        
        # Hex values
        if is_bytes:
            hex_part = " ".join(f"{b:02x}" for b in chunk)
        else:
            hex_part = " ".join(f"{ord(c):02x}" for c in chunk)
        hex_part = hex_part.ljust(16 * 3 - 1) # Pad to 16 bytes width

        # ASCII values
        if is_bytes:
            ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        else:
            ascii_part = chunk
        
        print(f"{addr}  {hex_part}  |{ascii_part}|")
    print("")

def rst_cb(gpio, level, tick):
    if level == 0:
        print(f"{ms():9.3f} ms  RST_AVR FALL  (disabled/reset asserted)")
    elif level == 1:
        print(f"{ms():9.3f} ms  RST_AVR RISE  (enabled/reset released)")

cb = pi.callback(RST_PIN, pigpio.EITHER_EDGE, rst_cb)

print("Logging RST_AVR + UART... Ctrl-C to stop.")
print(f"{ms():9.3f} ms  Initial RST_AVR level={pi.read(RST_PIN)}")

try:
    while True:
        data = ser.read(256)
        now = time.monotonic()
        if data:
            buf.extend(data)
            last_rx = now
        else:
            if buf and last_rx and (now - last_rx) >= GAP_SEC:
                frame = bytes(buf)
                then = time.monotonic()
                delta = (then - now) * 1000.0
                print(f"{delta:9.3f} ms {ms():9.3f} ms  UART burst len={len(frame)}")
                print_frame(frame)
                msbs = extract_msbs(frame)
                print_frame(msbs)
                frame = strip_msb(frame)
                print_frame(frame)
                buf.clear()
                last_rx = None

except KeyboardInterrupt:
    cb.cancel()
    pi.stop()
    ser.close()
