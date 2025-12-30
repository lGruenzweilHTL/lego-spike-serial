import os
import json
import yaml

def load_config(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    with open(file_path, "r", encoding="utf-8") as f:
        if ext in (".yaml", ".yml"):
            return yaml.safe_load(f)
        return json.load(f)

def from_file(file_path):
    data = load_config(file_path)

    firmware = ""
    start_lines = data.get("start_code", [])
    if isinstance(start_lines, str):
        firmware += start_lines.rstrip("\n") + "\n"
    else:
        for line in start_lines:
            firmware += line + "\n"

    firmware += """
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                continue
            line = line.strip()
            if not line:
                continue
            hub.sound.beep(880, 120)
            print("HUB: ACK ->", line)
    """

    commands = data.get("commands", [])
    for command in commands:
        firmware = add_command(firmware, command)

    return firmware.encode("utf-8")

def add_command(firmware, command):
    statement_indent = " " * 8
    code_indent = " " * 12

    name = command.get("name", "").lower()
    params = command.get("parameters", [])
    raw_code = command.get("code", [])
    if isinstance(raw_code, str):
        code_lines = raw_code.splitlines()
    else:
        code_lines = raw_code

    firmware += f'{statement_indent}if line.lower() == "{name}":\n'
    firmware += f'{code_indent}cmd_parts = line.split()\n'

    for idx, param in enumerate(params):
        param_name = param.get("name", "")
        param_type = param.get("type", "str")
        part_index = idx + 1
        if param_type == "int":
            firmware += f'{code_indent}{param_name} = int(cmd_parts[{part_index}])\n'
        elif param_type == "float":
            firmware += f'{code_indent}{param_name} = float(cmd_parts[{part_index}])\n'
        elif param_type == "bool":
            firmware += f'{code_indent}{param_name} = cmd_parts[{part_index}].lower() == "true"\n'
        else:
            firmware += f'{code_indent}{param_name} = cmd_parts[{part_index}]\n'

    for line in code_lines:
        firmware += f'{code_indent}{line}\n'

    return firmware
