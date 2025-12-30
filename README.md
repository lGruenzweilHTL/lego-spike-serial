# Lego Spike Serial commands

This repository contains a command interpreter for controlling Lego Spike Prime and Lego Spike Essential hubs via serial communication.

## Features

- Connect to Lego Spike hubs via USB serial.
- Send commands to control motors, lights, and sensors.
- Receive data from sensors.
- Define custom commands using a simple command syntax with a JSON or YAML configuration file.

### Planned Features

- Log levels for debugging and information.
- Better configuration options.
- Optional parameters for commands.

## Config file (JSON)

Commands and other configuration is defined in a JSON file. The following is an example of the JSON structure:
```json
{
  "start_code": [
    "# Start code here",
    "# Use this for imports and helper functions",
    "print('Hub ready')"
  ],
  "commands": [
    {
      "name": "command_name",
      "parameters": [
        {
          "name": "parameter_name",
          "type": "int|float|str|bool"
        }
      ],
      "code": [
        "# MicroPython code to be executed when the command is invoked",
        "print(parameter_name)"
      ]
    }
  ]
}
```

## Config file (YAML)

The same configuration can be defined in a YAML file. The following is an example of the YAML structure:
```yaml
start_code: |
  import sys, hub, motor
  from hub import port
  print('HUB: READY')

commands:
  - name: command_name
    parameters:
      - name: parameter_name
        type: int|float|str|bool
    code: |
      # MicroPython code to be executed when the command is invoked
      print(parameter_name)
```

> [!TIP]
> We recommend using YAML for better readability, especially for larger configurations.
> This also makes it easier to include multi-line code blocks by using literal style (`|`).


### Start Code

The `start_code` field contains a list of microPython code lines that will be executed once when the hub starts up. This is useful for importing necessary modules or defining helper functions that will be used by the commands.

### Parameters

Parameters are defined using the 'parameters' list within each command.
Each parameter has the following fields:
- `name`: The name of the parameter.
- `type`: The data type of the parameter. Supported types are `int`, `float`, `str`, and `bool`.

Parameters will be passed to the command code as variables with the same name as defined in the `name` field and will be of the specified `type`.
When sending a command over serial, parameters should be provided in the order they are defined in the `parameters` list.

### Command Code

The `code` field contains the microPython code that will be executed on the Lego Spike hub when the command is invoked. The code can use the parameters defined in the `parameters` list.

Use the `print()` function to send output back to the host computer over serial.

> [!IMPORTANT]
> Do not return values from the command code. Instead, use `print()` to send data back to the host.

## Acknowledgments

The basic serial code is based on the work of [ammardaher](https://github.com/ammardaher/LEGO-Spike-USB-Serial-Console).
