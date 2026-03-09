import firmware_factory
import time
import serial
import threading
from typing import Callable, Optional

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

        # Transaction id and pending callbacks map
        # _tx_counter increments for every sent command; tx ids are integers starting at 1
        self._tx_counter = 0
        self._tx_lock = threading.Lock()
        # pending: txid -> (callback, optional threading.Event, result_container)
        self._pending = {}

        # Reader thread to process incoming messages and dispatch by txid
        self._reader_thread = None
        self._stop_reader = threading.Event()

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

        # start reader thread
        if self._reader_thread is None or not self._reader_thread.is_alive():
            self._stop_reader.clear()
            self._reader_thread = threading.Thread(target=self._reader_loop, name="SpikeReader", daemon=True)
            self._reader_thread.start()

    def disconnect(self):
        """Disconnect from the Spike device."""
        # stop reader thread first
        self._stop_reader.set()
        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)
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

    def _next_txid(self) -> int:
        """Generate the next transaction id in a thread-safe way."""
        with self._tx_lock:
            self._tx_counter += 1
            # wrap-around guard (very large number unlikely to be hit)
            if self._tx_counter > 0x7FFFFFFF:
                self._tx_counter = 1
            return self._tx_counter

    def _reader_loop(self):
        """Background thread that reads incoming lines and dispatches callbacks based on txid prefix."""
        # Use readline to get full lines; rely on serial.timeout to avoid blocking forever
        while not self._stop_reader.is_set() and self.connected:
            try:
                line = self.serial.readline()
                print("Line: " + line)
            except Exception:
                # if serial port is closed or error occurs, stop loop
                break
            if not line:
                # timeout, no data
                continue
            try:
                text = line.decode('utf-8', errors='replace').strip()
            except Exception:
                text = ''
            if not text:
                continue
            # Parse txid at start: expect '<txid> <payload>' where txid is integer
            parts = text.split(' ', 1)
            txid = None
            payload = text
            if parts:
                try:
                    possible = parts[0]
                    txid = int(possible)
                    payload = parts[1] if len(parts) > 1 else ''
                except Exception:
                    # not a transactioned message; ignore or could be logged
                    print("Untransactioned message: " + text)
                    txid = None
            if txid is not None:
                entry = None
                entry = self._pending.pop(txid, None)
                if entry:
                    callback, event, result_container = entry
                    # store result for waiter
                    if result_container is not None:
                        result_container['result'] = payload
                    # call callback if provided
                    if callback:
                        try:
                            callback(txid, payload)
                        except Exception as e:
                            # protect reader thread from exceptions
                            print(f"PC: callback for txid {txid} raised: {e}")
                    # notify waiter if present
                    if event is not None:
                        event.set()
                else:
                    # no pending entry: message arrived unsolicited; ignore or log
                    # print(f"PC: Unhandled txid {txid} payload: {payload}")
                    pass
            else:
                # no txid found: ignore or handle as generic message
                # print(f"PC: Received untagged message: {text}")
                pass

    def send_command(self, command: str, callback: Optional[Callable[[int, str], None]] = None,
                     wait: bool = False, timeout: Optional[float] = None) -> Optional[int]:
        """
        Send a command string to the Spike device. A newline will be automatically appended to make the hub's readline() return.
        Each sent command (except flashing) is prefixed with a transaction id so responses can be matched.

        Args:
            command (str): The command string to send (payload only, txid will be prepended)
            callback (callable(txid:int, payload:str), optional): called when a response for this txid arrives
            wait (bool): if True, block until a response arrives or timeout occurs; returns the payload (str) or None on timeout
            timeout (float, optional): seconds to wait when wait=True

        Returns:
            int or None: the transaction id assigned to this command. If wait=True and a response arrives, the response string is returned instead.
        """
        if not self.connected:
            raise Exception("Not connected to Spike device")

        txid = self._next_txid()
        # form message as: '<txid> <command>\n'
        full = f"{txid} {command}\n".encode('utf-8')

        # prepare waiting structures if needed
        event = None
        result_container = None
        if wait or callback is not None:
            event = threading.Event() if wait else None
            result_container = {} if wait else None
            # store the callback/event/result so reader can dispatch
            # callback may be None; that's ok for wait-only usage
            self._pending[txid] = (callback, event, result_container)

        # send the command using chunked writes
        self._write_chunks(full)

        if wait:
            # wait for event set by reader thread
            finished = event.wait(timeout=timeout)
            # cleanup if still present
            self._pending.pop(txid, None)
            if not finished:
                return None
            return result_container.get('result')

        # return txid for caller to track if they want
        return txid
