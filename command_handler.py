import firmware_factory
import time
import serial

class SpikeConnection:
    def __init__(self, port, baud):
        self.port = port
        self.baud = baud
        self.connected = False
        self.serial = None

    def connect(self, timeout=0.1):
        """Connect to the Spike device.
        Raises:
            SerialException: If unable to open the serial port.
        """
        self.serial = serial.Serial(self.port, self.baud, timeout=timeout)
        self.serial.open() # Serial exception will propagate if unable to open
        self.connected = True

    def disconnect(self):
        """Disconnect from the Spike device."""
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.connected = False

    def read_available(self, timeout=0.2):
        """
        Read all available data from the Spike device within the specified timeout.
        Args:
            timeout (float): Time in seconds to wait for data
        Returns:
            str or None: Decoded string data if available, otherwise None
        """
        end = time.time() + timeout
        out = b""
        while time.time() < end:
            num_bytes = self.serial.in_waiting or 1 # TODO: find out what happens when 'or 1' is removed
            chunk = self.serial.read(num_bytes)
            if not chunk:
                time.sleep(0.01)
                continue
            out += chunk
        if out:
            try:
                return out.decode("utf-8")
            except UnicodeDecodeError:
                pass
        return None
    
    def flash(self, config_path):
        """
        Flash the Spike device with a command receiver program based on the provided configuration file.
        Args:
            config_path (str): Path to the JSON configuration file defining commands
        """
        # TODO: tweak timeouts
        if not self.connected:
            raise Exception("Not connected to Spike device")
        
        firmware = firmware_factory.from_json(config_path)

        # Interrupt any running program
        self.serial.write(b'\x03')  # Ctrl-C
        time.sleep(0.2)
        print(self.read_available(0.3))

        # Enter paste mode
        self.serial.write(b'\x05')  # Ctrl-E (paste mode)
        time.sleep(0.1)

        # Paste the hub receiver program
        self.serial.write(firmware)
        time.sleep(0.05)

        # Finish paste (execute)
        self.serial.write(b'\x04')  # Ctrl-D to run pasted block
        time.sleep(0.2)
        print(self.read_available(0.6))

    def send_command(self, command):
        """
        Send a command string to the Spike device. A newline will be automatically appended to make the hub's readline() return.
        Args:
            command (str): The command string to send
        """
        if not self.connected:
            raise Exception("Not connected to Spike device")
        self.serial.write((command + "\n").encode("utf-8"))
        