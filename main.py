import firmware_factory
from command_handler import SpikeConnection

PORT = "/dev/ttyACM0"        # This is for linux. On Windows: COM9 ; macOS: /dev/tty.usbmodem*
BAUD = 115200

fw = firmware_factory.from_file("example/config.yaml")
print(fw.decode())
#while True: pass

connection = SpikeConnection(PORT, BAUD)
connection.connect()
connection.flash("example/config.yaml")  # Flash the hub with commands from config

try:
    while True:
        user_line = input("> ")
        if not user_line:
            continue
        # Send the command with a transaction id and wait for a matching response.
        # send_command will return the payload string (without txid) or None on timeout.
        result = connection.send_command(user_line, wait=True, timeout=3.0)
        if result is None:
            print("PC: no response (timeout)")
        elif result is str:
            print(result)
except KeyboardInterrupt:
    print("\nPC: Bye!")
finally:
    connection.disconnect()
