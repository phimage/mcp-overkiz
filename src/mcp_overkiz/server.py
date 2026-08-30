import asyncio
import os
import urllib.parse

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
from pydantic import AnyUrl

from pyoverkiz.client import OverkizClient
from pyoverkiz.models import Command
from pyoverkiz.enums import ExecutionState
from pyoverkiz.const import SUPPORTED_SERVERS

# Overkiz configuration (get from environment variables)
# For Bouygues Flexom accounts, set OVERKIZ_SERVER=flexom
OVERKIZ_USERNAME = os.environ.get("OVERKIZ_USERNAME", "")
OVERKIZ_PASSWORD = os.environ.get("OVERKIZ_PASSWORD", "")
OVERKIZ_SERVER = os.environ.get("OVERKIZ_SERVER", "somfy-europe")

# Overkiz client and devices cache
overkiz_client = None
light_devices = {}   # device label -> Device, for lights
cover_devices = {}   # device label -> Device, for shutters / blinds

server = Server("overkiz-mcp")

# Overkiz core commands for roller shutters (position scale: 0 = closed, 100 = open)
CMD_COVER_UP = "up"
CMD_COVER_DOWN = "down"
CMD_COVER_STOP = "stop"
CMD_COVER_SET_POSITION = "setPosition"


def is_cover_device(device) -> bool:
    """Return True if the device looks like a shutter / blind (cover)."""
    widgets = [device.widget, getattr(device, "widget_name", None), device.ui_class]
    for w in widgets:
        if not w:
            continue
        s = str(w)
        if "shutter" in s.lower() or "blind" in s.lower():
            return True
    return False


def supports_command(device, cmd: str) -> bool:
    """Best-effort check that a device accepts a given core command."""
    fn = getattr(device, "supports_command", None)
    if callable(fn):
        try:
            return bool(fn(cmd))
        except Exception:
            pass
    cmds = getattr(getattr(device, "definition", None), "commands", None)
    if isinstance(cmds, (list, tuple, set, frozenset, dict)):
        try:
            return cmd in {getattr(c, "name", c) for c in cmds}
        except TypeError:
            return False
    return True


def cover_supports(device, cmd: str, **_kwargs) -> bool:
    return supports_command(device, cmd)


def state_name_value(states, *names):
    """Pick the value of the first matching state from a State list/dict."""
    if isinstance(states, dict):
        items = states.values()
        for n in names:
            st = states.get(n)
            if st is not None:
                return st.value
    elif states:
        for st in states:
            if getattr(st, "name", None) in names:
                return st.value
    return None


def format_cover_position(value) -> str:
    """Human-readable position label (0 = closed, 100 = open, 124 = unknown)."""
    try:
        pct = int(value)
    except (TypeError, ValueError):
        return str(value)
    if pct == 124:
        return "unknown (124)"
    if pct == 108:
        return "my position (108)"
    if pct <= 0:
        return "closed (0%)"
    if pct >= 100:
        return "open (100%)"
    return f"{pct}% open"


def get_cover_state_text(device) -> str:
    states = getattr(device, "states", None)
    pos = state_name_value(states, "core:PositionState", "PositionState")
    if pos is not None:
        return format_cover_position(pos)
    closed = state_name_value(states, "core:OpenClosedState", "OpenClosedState")
    if closed is not None:
        return "closed" if closed == "CLOSED" else ("open" if closed == "OPEN" else str(closed))
    return "Unknown"


async def execute_and_wait(device, cmd_name: str, cmd_params=None) -> int:
    """Send a core command to a device and wait for execution to complete."""
    command = Command(cmd_name, cmd_params or [])
    execution_id = await overkiz_client.execute_commands(device.device_url, [command])
    current_execution = await overkiz_client.get_current_execution(execution_id)
    for _ in range(600):
        if current_execution is None or current_execution.state != ExecutionState.COMPLETED:
            break
        await asyncio.sleep(1)
        current_execution = await overkiz_client.get_current_execution(execution_id)
    return execution_id


# Function to initialize the Overkiz client
async def initialize_overkiz_client():
    global overkiz_client, light_devices, cover_devices

    if not OVERKIZ_USERNAME or not OVERKIZ_PASSWORD:
        print("Overkiz credentials not configured. Set OVERKIZ_USERNAME and OVERKIZ_PASSWORD environment variables.")
        return False

    overkiz_server = SUPPORTED_SERVERS.get(OVERKIZ_SERVER)
    if not overkiz_server:
        print(f"Overkiz server '{OVERKIZ_SERVER}' unknown. Use one of: {', '.join(SUPPORTED_SERVERS)}")
        return False

    overkiz_client = OverkizClient(username=OVERKIZ_USERNAME, password=OVERKIZ_PASSWORD, server=overkiz_server)
    await overkiz_client.login()

    # Get all devices
    devices = await overkiz_client.get_devices()

    # Filter for light devices and build a map with friendly names
    for device in devices:
        widget = str(getattr(device, "widget", "") or "")
        if "Light" in widget or "OnOff" in widget or "LightController" in widget:
            light_devices[device.label] = device
        if is_cover_device(device):
            cover_devices[device.label] = device

    return True


@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """
    List available Overkiz light and cover (shutter) devices.
    Lights are exposed with a light:// URI scheme, shutters with cover://.
    """
    resources = []

    # Add light resources if client is initialized
    if light_devices:
        for light_name, device in light_devices.items():
            state = "Unknown"
            try:
                for state_obj in (device.states or []):
                    if getattr(state_obj, "name", None) == "core:OnOffState":
                        state = "On" if state_obj.value else "Off"
                        break
            except Exception:
                pass

            encoded_light_name = urllib.parse.quote(light_name)
            resources.append(
                types.Resource(
                    uri=AnyUrl(f"light://{encoded_light_name}"),
                    name=f"Light: {light_name}",
                    description=f"Overkiz light device: {light_name} (Status: {state})",
                    mimeType="application/json",
                )
            )

    # Add cover (shutter) resources
    if cover_devices:
        for cover_name, device in cover_devices.items():
            state = get_cover_state_text(device)
            encoded_cover_name = urllib.parse.quote(cover_name)
            resources.append(
                types.Resource(
                    uri=AnyUrl(f"cover://{encoded_cover_name}"),
                    name=f"Shutter: {cover_name}",
                    description=f"Overkiz shutter/cover device: {cover_name} (Position: {state})",
                    mimeType="application/json",
                )
            )

    return resources


@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    """
    Read device info by its URI (light:// for lights, cover:// for shutters).
    The device name is extracted from the URI host component.
    """
    scheme = getattr(uri, "scheme", None) or str(uri).split("://", 1)[0]

    if scheme == "light":
        encoded_light_name = str(uri).replace("light://", "")
        light_name = urllib.parse.unquote(encoded_light_name)

        if light_name not in light_devices:
            raise ValueError(f"Light not found: {light_name}")

        device = light_devices[light_name]
        state = "Unknown"
        try:
            for state_obj in (device.states or []):
                if getattr(state_obj, "name", None) == "core:OnOffState":
                    state = state_obj.value
                    break
        except Exception:
            pass

        return f'{{"name": "{light_name}", "type": "light", "state": "{state}"}}'

    if scheme == "cover":
        encoded_cover_name = str(uri).replace("cover://", "")
        cover_name = urllib.parse.unquote(encoded_cover_name)

        if cover_name not in cover_devices:
            raise ValueError(f"Cover not found: {cover_name}")

        device = cover_devices[cover_name]
        state = get_cover_state_text(device)
        return f'{{"name": "{cover_name}", "type": "cover", "position": "{state}"}}'

    raise ValueError(f"Unsupported URI scheme: {scheme}")


@server.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]:
    """
    List available prompts.
    """
    return []


@server.get_prompt()
async def handle_get_prompt(
    name: str, arguments: dict[str, str] | None
) -> types.GetPromptResult:
    """
    Generate a prompt by combining arguments with server state.
    """
    raise ValueError(f"Unknown prompt: {name}")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    tools = []

    # Add light control tools if any light device is present
    if light_devices:
        tools.extend([
            types.Tool(
                name="list-lights",
                description="List all available lights and their current status",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="light-status",
                description="Get the status of a specific light by name",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "The name of the light to check status"},
                    },
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="light-on",
                description="Turn on a light by name",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "The name of the light to turn on"},
                    },
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="light-off",
                description="Turn off a light by name",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "The name of the light to turn off"},
                    },
                    "required": ["name"],
                },
            ),
        ])

    # Add cover / shutter control tools if any shutter device is present
    if cover_devices:
        cover_names = ", ".join(cover_devices.keys())
        tools.extend([
            types.Tool(
                name="list-covers",
                description="List all available shutters/blinds and their current position (0% = closed, 100% = open)",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="cover-status",
                description="Get the current position of a specific shutter by name",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": f"The shutter name (one of: {cover_names})"},
                    },
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="cover-up",
                description="Fully open (raise) a shutter by name",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "The shutter name"},
                    },
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="cover-down",
                description="Fully close (lower) a shutter by name",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "The shutter name"},
                    },
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="cover-stop",
                description="Stop a shutter currently moving",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "The shutter name"},
                    },
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="cover-position",
                description="Move a shutter to a specific position (0 = fully closed, 100 = fully open)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "The shutter name"},
                        "position": {"type": "integer", "minimum": 0, "maximum": 100,
                                    "description": "Target position, 0-100"},
                    },
                    "required": ["name", "position"],
                },
            ),
        ])

    return tools


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool execution requests.
    Tools can modify server state and notify clients of changes.
    """
    if name == "list-lights":
        if not light_devices:
            return [types.TextContent(type="text",
                text="No light devices available. Make sure the Overkiz client is properly initialized.")]

        light_info = []
        for light_name, device in light_devices.items():
            try:
                states = await overkiz_client.get_state(device.device_url)
                state = "Unknown"
                for state_obj in states:
                    if getattr(state_obj, "name", None) == "core:OnOffState":
                        state = state_obj.value
                        break
                light_info.append(f"- {light_name}: {state}")
            except Exception:
                light_info.append(f"- {light_name}: Status unavailable")

        return [types.TextContent(type="text", text="Available lights:\n" + "\n".join(light_info))]

    elif name == "light-status":
        if not arguments:
            raise ValueError("Missing arguments")
        light_name = arguments.get("name")
        if not light_name:
            raise ValueError("Missing light name")
        if not light_devices:
            return [types.TextContent(type="text",
                text="No light devices available. Make sure the Overkiz client is properly initialized.")]
        if light_name not in light_devices:
            return [types.TextContent(type="text",
                text=f"Light '{light_name}' not found. Available lights: {', '.join(light_devices.keys())}")]

        device = light_devices[light_name]
        try:
            states = await overkiz_client.get_state(device.device_url)
            state = "Unknown"
            for state_obj in states:
                if getattr(state_obj, "name", None) == "core:OnOffState":
                    state = state_obj.value
                    break
            return [types.TextContent(type="text", text=f"Light '{light_name}' is currently {state}")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Failed to get status for light '{light_name}': {str(e)}")]

    elif name == "light-on" or name == "light-off":
        if not arguments:
            raise ValueError("Missing arguments")
        light_name = arguments.get("name")
        if not light_name:
            raise ValueError("Missing light name")
        if not light_devices:
            return [types.TextContent(type="text",
                text="No light devices available. Make sure the Overkiz client is properly initialized.")]
        if light_name not in light_devices:
            return [types.TextContent(type="text",
                text=f"Light '{light_name}' not found. Available lights: {', '.join(light_devices.keys())}")]

        action = "on" if name == "light-on" else "off"
        device = light_devices[light_name]
        verb = "turned on" if action == "on" else "turned off"
        try:
            await execute_and_wait(device, action)
            await server.request_context.session.send_resource_list_changed()
            return [types.TextContent(type="text", text=f"Successfully {verb} light '{light_name}'")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Failed to {verb} light '{light_name}': {str(e)}")]

    elif name == "list-covers":
        if not cover_devices:
            return [types.TextContent(type="text",
                text="No shutter/cover devices available. Make sure the Overkiz client is properly initialized.")]

        cover_info = []
        for cover_name, device in cover_devices.items():
            try:
                states = await overkiz_client.get_state(device.device_url)
                pos = state_name_value(states, "core:PositionState", "PositionState")
                if pos is None:
                    closed = state_name_value(states, "core:OpenClosedState", "OpenClosedState")
                    label = str(closed) if closed is not None else "Unknown"
                else:
                    label = format_cover_position(pos)
                cover_info.append(f"- {cover_name}: {label}")
            except Exception:
                cover_info.append(f"- {cover_name}: position unavailable")

        return [types.TextContent(type="text", text="Available shutters:\n" + "\n".join(cover_info))]

    elif name == "cover-status":
        if not arguments:
            raise ValueError("Missing arguments")
        cover_name = arguments.get("name")
        if not cover_name:
            raise ValueError("Missing shutter name")
        if not cover_devices:
            return [types.TextContent(type="text",
                text="No shutter/cover devices available. Make sure the Overkiz client is properly initialized.")]
        if cover_name not in cover_devices:
            return [types.TextContent(type="text",
                text=f"Shutter '{cover_name}' not found. Available shutters: {', '.join(cover_devices.keys())}")]

        device = cover_devices[cover_name]
        try:
            states = await overkiz_client.get_state(device.device_url)
            pos = state_name_value(states, "core:PositionState", "PositionState")
            if pos is None:
                closed = state_name_value(states, "core:OpenClosedState", "OpenClosedState")
                label = str(closed) if closed is not None else "Unknown"
            else:
                label = format_cover_position(pos)
            return [types.TextContent(type="text", text=f"Shutter '{cover_name}' position: {label}")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Failed to get position for shutter '{cover_name}': {str(e)}")]

    elif name in ("cover-up", "cover-down", "cover-stop", "cover-position"):
        if not arguments:
            raise ValueError("Missing arguments")
        cover_name = arguments.get("name")
        if not cover_name:
            raise ValueError("Missing shutter name")
        if not cover_devices:
            return [types.TextContent(type="text",
                text="No shutter/cover devices available. Make sure the Overkiz client is properly initialized.")]
        if cover_name not in cover_devices:
            return [types.TextContent(type="text",
                text=f"Shutter '{cover_name}' not found. Available shutters: {', '.join(cover_devices.keys())}")]

        device = cover_devices[cover_name]

        if name == "cover-up":
            cmd, params, verb = CMD_COVER_UP, None, "open"
        elif name == "cover-down":
            cmd, params, verb = CMD_COVER_DOWN, None, "close"
        elif name == "cover-stop":
            cmd, params, verb = CMD_COVER_STOP, None, "stop"
        else:
            position = arguments.get("position")
            try:
                position = int(position)
            except (TypeError, ValueError):
                return [types.TextContent(type="text", text="Invalid position: must be an integer between 0 and 100.")]
            if not 0 <= position <= 100:
                return [types.TextContent(type="text", text="Invalid position: must be between 0 and 100.")]
            cmd, params, verb = CMD_COVER_SET_POSITION, [position], f"move to {position}% open"

        if not cover_supports(device, cmd):
            return [types.TextContent(type="text",
                text=f"Shutter '{cover_name}' does not appear to support the '{cmd}' command. Available shutters: {', '.join(cover_devices.keys())}")]

        try:
            await execute_and_wait(device, cmd, params)
            await server.request_context.session.send_resource_list_changed()
            return [types.TextContent(type="text", text=f"Successfully {verb} shutter '{cover_name}'")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Failed to {verb} shutter '{cover_name}': {str(e)}")]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    # Initialize Overkiz client before starting the server
    if not await initialize_overkiz_client():
        return

    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="overkiz-mcp",
                server_version="0.2.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
