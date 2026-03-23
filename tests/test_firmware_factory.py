import unittest
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import firmware_factory


class TestFirmwareFactory(unittest.TestCase):
    def test_add_command_no_params(self):
        command = {"name": "ping", "parameters": [], "code": ["return 'pong'"]}
        lines = []
        firmware_factory.add_command(lines, command)

        content = "\n".join(lines)
        self.assertIn("def ping(payload):", content)
        self.assertIn("return 'pong'", content)

    def test_add_command_with_params(self):
        command = {
            "name": "move",
            "parameters": [
                {"name": "speed", "type": "int"},
                {"name": "direction", "type": "str"},
            ],
            "code": ["return f'Moving at {speed} in {direction}'"],
        }
        lines = []
        firmware_factory.add_command(lines, command)

        content = "\n".join(lines)
        self.assertIn("def move(payload):", content)
        self.assertIn("cmd_parts = payload.split()", content)
        self.assertIn("speed = int(cmd_parts[1])", content)
        self.assertIn("direction = cmd_parts[2]", content)

    def test_from_file_integration(self):
        # Create a dummy config file
        import tempfile
        import json

        config = {
            "start_code": ["print('Start')"],
            "commands": [{"name": "test", "parameters": [], "code": ["return 42"]}],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(config, tmp)
            tmp_path = tmp.name

        try:
            fw_bytes = firmware_factory.from_file(tmp_path)
            fw_str = fw_bytes.decode("utf-8")

            self.assertIn("print('Start')", fw_str)
            self.assertIn("def test(payload):", fw_str)
            self.assertIn("return 42", fw_str)
            self.assertIn("if txid:", fw_str)  # Check for response handling

        finally:
            os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
