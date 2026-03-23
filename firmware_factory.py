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

    # Add command functions
    commands = data.get("commands", [])
    for command in commands:
        add_command(lines, command)

    # Now the main loop
    loop_lines = [
        "while True:",
        "    try:",
        "        line = sys.stdin.readline()",
        "        if not line:",
        "            continue",
        "        line = line.strip()",
        "        if not line:",
        "            continue",
        "        # extract optional transaction id at the start: '<txid> <payload>'",
        "        parts = line.split(' ', 1)",
        "        txid = ''",
        "        payload = line",
        "        try:",
        "            possible = parts[0]",
        "            int(possible)",
        "            txid = possible",
        "            payload = parts[1] if len(parts) > 1 else ''",
        "        except Exception:",
        "            # no numeric txid; treat entire line as payload",
        "            txid = ''",
        "            payload = line",
        "        result = None",
    ]

    # Add the ifs for each command
    for command in commands:
        name = command.get("name", "").lower()
        params = command.get("parameters", [])
        if not params:
            loop_lines.append(f'        if payload.lower() == "{name}":')
            loop_lines.append(f"            result = {name}(payload)")
        else:
            loop_lines.append(f'        if payload.lower().startswith("{name} "):')
            loop_lines.append(f"            result = {name}(payload)")

    # Add the result printing
    loop_lines.extend(
        [
            "        if result is not None:",
            "            try:",
            "                if txid:",
            "                    print(txid + ' ' + str(result))",
            "                else:",
            "                    print(str(result))",
            "            except Exception:",
            "                pass",
            "    except Exception as e:",
            "        # include txid if present when reporting errors",
            "        try:",
            "            if txid:",
            "                print(txid + ' ' + 'HUB_ERROR: ' + str(e))",
            "            else:",
            "                print('HUB_ERROR: ' + str(e))",
            "        except Exception:",
            "            pass",
        ]
    )

    lines.extend(loop_lines)

    return "\n".join(lines).encode("utf-8")


def add_command(lines: List[str], command: Dict[str, Any]) -> None:
    indent = "    "

    name = command.get("name", "").lower()
    params = command.get("parameters", [])
    raw_code = command.get("code", [])

    if isinstance(raw_code, str):
        code_lines = raw_code.splitlines()
    else:
        code_lines = raw_code

    lines.append(f"def {name}(payload):")

    if params:
        lines.append(f"{indent}cmd_parts = payload.split()")

    for idx, param in enumerate(params):
        param_name = param.get("name", "")
        param_type = param.get("type", "str")
        part_index = idx + 1

        if param_type == "int":
            lines.append(f"{indent}{param_name} = int(cmd_parts[{part_index}])")
        elif param_type == "float":
            lines.append(f"{indent}{param_name} = float(cmd_parts[{part_index}])")
        elif param_type == "bool":
            lines.append(
                f"{indent}{param_name} = cmd_parts[{part_index}].lower() == 'true'"
            )
        else:
            lines.append(f"{indent}{param_name} = cmd_parts[{part_index}]")

    for line in code_lines:
        lines.append(f"{indent}{line}")
