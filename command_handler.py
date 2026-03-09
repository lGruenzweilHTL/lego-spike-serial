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

        # write tuning
        self.chunk_size = 128
        self.write_pause = 0.002
        self.flush_after_write = True

        # transaction state
        self._tx_counter = 0
        self._tx_lock = threading.Lock()
        self._pending = {}  # txid -> (callback, Event|None, result_container|None)

        # reader thread
        self._reader_thread = None
        self._stop_reader = threading.Event()
        self._awaiting = {}  # txid -> timestamp for txid-only lines
        self._awaiting_timeout = 2.0

    def connect(self, timeout=0.1):
        """Open serial port and start background reader."""
        self.serial = serial.Serial(self.port, self.baud, timeout=timeout)
        if not self.serial.is_open:
            self.serial.open()
        try:
            self.serial.write_timeout = 0.5
        except Exception:
            pass
        self.connected = True

        if self._reader_thread is None or not self._reader_thread.is_alive():
            self._stop_reader.clear()
            self._reader_thread = threading.Thread(target=self._reader_loop, name="SpikeReader", daemon=True)
            self._reader_thread.start()

    def disconnect(self):
        self._stop_reader.set()
        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.connected = False

    def _write_chunks(self, data: bytes):
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
            if pos < total and self.write_pause:
                time.sleep(self.write_pause)

    def read_available(self, timeout=0.2):
        """Read available bytes and return decoded UTF-8 string or None."""
        end = time.time() + timeout
        out = b""
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
    
    def flash(self, config_path):
        """Flash a receiver program generated from config_path."""
        if not self.connected:
            raise Exception("Not connected to Spike device")
        firmware = firmware_factory.from_file(config_path)

        # interrupt, enter paste, send, finish
        self._write_chunks(b'\x03')
        time.sleep(0.2)
        print(self.read_available(0.3))

        self._write_chunks(b'\x05')
        time.sleep(0.1)

        self._write_chunks(firmware)
        time.sleep(0.05)

        self._write_chunks(b'\x04')
        time.sleep(0.2)
        print(self.read_available(0.6))

    def _next_txid(self) -> int:
        with self._tx_lock:
            self._tx_counter += 1
            if self._tx_counter > 0x7FFFFFFF:
                self._tx_counter = 1
            return self._tx_counter

    def _reader_loop(self):
        """Reader thread: dispatch lines to pending txids; handle txid-only lines by awaiting next payload."""
        while not self._stop_reader.is_set() and self.connected:
            try:
                line = self.serial.readline()
            except Exception:
                print("PC: serial.readline() raised; check if the serial port is open")
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
                    matched_ts = 0
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
                     wait: bool = False, timeout: Optional[float] = None) -> Optional[int]:
        """Send '<txid> <command>\n'. If wait=True return the response string or None on timeout; otherwise return txid."""
        if not self.connected:
            raise Exception("Not connected to Spike device")

        txid = self._next_txid()
        full = f"{txid} {command}\n".encode('utf-8')

        event = threading.Event() if wait else None
        result_container = {} if wait else None
        self._pending[txid] = (callback, event, result_container)

        self._write_chunks(full)

        if wait:
            finished = event.wait(timeout=timeout)
            self._pending.pop(txid, None)
            if not finished:
                return None
            return result_container.get('result')

        return txid
