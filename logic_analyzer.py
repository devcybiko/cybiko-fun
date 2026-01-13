import time
import pigpio

# --- GPIO Pin Configuration (BCM numbering) ---
# !!! IMPORTANT !!!
# You MUST change this pin number to match your wiring.
DATA_PIN = 9   # The GPIO pin to analyze (e.g., RX_AVR)

# --- Analysis Settings ---
# Time in milliseconds with no signal change to be considered a gap
GAP_MS = 10

# --- Global State Variables ---
pi = None
callback = None
transitions = []
capturing = False
last_event_tick = 0

def analyze_transitions():
    """Processes the recorded transitions and prints an analysis."""
    global transitions
    if not transitions:
        return

    print(f"\n--- Analysis of {len(transitions)} Signal Changes ---")
    
    # Add a final "now" tick to calculate the duration of the last level
    final_tick = transitions[-1][1]
    transitions.append((transitions[-1][0], final_tick + 1))

    for i in range(len(transitions) - 1):
        level = transitions[i][0]
        start_tick = transitions[i][1]
        end_tick = transitions[i+1][1]
        
        # pigpio ticks are in microseconds
        duration = pigpio.tickDiff(start_tick, end_tick)
        
        print(f"Level: {level}, Duration: {duration} us")

    print("--- End of Analysis ---\n")
    transitions = []

def data_callback(gpio, level, tick):
    """
    This function is called on every signal change (edge).
    It records the level and the microsecond timestamp.
    """
    global transitions, capturing, last_event_tick

    # On the first edge, record the initial state and start capturing
    if not capturing:
        # Get the level *before* this transition
        initial_level = 1 if level == 0 else 0
        # Find the tick right before the first edge
        initial_tick = tick - 1 
        transitions.append((initial_level, initial_tick))
        capturing = True

    transitions.append((level, tick))
    last_event_tick = tick

def main():
    global pi, callback, capturing, last_event_tick

    print(f"Starting Logic Analyzer on GPIO {DATA_PIN}...")
    
    try:
        pi = pigpio.pi()
        if not pi.connected:
            print("Error: Could not connect to pigpiod. Is it running?")
            print("Start it with: sudo systemctl enable --now pigpiod")
            return

        # Set up GPIO mode
        pi.set_mode(DATA_PIN, pigpio.INPUT)

        # Set a glitch filter to ignore noise pulses shorter than 15 microseconds
        pi.set_glitch_filter(DATA_PIN, 15)
        print("Glitch filter set to 15 us.")

        # Create the callback that will fire on each signal change
        callback = pi.callback(DATA_PIN, pigpio.EITHER_EDGE, data_callback)
        last_event_tick = pi.get_current_tick()
        
        print("Waiting for signal changes... (Ctrl-C to stop)")
        print("Trigger the Cybiko to send data now.")

        while True:
            # If we are capturing, check for a gap to end the capture
            if capturing:
                tick_diff = pigpio.tickDiff(last_event_tick, pi.get_current_tick())
                if tick_diff > (GAP_MS * 1000):
                    analyze_transitions()
                    capturing = False
                    print("Capture finished. Waiting for new signal changes...")
            
            time.sleep(0.01) # Main loop sleep

    except KeyboardInterrupt:
        print("\nStopping analyzer...")
    finally:
        if callback:
            callback.cancel()
        if pi and pi.connected:
            pi.stop()
        print("Cleanup complete. Exiting.")

if __name__ == "__main__":
    main()
