import json
def from_json(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)

    firmware = ""
    start_lines = data.get("start_code", [])
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
        add_command(firmware, command)

    return firmware.encode("utf-8")


def add_command(firmware, command):
    statement_indent = " " * 8
    code_indent = " " * 12

    name = command.get("name", "").lower()
    params = command.get("parameters", [])
    code_lines = command.get("code", [])

    firmware += f'{statement_indent}if line.lower() == "{name}":\n'

    # Parameter parsing
    firmware += f'{code_indent}cmd_parts = line.split()\n'
    for param in params:
        param_name = param.get("name", "")
        param_type = param.get("type", "str")
        if param_type == "int":
            firmware += f'{code_indent}{param_name} = int(cmd_parts[{params.index(param_name) + 1}])\n'
        elif param_type == "float":
            firmware += f'{code_indent}{param_name} = float(cmd_parts[{params.index(param_name) + 1}])\n'
        elif param_type == "bool":
            firmware += f'{code_indent}{param_name} = cmd_parts[{params.index(param_name) + 1}].lower() == "true"\n'
        else:
            firmware += f'{code_indent}{param_name} = cmd_parts[{params.index(param_name) + 1}]\n'

    # Command code
    for line in code_lines:
        firmware += f'{code_indent}{line}\n'
