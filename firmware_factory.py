import os
import json
import yaml
from typing import Dict, Any, List, Union

def load_config(file_path: str) -> Dict[str, Any]:
    ext = os.path.splitext(file_path)[1].lower()
    with open(file_path, "r", encoding="utf-8") as f:
        if ext in (".yaml", ".yml"):
            return yaml.safe_load(f)
        return json.load(f)

def from_file(file_path: str) -> bytes:
    data = load_config(file_path)
    lines: List[str] = ["import sys"]

    start_lines = data.get("start_code", [])
    if isinstance(start_lines, str):
        lines.append(start_lines.rstrip("\n"))
    else:
        lines.extend(start_lines)

    # Main loop: read a line, optionally parse a leading txid, and set `payload` to the command text
    lines.append("""
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
""")

    commands = data.get("commands", [])
    for command in commands:
        add_command(lines, command)

    lines.append("""
    except Exception as e:
        # include txid if present when reporting errors
        try:
            if txid:
                print(txid + ' ' + 'HUB_ERROR: ' + str(e))
            else:
                print('HUB_ERROR: ' + str(e))
        except Exception:
            pass
""")

    return "\n".join(lines).encode("utf-8")

def add_command(lines: List[str], command: Dict[str, Any]) -> None:
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
        lines.append(f'{statement_indent}if payload.lower() == "{name}":')
        # no cmd_parts parsing for no-arg commands
    else:
        lines.append(f'{statement_indent}if payload.lower().startswith("{name} "):')
        lines.append(f'{code_indent}cmd_parts = payload.split()')

    # initialize result so user code can set `result = ...` to return a value
    lines.append(f'{code_indent}result = None')

    for idx, param in enumerate(params):
        param_name = param.get("name", "")
        param_type = param.get("type", "str")
        part_index = idx + 1
        
        if param_type == "int":
            lines.append(f'{code_indent}{param_name} = int(cmd_parts[{part_index}])')
        elif param_type == "float":
            lines.append(f'{code_indent}{param_name} = float(cmd_parts[{part_index}])')
        elif param_type == "bool":
            lines.append(f'{code_indent}{param_name} = cmd_parts[{part_index}].lower() == "true"')
        else:
            lines.append(f'{code_indent}{param_name} = cmd_parts[{part_index}]')

    for line in code_lines:
        # Generated code should operate on `payload` (or derived params) and may set `result`.
        lines.append(f'{code_indent}{line}')

    # If the user code set `result` (not None), print it back prefixed by txid when available
    lines.append(f"{code_indent}if result is not None:")
    lines.append(f"{code_indent}    try:")
    lines.append(f"{code_indent}        if txid:")
    lines.append(f"{code_indent}            print(txid + ' ' + str(result))")
    lines.append(f"{code_indent}        else:")
    lines.append(f"{code_indent}            print(str(result))")
    lines.append(f"{code_indent}    except Exception:")
    lines.append(f"{code_indent}        pass")

