"""
@file record.py
@brief Python script to record audio from a serial port and save it as a WAV file.
usage:
    On Windows: 
        python record.py -p COM3 -o output.wav -b 921600
    On Linux:
        python record.py -p /dev/ttyACM0 -o output.wav -b 921600
"""

import argparse
import sys
import time
import wave

import subprocess
try:
    import serial
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "pyserial"], check=True)
    import serial

SAMPLE_RATE = 16000              # Audio sample rate (Hz)
SAMPLE_WIDTH_BYTES = 2           # Sample width in bytes (16-bit PCM)
CHANNELS = 1                     # Number of audio channels
RECORD_DURATION_S = 10            # Recording duration (seconds)

PACKET_START = bytes([0xAA, 0x55, ord('S'), ord('T'), ord('A'), ord('R'), ord('T')]) # Start packet marker
PACKET_END = bytes([0xAA, 0x55, ord('E'), ord('N'), ord('D')])                       # End packet marker
SYNC_TIMEOUT_S = 20             # Timeout for waiting start signal (seconds)

def find_start_packet(ser, timeout):
    """
    @brief Wait for the start packet from serial port within a timeout.
    @param ser Serial port object.
    @param timeout Timeout in seconds.
    @return True if start packet is found, False otherwise.
    """
    start_time = time.time()
    buffer = bytearray()
    while time.time() - start_time < timeout:
        if ser.in_waiting > 0:
            chunk = ser.read(ser.in_waiting)
            buffer.extend(chunk)
            if buffer.endswith(PACKET_START):
                return True
        else:
            time.sleep(0.01)
    return False

def main(port, baudrate, output_file):
    """
    @brief Connect to serial port, synchronize, receive audio data, and save as WAV file.
    @param port Serial port name.
    @param baudrate Serial baudrate.
    @param output_file Output WAV file name.
    """
    total_bytes_to_read = SAMPLE_RATE * SAMPLE_WIDTH_BYTES * CHANNELS * RECORD_DURATION_S

    print("--- Zephyr/Python Audio Recorder ---")
    print(f"  - Serial port: {port}, Baudrate: {baudrate}")
    print(f"  - Output: {output_file}")
    print(f"  - Expected bytes: {total_bytes_to_read}")
    print("-" * 36)

    try:
        with serial.Serial(port, baudrate, timeout=1) as ser:
            print(f"Serial port opened. Please press SW0 on device within {SYNC_TIMEOUT_S} seconds...")

            # Wait for start packet
            if not find_start_packet(ser, SYNC_TIMEOUT_S):
                print("\nError: Timeout waiting for start packet.")
                print("Check if device is running and button is pressed.")
                sys.exit(1)
            
            print("Synchronized (START packet received). Receiving audio data...")
            
            # Read fixed-length audio data
            ser.timeout = RECORD_DURATION_S + 2
            audio_data = ser.read(total_bytes_to_read)
            
            if len(audio_data) < total_bytes_to_read:
                print(f"\nError: Timeout reading audio data.")
                print(f"Expected {total_bytes_to_read} bytes, got {len(audio_data)} bytes.")
                sys.exit(1)

            print(f"Received {len(audio_data)} bytes of audio data.")
            
            # Optionally verify end packet
            ser.timeout = 2.0 
            end_buffer = ser.read(len(PACKET_END))
            if end_buffer == PACKET_END:
                print("Transfer verified (END packet received).")
            else:
                print("Warning: END packet not received. File may still be valid.")

            # Write to WAV file
            print(f"Saving to '{output_file}'...")
            with wave.open(output_file, "wb") as wav_file:
                wav_file.setnchannels(CHANNELS)
                wav_file.setsampwidth(SAMPLE_WIDTH_BYTES)
                wav_file.setframerate(SAMPLE_RATE)
                wav_file.writeframes(audio_data)
            
            print("WAV file saved.")

    except serial.SerialException as e:
        print(f"Serial error: {e}")
        print("Please check the serial port and device connection.")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record audio from serial port and save as WAV file.")
    parser.add_argument("-p", "--port", required=True, help="Serial port (e.g. COM3 or /dev/ttyACM0)")
    parser.add_argument("-o", "--output", default="output.wav", help="Output WAV file name (default: output.wav)")
    parser.add_argument("-b", "--baudrate", type=int, default=921600, help="Serial baudrate (default: 921600)")
    
    args = parser.parse_args()

    main(args.port, args.baudrate, args.output)