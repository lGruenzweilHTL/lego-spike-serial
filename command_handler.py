import firmware_factory
import time
import serial

class SpikeConnection:
    def __init__(self, port, baud):
        self.port = port
        self.baud = baud
        self.connected = False
        self.serial = None
        # Tuning parameters to avoid partial writes when sending many commands
        # chunk_size: split large writes into chunks to avoid hitting USB buffer limits
        # write_pause: short sleep between chunks to give the device time to process
        # flush_after_write: call flush() after each chunk when supported by pyserial
        self.chunk_size = 128
        self.write_pause = 0.002
        self.flush_after_write = True

    def connect(self, timeout=0.1):
        """Connect to the Spike device.
        Raises:
            SerialException: If unable to open the serial port.
        """
        self.serial = serial.Serial(self.port, self.baud, timeout=timeout)
        if not self.serial.is_open:
            self.serial.open() # Serial exception will propagate if unable to open
        # set a sane write timeout so write(...) will fail quickly on errors
        try:
            self.serial.write_timeout = 0.5
        except Exception:
            # some serial backends may not support write_timeout; ignore
            pass
        self.connected = True

    def disconnect(self):
        """Disconnect from the Spike device."""
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.connected = False

    def _write_chunks(self, data: bytes):
        """
        Write bytes to the serial port in small chunks with optional flush and short pauses.
        This reduces the chance of partial/trimmed writes when many commands are sent quickly.
        """
        if not data:
            return
        total = len(data)
        pos = 0
        while pos < total:
            end = min(pos + self.chunk_size, total)
            chunk = data[pos:end]
            try:
                written = self.serial.write(chunk)
            except Exception as e:
                print(f"PC: serial.write() raised: {e}")
                raise
            # Some serial implementations return None; treat that as full write
            if written is None:
                written = len(chunk)
            if written != len(chunk):
                print(f"PC: Warning: partial write ({written}/{len(chunk)})")
            if self.flush_after_write:
                try:
                    self.serial.flush()
                except Exception:
                    pass
            pos += written
            # small pause to avoid overrunning the device when sending many commands
            if pos < total and self.write_pause:
                time.sleep(self.write_pause)

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
            config_path (str): Path to the JSON or YAML configuration file defining commands
        """
        # TODO: tweak timeouts
        if not self.connected:
            raise Exception("Not connected to Spike device")
        
        firmware = firmware_factory.from_file(config_path)

        # Interrupt any running program
        self._write_chunks(b'\x03')  # Ctrl-C
        time.sleep(0.2)
        print(self.read_available(0.3))

        # Enter paste mode
        self._write_chunks(b'\x05')  # Ctrl-E (paste mode)
        time.sleep(0.1)

        # Paste the hub receiver program
        # send the generated firmware in chunks to avoid partial paste when large
        self._write_chunks(firmware)
        time.sleep(0.05)

        # Finish paste (execute)
        self._write_chunks(b'\x04')  # Ctrl-D to run pasted block
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
        data = (command + "\n").encode("utf-8")
        # Use chunked writes to reduce the chance of incomplete data when many commands are sent
        self._write_chunks(data)
