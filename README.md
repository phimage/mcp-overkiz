# mcp-overkiz MCP server

MCP server for controlling lights and shutters (covers) using pyoverkiz

## Components

### Resources

The server implements a lights and covers control system with:
- Custom `light://` URI scheme for accessing individual light devices — each resource has a name and current state (On/Off)
- Custom `cover://` URI scheme for shutters/blinds — each resource has a name and current position (0% = closed, 100% = open)
- Resources are automatically discovered from your Overkiz/Somfy/Flexom account

### Tools

Lights:
- `list-lights`: Lists all available lights and their current status
- `light-on` / `light-off`: Turns a light on/off by name
- `light-status`: Gets the status of a specific light by name

Shutters / blinds (covers):
- `list-covers`: Lists all available shutters and their current position
- `cover-up`: Fully opens (raises) a shutter
- `cover-down`: Fully closes (lowers) a shutter
- `cover-stop`: Stops a shutter currently moving
- `cover-position`: Moves a shutter to a specific position (0 = closed, 100 = open)
- `cover-status`: Gets the current position of a specific shutter by name

All cover tools take `name` as a required string argument; `cover-position` also takes `position` (integer 0-100).

## Configuration

The server requires the following environment variables:
- `OVERKIZ_USERNAME`: Your Overkiz/Somfy account username (usually your email)
- `OVERKIZ_PASSWORD`: Your Overkiz/Somfy account password
- `OVERKIZ_SERVER`: The Overkiz server to connect to. Valid values: `somfy-europe` (default), `somfy-america`, `somfy-oceania`, `flexom` (Bouygues Flexom), `atlantic-cozytouch`, `brandt`, `hexaom-hexaconnect`, `sauter-cozytouch`, `thermor-cozytouch`, `ubiwizz`, `nexity`, `rexel`

Tip: instead of pasting your password directly in your MCP config, write the three
`OVERKIZ_*` values into a shell file (e.g. `~/Documents/mcp-overkiz.env`) and load it
from the MCP client env section when supported, or keep the env values inline — the
password is only ever read locally by the server, never sent anywhere but the Overkiz
cloud for your login.

## Quickstart

### Running with Claude Desktop

#### Claude Desktop

- On MacOS: `~/Library/Application\ Support/Claude/claude_desktop_config.json`
- On Windows: `%APPDATA%/Claude/claude_desktop_config.json`

<details>
  <summary>Published Servers Configuration</summary>
  
  ```json
  "mcpServers": {
    "overkiz-mcp": {
      "command": "uvx",
      "args": [
        "mcp-overkiz"
      ],
      "env": {
        "OVERKIZ_USERNAME": "your-email@example.com",
        "OVERKIZ_PASSWORD": "your-password",
        "OVERKIZ_SERVER": "somfy-europe"
      }
    }
  }
  ```
</details>

<details>
  <summary>Development/Unpublished Servers Configuration</summary>
  
  ```json
  "mcpServers": {
    "overkiz-mcp": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/project/folder/mcp-overkiz",
        "mcp-overkiz"
      ],
      "env": {
        "OVERKIZ_USERNAME": "your-email@example.com",
        "OVERKIZ_PASSWORD": "your-password",
        "OVERKIZ_SERVER": "somfy-europe"
      }
    }
  }
  ```
</details>

### Example Usage

Once the server is running and connected to your MCP client, you can control your home with commands like:

Lights:
- "List all my lights"
- "Turn on the living room light"
- "Turn off the bedroom light"

Shutters:
- "What's the position of my shutters?"
- "Close all the shutters"
- "Open the kitchen shutter"
- "Set the living room shutter to 50%"
- "Stop the shutter"
