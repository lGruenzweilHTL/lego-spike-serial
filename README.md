# Lego Spike Serial commands

This repository contains a command interpreter for controlling Lego Spike Prime and Lego Spike Essential hubs via serial communication.

## Features

- Connect to Lego Spike hubs via USB serial.
- Send commands to control motors, lights, and sensors.
- Receive data from sensors.
- Custom commands using a simple command syntax with a json configuration file.

## Command definitions

Commands are defined in a JSON file named `commands.json`. The structure of the JSON file is as follows:
```json
{
  "start_code": [
    "import hub",
    "import time",
    "print('Hub ready')"
  ],
  "commands": [
    {
      "name": "command_name",
      "parameters": [
        {
          "name": "parameter_name",
          "type": "int|float|str|bool",
          "required": true,
          "default": "default_value (if applicable)"
        }
      ],
      "code": "microPython code to run on the hub"
    }
  ]
}
```

### Start Code

The `start_code` field contains a list of microPython code lines that will be executed once when the hub starts up. This is useful for importing necessary modules or defining helper functions that will be used by the commands.

### Parameters

Parameters are defined using the 'parameters' list within each command.
Each parameter has the following fields:
- `name`: The name of the parameter.
- `type`: The data type of the parameter. Supported types are `int`, `float`, `str`, and `bool`.
- `default`: (Optional) The default value for the parameter if it is not provided when invoking the command.
- `required`: A boolean indicating whether the parameter is required.

Parameters will be passed to the command code as variables with the same name as defined in the `name` field and will be of the specified `type`.
When sending a command over serial, parameters should be provided in the order they are defined in the `parameters` list.

#### Validation

When a command is invoked, the following checks are performed on the parameters:
- If a parameter is marked as `required` but is not provided
- If a parameter is provided but does not match the specified `type`

If a parameter is not required and not provided, the `default` value will be used if specified.
If a parameter is not required, not provided and has no default value, it will be set to `None`.

### Command Code

The `code` field contains the microPython code that will be executed on the Lego Spike hub when the command is invoked. The code can use the parameters defined in the `parameters` list.

Use the `print()` function to send output back to the host computer over serial.

> [!IMPORTANT]
> Do not return values from the command code. Instead, use `print()` to send data back to the host.

## Acknowledgments

The basic serial code is based on the work of [ammardaher](https://github.com/ammardaher/LEGO-Spike-USB-Serial-Console).
