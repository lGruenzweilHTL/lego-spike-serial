import argparse
import sys
import firmware_factory
from command_handler import SpikeConnection

def parse_args():
    parser = argparse.ArgumentParser(description="Lego Spike Serial Command Interface")
    parser.add_argument("config", help="Path to the configuration file (YAML/JSON)")
    parser.add_argument("-p", "--port", default="/dev/ttyACM0", help="Serial port (default: /dev/ttyACM0)")
    parser.add_argument("-b", "--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()

    print(f"Loading configuration from {args.config}...")
    try:
        fw = firmware_factory.from_file(args.config)
        # print(fw.decode()) # Optionally print generated firmware for debug
    except Exception as e:
        print(f"Error loading configuration: {e}")
        sys.exit(1)

    print(f"Connecting to {args.port} at {args.baud} baud...")
    connection = SpikeConnection(args.port, args.baud)
    try:
        connection.connect()
    except Exception as e:
        print(f"Failed to connect: {e}")
        sys.exit(1)

    print("Flashing firmware...")
    try:
        connection.flash(args.config)
    except Exception as e:
        print(f"Error flashing firmware: {e}")
        connection.disconnect()
        sys.exit(1)
    
    print("Ready. Type commands below.")
    
    try:
        while True:
            try:
                user_line = input("> ")
            except EOFError:
                break
                
            if not user_line:
                continue
            
            # Send the command with a transaction id and wait for a matching response.
            # send_command will return the payload string (without txid) or None on timeout.
            result = connection.send_command(user_line, wait=True, timeout=3.0)
            if result is None:
                print("PC: no response (timeout)")
            elif isinstance(result, str):
                r = result.strip()
                # ignore explicit awaitable markers returned by the device
                if not r.lower().startswith("<awaitable"):
                    print(result)
    except KeyboardInterrupt:
        print("\nPC: Bye!")
    finally:
        connection.disconnect()

