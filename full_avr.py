import time
import serial
from typing import Dict, Any, Optional


# Configuration for both serial ports, now with per-stream gap_sec
STREAMS_CONFIG: Dict[str, Dict[str, Any]] = {
    "RX_AVR": {
        "port": "/dev/ttyAMA5",
        "baud": 38400,
        "gap_sec": 0.010,
        "bytesize": serial.EIGHTBITS,  # Add data bits config
        "parity": serial.PARITY_ODD,
        "stopbits": serial.STOPBITS_TWO,
    },
    # "TX_AVR": {
    #     "port": "/dev/ttyAMA5",
    #     "baud": 38400,
    #     "gap_sec": 0.005, 
    #     "bytesize": serial.EIGHTBITS,  # Add data bits config
    #     "parity": serial.PARITY_NONE,
    #     "stopbits": serial.STOPBITS_TWO,
    # },
}

SER_TIMEOUT = 0 # 0.001 # Non-blocking read

t0 = time.monotonic()

def ms():
    return (time.monotonic() - t0) * 1000.0

def strip_msb(frame: bytes) -> bytes:
    """Strips the most significant bit from each byte in the frame."""
    return bytes(b & 0x7F for b in frame)

def extract_msbs(frame: bytes) -> str:
    """Extracts the most significant bit from each byte and returns a string of '1's and '.'s."""
    return "".join('1' if b & 0x80 else '.' for b in frame)

def print_frame(frame: bytes, xor_data: Optional[bytes] = None):
    """
    Prints the frame in a consolidated hexdump format.
    Shows raw hex, raw ascii, extracted MSBs, and stripped ascii.
    Optionally shows a fifth column with custom-formatted XOR data.
    """
    for i in range(0, len(frame), 16):
        chunk = frame[i:i+16]
        # Address
        addr = f"{i:08x}"
        # 1. Raw Hex values
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        hex_part = hex_part.ljust(16 * 3 - 1)
        # 2. Raw ASCII values
        raw_ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        raw_ascii_part = raw_ascii_part.ljust(16)
        # 3. Extracted MSBs
        msb_part = "".join('1' if b & 0x80 else '.' for b in chunk)
        msb_part = msb_part.ljust(16)
        # 4. Stripped ASCII values
        stripped_chunk = bytes(b & 0x7F for b in chunk)
        stripped_ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in stripped_chunk)
        stripped_ascii_part = stripped_ascii_part.ljust(16)
        line = f"{addr}  {hex_part}  |{raw_ascii_part}| |{msb_part}| |{stripped_ascii_part}|"
        # 5. Optional XOR data
        if xor_data:
            xor_chunk = xor_data[i:i+16]
            def get_xor_char(b):
                if b == 0x80:
                    return 'X'
                if b == 0x00:
                    return '-'
                return chr(b) if 32 <= b <= 126 else "."
            xor_part = "".join(get_xor_char(b) for b in xor_chunk)
            xor_part = xor_part.ljust(16)
            line += f" |{xor_part}|"
        print(line)
    
    # Checksum calculation and comparison
    if len(frame) > 1:
        computed_checksum = sum(frame[:-1]) & 0xFF
        received_checksum = frame[-1]
        diff = (received_checksum - computed_checksum) & 0xFF
        if diff == 0:
            print(f"Checksum OK: computed 0x{computed_checksum:02X}, received 0x{received_checksum:02X}")
        else:
            print(f"Checksum mismatch: computed 0x{computed_checksum:02X}, received 0x{received_checksum:02X}, diff 0x{diff:02X}")
    print("", flush=True)

class StreamProcessor:
    """Manages the state and processing for a single serial stream."""
    def __init__(self, name: str, port: str, baud: int, parity, gap_sec: float, stopbits, bytesize):
        self.name = name
        self.ser = serial.Serial(port, baud, timeout=SER_TIMEOUT,
                                 bytesize=bytesize, parity=parity,
                                 stopbits=stopbits)
        self.buf = bytearray()
        self.last_rx = None
        self.last_frame = None
        self.gap_sec = gap_sec
        print(f"Listening to {self.name} on {port} at {baud} baud (gap_sec={gap_sec}, {bytesize}{parity}{stopbits})...")

    def read(self):
        """Read data from the serial port and update the buffer."""
        data = self.ser.read(512)
        if data:
            self.buf.extend(data)
            self.last_rx = time.monotonic()

    def process_burst(self):
        """Check for a gap and process the buffered frame if one is found."""
        now = time.monotonic()
        delta = (now - self.last_rx) if self.last_rx else None
        if self.buf and self.last_rx and delta >= self.gap_sec:
            frame = bytes(self.buf)
            print(f"--- {self.name}: [{now*1000:.3f}ms ({delta*1000:.3f})ms] NEW FRAME (UART burst len={len(frame)}) ---", flush=True)
            if self.last_frame and len(frame) == len(self.last_frame):
                xor_frame = bytes(a ^ b for a, b in zip(frame, self.last_frame))
                print_frame(frame, xor_frame)
            else:
                print_frame(frame)
            self.last_frame = frame
            self.buf.clear()
            self.last_rx = None

    def close(self):
        self.ser.close()

try:
    # Initialize stream processors with per-stream gap_sec
    streams = {
        name: StreamProcessor(
            name=name,
            port=config["port"],
            baud=config["baud"],
            parity=config["parity"],
            gap_sec=config.get("gap_sec", 0.020),  # fallback to 20ms if not set
            stopbits=config.get("stopbits", serial.STOPBITS_TWO),
            bytesize=config.get("bytesize", serial.EIGHTBITS),
        )
        for name, config in STREAMS_CONFIG.items()
    }

    while True:
        for stream in streams.values():
            stream.read()
            stream.process_burst()

except KeyboardInterrupt:
    print("\nClosing ports...")
except Exception as e:
    print(f"\nAn error occurred: {e}")
finally:
    for stream in streams.values():
        stream.close()
    print("Done.")

