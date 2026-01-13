import serial
import time

UART_DEV = "/dev/ttyS0"
BAUD = 38400  # try others if needed

ser = serial.Serial("/dev/ttyAMA0", BAUD,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.1)

def print_printable_ascii(data):
    """
    Prints each byte as a printable ASCII character (or a dot)
    followed by its hex representation.
    """
    output_ascii = []
    output_hex = []
    for byte in data:
        # Printable ASCII characters are in the range 32 (space) to 126 (~)
        char = chr(byte) if 32 <= byte <= 126 else '.' 
        hex_code = f"{byte:02x}"
        output_hex.append(f"{hex_code} ")
        output_ascii.append(f"{char}  ")
    print("HEX:", " ".join(output_hex))
    print("ASC:", " ".join(output_ascii))


print("Listening...")
while True:
    data = ser.read(256)
    if data:
        print("RX:", data.hex(" "))
        print_printable_ascii(data)