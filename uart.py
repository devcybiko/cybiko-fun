import time
import serial
from typing import Dict, Any, Optional
import pigpio

# Configuration for both serial ports, now with per-stream gap_sec
STREAMS_CONFIG: Dict[str, Dict[str, Any]] = {
    "TX_AVR": {
        "port": "/dev/ttyAMA5",
        "baud": 38400,
        "gap_sec": 0.005, 
        "bytesize": serial.EIGHTBITS,  # Add data bits config
        "parity": serial.PARITY_NONE,
        "stopbits": serial.STOPBITS_TWO,
    },
}

