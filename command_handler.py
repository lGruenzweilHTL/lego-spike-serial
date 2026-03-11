import firmware_factory
import time
import serial
import threading
from typing import Callable, Optional, Dict, Tuple, Any

class SpikeConnection:
    def __init__(self, port: str, baud: int):
        self.port = port
        self.baud = baud
        self.connected = False
        self.serial: Optional[serial.Serial] = None

        # write tuning
        self.chunk_size = 128
        self.write_pause = 0.002
        self.flush_after_write = True

        # transaction state
        self._tx_counter = 0
        self._tx_lock = threading.Lock()
        self._pending: Dict[int, Tuple[Optional[Callable], Optional[threading.Event], Optional[Dict]]] = {}  # txid -> (callback, Event|None, result_container|None)

        # reader thread
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_reader = threading.Event()
        self._awaiting: Dict[int, float] = {}  # txid -> timestamp for txid-only lines
        self._awaiting_timeout = 2.0

    def connect(self, timeout: float = 0.1) -> None:
        """Open serial port and start background reader."""
        self.serial = serial.Serial(self.port, self.baud, timeout=timeout)
        if not self.serial.is_open:
            self.serial.open()
        try:
            self.serial.write_timeout = 0.5
        except Exception:
            pass
        self.connected = True
        self.start_reader()

    def start_reader(self) -> None:
        if self._reader_thread is None or not self._reader_thread.is_alive():
            self._stop_reader.clear()
            self._reader_thread = threading.Thread(target=self._reader_loop, name="SpikeReader", daemon=True)
            self._reader_thread.start()

    def stop_reader(self) -> None:
        self._stop_reader.set()
        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)
        self._reader_thread = None

    def disconnect(self) -> None:
        self.stop_reader()
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.connected = False

    def _write_chunks(self, data: bytes) -> None:
        if not data:
            return
        total = len(data)
        pos = 0
        while pos < total:
            end = min(pos + self.chunk_size, total)
            chunk = data[pos:end]
            try:
                if self.serial:
                    written = self.serial.write(chunk)
                else:
                    raise Exception("Serial not connected")
            except Exception as e:
                print(f"PC: serial.write() raised: {e}")
                raise
            if written is None:
                written = len(chunk)
            if written != len(chunk):
                print(f"PC: Warning: partial write ({written}/{len(chunk)})")
            if self.flush_after_write:
                try:
                    if self.serial:
                        self.serial.flush()
                except Exception:
                    pass
            pos += written
            if pos < total and self.write_pause:
                time.sleep(self.write_pause)

    def read_available(self, timeout: float = 0.2) -> Optional[str]:
        """Read available bytes and return decoded UTF-8 string or None."""
        end = time.time() + timeout
        out = b""
        if not self.serial:
             return None
        while time.time() < end:
            num_bytes = self.serial.in_waiting or 1
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

    def read_until(self, expected: bytes, timeout: float = 1.0) -> bytes:
        """Read until expected bytes sequence is found or timeout occurs."""
        end = time.time() + timeout
        data = b""
        if not self.serial:
            return b""
            
        while time.time() < end:
            if self.serial.in_waiting:
                chunk = self.serial.read(self.serial.in_waiting)
                data += chunk
                if expected in data:
                    return data
            time.sleep(0.01)
        return data
    
    def flash(self, config_path: str) -> None:
        """Flash a receiver program generated from config_path."""
        if not self.connected or not self.serial:
            raise Exception("Not connected to Spike device")
        
        # Pause reader thread to avoid contention
        self.stop_reader()
        
        try:
            firmware = firmware_factory.from_file(config_path)

            print("PC: Interrupting running program...")
            self._write_chunks(b'\x03') # Ctrl-C
            time.sleep(0.1)
            # Send another Ctrl-C to be sure we are in REPL
            self._write_chunks(b'\x03') 
            
            # Wait for REPL prompt
            got = self.read_until(b'>>>', timeout=2.0)
            if b'>>>' not in got:
                 print(f"PC: Warning: Did not see REPL prompt '>>>'. Got: {got}")

            print("PC: Entering paste mode...")
            self._write_chunks(b'\x05') # Ctrl-E
            got = self.read_until(b'paste mode', timeout=1.0)
            
            print("PC: Sending firmware...")
            self._write_chunks(firmware)
            time.sleep(0.05)

            print("PC: Finishing upload...")
            self._write_chunks(b'\x04') # Ctrl-D
            
            # Wait for soft reboot confirmation
            got = self.read_until(b'soft reboot', timeout=2.0)
            if b'soft reboot' not in got:
                 # It might just start running without printing soft reboot if it was already in a weird state, 
                 # or maybe the firmware output starts immediately.
                 pass
            
            print("PC: Firmware started.")

        finally:
            # clear input buffer before restarting reader
            self.serial.reset_input_buffer()
            self.start_reader()

    def _next_txid(self) -> int:
        with self._tx_lock:
            self._tx_counter += 1
            if self._tx_counter > 0x7FFFFFFF:
                self._tx_counter = 1
            return self._tx_counter

    def _reader_loop(self) -> None:
        """Reader thread: dispatch lines to pending txids; handle txid-only lines by awaiting next payload."""
        while not self._stop_reader.is_set() and self.connected and self.serial:
            try:
                line = self.serial.readline()
            except Exception:
                # Serial port might be closed or disconnected
                break
            if not line:
                continue
            try:
                text = line.decode('utf-8', errors='replace').strip()
            except Exception:
                text = ''
            if not text:
                continue

            parts = text.split(' ', 1)
            txid = None
            payload = text
            if parts:
                try:
                    txid = int(parts[0])
                    payload = parts[1] if len(parts) > 1 else ''
                except Exception:
                    # not transactioned: see if a recent txid-only line awaits this payload
                    now = time.time()
                    matched_txid = None
                    matched_ts = 0.0
                    for atxid, ts in list(self._awaiting.items()):
                        if now - ts <= self._awaiting_timeout and ts > matched_ts:
                            matched_txid = atxid
                            matched_ts = ts
                    if matched_txid is not None:
                        try:
                            entry = self._pending.pop(matched_txid, None)
                            self._awaiting.pop(matched_txid, None)
                            if entry:
                                callback, event, result_container = entry
                                if result_container is not None:
                                    result_container['result'] = text
                                if callback:
                                    try:
                                        callback(matched_txid, text)
                                    except Exception as e:
                                        print(f"PC: callback for txid {matched_txid} raised: {e}")
                                if event is not None:
                                    event.set()
                                continue
                        except Exception:
                            pass
                    print("Untransactioned message: " + text)
                    txid = None

            if txid is not None:
                entry = self._pending.get(txid, None)
                if entry:
                    callback, event, result_container = entry
                    if payload == '':
                        self._awaiting[txid] = time.time()
                        if result_container is not None:
                            result_container['result'] = payload
                        continue

                    self._awaiting.pop(txid, None)
                    self._pending.pop(txid, None)
                    if result_container is not None:
                        result_container['result'] = payload
                    if callback:
                        try:
                            callback(txid, payload)
                        except Exception as e:
                            print(f"PC: callback for txid {txid} raised: {e}")
                    if event is not None:
                        event.set()

    def send_command(self, command: str, callback: Optional[Callable[[int, str], None]] = None,
                     wait: bool = False, timeout: Optional[float] = None) -> Optional[Union[int, str]]:
        """Send '<txid> <command>\n'. If wait=True return the response string or None on timeout; otherwise return txid."""
        if not self.connected:
            raise Exception("Not connected to Spike device")

        txid = self._next_txid()
        full = f"{txid} {command}\n".encode('utf-8')

        event = threading.Event() if wait else None
        result_container: Optional[Dict[str, str]] = {'result': ''} if wait else None
        self._pending[txid] = (callback, event, result_container)

        self._write_chunks(full)

        if wait and event:
            finished = event.wait(timeout=timeout)
            self._pending.pop(txid, None)
            if not finished:
                return None
            return result_container['result'] if result_container else None

        return txid

