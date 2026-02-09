import time
from command_handler import SpikeConnection

PORT = "/dev/ttyACM0"        # This is for linux. On Windows: COM9 ; macOS: /dev/tty.usbmodem*
BAUD = 115200

# TODO: fix command recognition for no-parameter commands (ping)
connection = SpikeConnection(PORT, BAUD)
connection.connect()
connection.flash("example/config.yaml")  # Flash the hub with commands from config

try:
    while True:
        user_line = input("> ")
        # Send the line followed by newline so the hub's readline() returns
        connection.send_command(user_line)
        time.sleep(0.2)
        print(connection.read_available())  # Read and print hub response
except KeyboardInterrupt:
    print("\nPC: Bye!")