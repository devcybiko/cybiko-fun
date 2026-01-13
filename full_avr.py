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

def ascii_runs(data: bytes):
    runs = []
    run = bytearray()
    for b in data:
        if 32 <= b <= 126:
            run.append(b)
        else:
            run.append(ord('.'))
            #if len(run) >= 3:
            #    runs.append(run.decode("ascii", errors="ignore"))
            #run.clear()
            pass
    if len(run) >= 3:
        runs.append(run.decode("ascii", errors="ignore"))
    return runs

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
                delta = (now - then) * 1000.0
                print(f"{delta:9.3f} ms {ms():9.3f} ms  UART burst len={len(frame)}")
                print(frame.hex(" "))
                runs = ascii_runs(frame)
                if runs:
                    print("ASCII:", runs)
                buf.clear()
                last_rx = None

except KeyboardInterrupt:
    cb.cancel()
    pi.stop()
    ser.close()
