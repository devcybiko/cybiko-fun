import RPi.GPIO as GPIO
import time

PIN = 17  # BCM numbering

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

t0 = time.monotonic()

def cb(channel):
    t = (time.monotonic() - t0) * 1000
    level = GPIO.input(PIN)
    print(f"{t:9.3f} ms  level={level}")

GPIO.add_event_detect(PIN, GPIO.BOTH, callback=cb)

print("Watching -RST_AVR edges... Ctrl-C to stop.")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    GPIO.cleanup()
