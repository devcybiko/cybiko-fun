import time
import pigpio

DATA_PIN = 9   # The GPIO pin to analyze (e.g., RX_AVR)

global pi, callback, transitions
pi = None
callback = None
transitions = []

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

def simple_callback(gpio, level, tick):
    global transitions, capturing, last_event_tick, last_idle_tick

    transitions.append((level, tick))
    print(f"Callback: Level {level} at tick {tick}", flush=True)

def init_pigpio():
    global pi, callback

    pi = pigpio.pi()
    if not pi.connected:
        print("Error: Could not connect to pigpiod. Is it running?", flush=True)
        print("Start it with: sudo systemctl enable --now pigpiod", flush=True)
        raise SystemExit(1)

    # Set up GPIO mode
    pi.set_mode(DATA_PIN, pigpio.INPUT)
    pi.set_pull_up_down(DATA_PIN, pigpio.PUD_OFF) 
    # pi.set_glitch_filter(DATA_PIN, 2)
    callback = pi.callback(DATA_PIN, pigpio.EITHER_EDGE, simple_callback)

def main():
    global pi, callback, transitions

    print(f"Starting Logic Analyzer on GPIO {DATA_PIN}...", flush=True)
    transitions = []              # Clear the global for the next burst

    try:
        init_pigpio() 

        print("Waiting for signal changes... (Ctrl-C to stop)", flush=True)
        print("Trigger the Cybiko to send data now.", flush=True)

        while True:
            if len(transitions) > 0:
                print(f"Captured {len(transitions)} transitions.", flush=True)
                print(f"{transitions}")
                transitions = []

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
