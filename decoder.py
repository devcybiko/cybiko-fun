import re
import sys

# --- Configuration ---
BAUD_RATE = 38400
BIT_TIME = 1000000 / BAUD_RATE  # Bit time in microseconds
TOLERANCE = 0.4  # Allowable timing variance (40%)

# Bit time boundaries
MIN_BIT_TIME = BIT_TIME * (1 - TOLERANCE)
MAX_BIT_TIME = BIT_TIME * (1 + TOLERANCE)

def parse_transitions(file_path):
    """Parses the logic analyzer data file into a list of (level, duration) tuples."""
    transitions = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                match = re.search(r"Level: (\d+), Duration: (\d+)", line)
                if match:
                    level = int(match.group(1))
                    duration = int(match.group(2))
                    transitions.append((level, duration))
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        sys.exit(1)
    return transitions

def decode_stream(transitions):
    """Decodes the stream of transitions into bytes, correcting for timing drift."""
    bytes_found = []
    
    # Create a flat timeline of levels, correcting for drift
    timeline = []
    remainder = 0.0
    for level, duration in transitions:
        # Add the remainder from the previous transition
        total_duration = duration + remainder
        
        # Calculate how many bits this duration represents
        num_bits = total_duration / BIT_TIME
        
        # The number of bits to generate is the rounded integer part
        num_bits_to_generate = int(round(num_bits))

        if num_bits_to_generate > 0:
            for _ in range(num_bits_to_generate):
                timeline.append(level)
        
        # The new remainder is the leftover time, carried to the next transition
        remainder = total_duration - (num_bits_to_generate * BIT_TIME)

    i = 0
    # Find the first potential start bit (idle 1 -> active 0)
    while i < len(timeline) - 1:
        if timeline[i] == 1 and timeline[i+1] == 0:
            break
        i += 1
    
    while i < len(timeline):
        # We are at the '1' before a potential start bit
        start_bit_index = i + 1
        
        # Ensure we have enough data for a full frame (1 start + 8 data + 1 parity + 1 stop = 11 bits)
        if start_bit_index + 10 >= len(timeline):
            break

        # Extract the potential frame
        frame = timeline[start_bit_index : start_bit_index + 11]

        # Verify frame structure: must start with 0 and end with 1
        start_bit = frame[0]
        stop_bit = frame[10]

        if start_bit == 0 and stop_bit == 1:
            data_bits = frame[1:9]
            
            # Reconstruct the byte (LSB first)
            byte_val = 0
            for bit_index, bit in enumerate(data_bits):
                if bit == 1:
                    byte_val |= (1 << bit_index)
            
            bytes_found.append(byte_val)
            
            # Jump ahead to the end of the current frame and look for the next one
            i = start_bit_index + 10
        else:
            # Not a valid frame, move to the next bit to search for a new start sequence
            i += 1
            
    return bytes_found


def find_packets(byte_list, headers):
    """Finds and returns a list of packets based on known headers."""
    packets = []
    i = 0
    while i < len(byte_list):
        found_header = False
        for header in headers:
            header_len = len(header)
            if i + header_len <= len(byte_list) and tuple(byte_list[i:i+header_len]) == header:
                # Found a header, now determine packet length.
                # This is a placeholder: assuming a fixed length or a length byte.
                # Let's look for the next header to determine length.
                next_header_index = -1
                for j in range(i + header_len, len(byte_list)):
                    for h in headers:
                        hl = len(h)
                        if j + hl <= len(byte_list) and tuple(byte_list[j:j+hl]) == h:
                            next_header_index = j
                            break
                    if next_header_index != -1:
                        break
                
                if next_header_index != -1:
                    packets.append(byte_list[i:next_header_index])
                    i = next_header_index
                else:
                    # Last packet in the stream
                    packets.append(byte_list[i:])
                    i = len(byte_list)
                found_header = True
                break
        if not found_header:
            i += 1
    return packets

def print_packets(packets):
    """Prints a list of packets, each on a new line."""
    if not packets:
        print("No packets found.")
        return
    
    print("--- Decoded Packets ---")
    for i, packet in enumerate(packets):
        hex_str = ' '.join(f'{b:02x}' for b in packet)
        ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in packet)
        print(f"Pkt {i+1}: {hex_str}")
        print(f"      {ascii_str}\n")
    print("-----------------------")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        file_path = 'data.txt'

    print(f"Decoding {file_path} at {BAUD_RATE} baud...")
    
    transitions = parse_transitions(file_path)
    if not transitions:
        print("No transitions found in file.")
    else:
        decoded_bytes = decode_stream(transitions)
        
        # Known headers
        headers = [
            (0x4d, 0xc0),
            (0x4d, 0xe0),
        ]
        
        packets = find_packets(decoded_bytes, headers)
        
        if packets:
            print_packets(packets)
        else:
            # Fallback to printing raw bytes if no packets were found
            print("Could not identify packets by header. Printing raw stream.")
            hex_str = ' '.join(f'{b:02x}' for b in decoded_bytes)
            ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in decoded_bytes)
            print(f"Hex:   {hex_str}")
            print(f"ASCII: {ascii_str}")
