from typing import Optional
import serial
import time

class HardUart:
    SER_TIMEOUT = 0.001 # 0.001 # Non-blocking read

    def __init__(self, port, baud, gap_sec):
        self.name = "TX_AVR"
        self.port = port
        self.baud = baud
        self.gap_sec = gap_sec
        self.bytesize = serial.EIGHTBITS  # Add data bits config
        self.parity = serial.PARITY_MARK
        self.stopbits = serial.STOPBITS_ONE
        self.ser = serial.Serial(self.port, self.baud, timeout=self.SER_TIMEOUT,
                                 bytesize=self.bytesize, parity=self.parity,
                                 stopbits=self.stopbits)
        self.buf = bytearray()
        self.last_rx = None
        self.last_frame = None
        print(f"Listening to {self.name} on {self.port} at {self.baud} baud (gap_sec={self.gap_sec}, {self.bytesize}{self.parity}{self.stopbits})...", flush=True)

    def read_bytes(self):
        """Read data from the serial port and update the buffer."""
        # print(f"Reading from {self.port}...", flush=True)
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
                self.print_frame(frame, xor_frame)
            else:
                self.print_frame(frame)
            self.last_frame = frame
            self.buf.clear()
            self.last_rx = None

    def close(self):
        self.ser.close()

    def print_frame(self, frame: bytes, xor_data: Optional[bytes] = None):
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
