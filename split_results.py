import re
import os


def split_results_file(filename, out_prefix="packet_"):
    with open(filename, 'r') as f:
        lines = f.readlines()

    packets = []
    packet = []
    mode = None
    start_idx = 26

    for line in lines:
        if line.startswith("Silence duration"):
            if mode != "silence":
                if packet:
                    packets.append(''.join(packet))
                packet = []
                mode = "silence"
            packet.append(line)
        elif line.startswith("--- TX_AVR"):
            if packet:
                packets.append(''.join(packet))
            packet = []
            mode = "tx_avr"
            packet.append(line)
        elif mode == "silence":
            packet.append(line)
            if line.startswith("--- Transaction Complete ---"):
                packets.append(''.join(packet))
                packet = []
                mode = None
        elif mode == "tx_avr":
            packet.append(line)
            if line.startswith("Checksum"):
                packets.append(''.join(packet))
                packet = []
                mode = None
        else:
            continue

    # Catch any trailing packet
    if packet:
        packets.append(''.join(packet))

    seq = start_idx
    for packet in packets:
        # Determine type by first line
        first_line = packet.lstrip().splitlines()[0] if packet.lstrip() else ""
        if first_line.startswith("--- TX_AVR"):
            suffix = "tx"
        else:
            suffix = "rx"
        out_name = f"packet_{seq}_{suffix}.txt"
        with open(out_name, "w") as out:
            out.write(packet.lstrip())
        print(f"Wrote {out_name} ({len(packet)} bytes)")
        seq += 1

if __name__ == "__main__":
    split_results_file("results.txt")
