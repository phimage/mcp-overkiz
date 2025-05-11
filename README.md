# mcp-overkiz MCP server

MCP server for controlling lights using pyoverkiz

## Components

### Resources

The server implements a light control system with:
- Custom light:// URI scheme for accessing individual light devices
- Each light resource has a name and current state (On/Off)
- The resources are automatically discovered from your Overkiz/Somfy account

### Tools

The server implements three tools:
- list-lights: Lists all available lights and their current status
  - Takes no arguments
- light-on: Turns on a light by name
  - Takes "name" as a required string argument
- light-off: Turns off a light by name
  - Takes "name" as a required string argument

## Configuration

The server requires the following environment variables:
- `OVERKIZ_USERNAME`: Your Overkiz/Somfy account username
- `OVERKIZ_PASSWORD`: Your Overkiz/Somfy account password
- `OVERKIZ_SERVER`: The Overkiz server to connect to (defaults to "somfy-europe")

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

Once the server is running and connected to Claude, you can control your lights with commands like:

- "List all my lights"
- "Turn on the living room light"
- "Turn off the bedroom light"
