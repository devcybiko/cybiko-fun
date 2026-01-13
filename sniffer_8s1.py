import serial
import time
import sys

# --- Configuration ---
SERIAL_PORT = '/dev/serial0'  # Default hardware UART on Raspberry Pi
BAUD_RATE = 38400

def format_bytes(byte_data):
    """Formats a byte string into a hex and ASCII representation."""
    if not byte_data:
        return ""
    
    hex_str = ' '.join(f'{b:02x}' for b in byte_data)
    ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in byte_data)
    return f"Hex: {hex_str}\nASCII: {ascii_str}\n"

def main():
    """
    Initializes and runs the serial sniffer with 8S1 settings.
    """
    print(f"Starting 8S1 (Space Parity) sniffer on {SERIAL_PORT} at {BAUD_RATE} bps...")
    print("Press Ctrl-C to stop.")

    try:
        # Configure and open the serial port
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUD_RATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_SPACE,  # Key setting for RX_AVR
            stopbits=serial.STOPBITS_ONE,
            timeout=0.1  # Non-blocking read
        )
    except serial.SerialException as e:
        print(f"Error: Could not open serial port {SERIAL_PORT}.")
        print(f"Details: {e}")
        print("\nPlease ensure the hardware UART is enabled and not used by a serial console.")
        print("Check your /boot/firmware/cmdline.txt and /boot/firmware/config.txt settings.")
        sys.exit(1)

    try:
        while True:
            # Check if there's data waiting
            if ser.in_waiting > 0:
                # Read all available data
                data = ser.read(ser.in_waiting)
                
                # Print the formatted output
                print(format_bytes(data), end='', flush=True)
            
            time.sleep(0.05) # Small delay to prevent high CPU usage

    except KeyboardInterrupt:
        print("\nStopping sniffer...")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("Serial port closed.")

if __name__ == "__main__":
    main()
