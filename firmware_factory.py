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

    firmware = "import sys\n"
    start_lines = data.get("start_code", [])
    if isinstance(start_lines, str):
        firmware += start_lines.rstrip("\n") + "\n"
    else:
        for line in start_lines:
            firmware += line + "\n"

    # Main loop: read a line, optionally parse a leading txid, and set `payload` to the command text
    firmware += """
while True:
    try:
        line = sys.stdin.readline()
        if not line:
            continue
        line = line.strip()
        if not line:
            continue
        # extract optional transaction id at the start: '<txid> <payload>'
        parts = line.split(' ', 1)
        txid = ''
        payload = line
        try:
            possible = parts[0]
            int(possible)
            txid = possible
            payload = parts[1] if len(parts) > 1 else ''
        except Exception:
            # no numeric txid; treat entire line as payload
            txid = ''
            payload = line

        # For simple ACK/debugging we can echo the payload back; if a txid was provided,
        # prefix responses with it so the host can match them.
        # Command-specific handlers below can print their own responses; they should
        # also include the txid if they want the host to match them.
        #print("Echo: " + txid + ' ' + payload)  # optional echo
"""

    commands = data.get("commands", [])
    for command in commands:
        firmware = add_command(firmware, command)

    firmware += """
    except Exception  as e:
        # include txid if present when reporting errors
        try:
            if txid:
                print(txid + ' ' + 'HUB_ERROR: ' + str(e))
            else:
                print('HUB_ERROR: ' + str(e))
        except Exception:
            pass
"""

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

    # Use the parsed `payload` variable in generated handlers.
    # If there are no parameters, match the command by equality; otherwise match by startswith and split.
    if not params:
        firmware += f'{statement_indent}if payload.lower() == "{name}":\n'
        # no cmd_parts parsing for no-arg commands
    else:
        firmware += f'{statement_indent}if payload.lower().startswith("{name} "):\n'
        firmware += f'{code_indent}cmd_parts = payload.split()\n'

    # initialize result so user code can set `result = ...` to return a value
    firmware += f'{code_indent}result = None\n'

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
        # Generated code should operate on `payload` (or derived params) and may set `result`.
        firmware += f'{code_indent}{line}\n'

    # If the user code set `result` (not None), print it back prefixed by txid when available
    firmware += f"{code_indent}if result is not None:\n"
    firmware += f"{code_indent}    try:\n"
    firmware += f"{code_indent}        if txid:\n"
    firmware += f"{code_indent}            print(txid + ' ' + str(result))\n"
    firmware += f"{code_indent}        else:\n"
    firmware += f"{code_indent}            print(str(result))\n"
    firmware += f"{code_indent}    except Exception:\n"
    firmware += f"{code_indent}        pass\n"

    return firmware
