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
OVERKIZ_USERNAME = os.environ.get("OVERKIZ_USERNAME", "")
OVERKIZ_PASSWORD = os.environ.get("OVERKIZ_PASSWORD", "")
OVERKIZ_SERVER = os.environ.get("OVERKIZ_SERVER", "somfy-europe")

# Overkiz client and devices cache
overkiz_client = None
light_devices = {}  # Will store device_name -> device mappings

server = Server("overkiz-mcp")

# Function to initialize the Overkiz client
async def initialize_overkiz_client():
    global overkiz_client, light_devices
    
    if not OVERKIZ_USERNAME or not OVERKIZ_PASSWORD:
        print("Overkiz credentials not configured. Set OVERKIZ_USERNAME and OVERKIZ_PASSWORD environment variables.")
        return False
  
    overkiz_server = SUPPORTED_SERVERS.get(OVERKIZ_SERVER)
    if not overkiz_server:
        print("Overkiz server not configured. Set OVERKIZ_SERVER environment variable.")
        return False
    
    overkiz_client = OverkizClient(username=OVERKIZ_USERNAME, password=OVERKIZ_PASSWORD, server=overkiz_server)
    await overkiz_client.login()
    
    # Get all devices
    devices = await overkiz_client.get_devices()
    
    # Filter for light devices and build a map with friendly names
    for device in devices:
        if "Light" in device.widget or "OnOff" in device.widget or "LightController" in device.widget:
            light_devices[device.label] = device
            
    return True
 

@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """
    List available Overkiz light devices.
    Each light is exposed as a resource with a custom light:// URI scheme.
    """
    resources = []
    
    # Add light resources if client is initialized
    if light_devices:
        for light_name, device in light_devices.items():
            state = "Unknown"
            try:
                # Try to get current state if possible
                for state_obj in device.states:
                    if state_obj.name == "core:OnOffState":
                        state = "On" if state_obj.value else "Off"
                        break
            except:
                pass
                
            # URL encode the light name to handle special characters in URIs
            encoded_light_name = urllib.parse.quote(light_name)
                
            resources.append(
                types.Resource(
                    uri=AnyUrl(f"light://{encoded_light_name}"),
                    name=f"Light: {light_name}",
                    description=f"Overkiz light device: {light_name} (Status: {state})",
                    mimeType="application/json",
                )
            )
    
    return resources

@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    """
    Read light device info by its URI.
    The light name is extracted from the URI host component.
    """
    if uri.scheme == "light":
        # Extract and URL decode the light name
        encoded_light_name = str(uri).replace("light://", "")
        light_name = urllib.parse.unquote(encoded_light_name)
        
        if light_name not in light_devices:
            raise ValueError(f"Light not found: {light_name}")
            
        device = light_devices[light_name]
        state = "Unknown"
        
        try:
            # Get the latest device state
            for state_obj in device.states:
                if state_obj.name == "core:OnOffState":
                    state = "On" if state_obj.value else "Off"
                    break
        except:
            pass
            
        return f"{{\"name\": \"{light_name}\", \"state\": \"{state}\"}}"
    
    raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

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
    
    # Add light control tools if client is initialized
    if light_devices:
        tools.extend([
            types.Tool(
                name="list-lights",
                description="List all available lights and their current status",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
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
            )
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
            return [
                types.TextContent(
                    type="text",
                    text="No light devices available. Make sure the Overkiz client is properly initialized.",
                )
            ]
        
        # Get the latest status for all lights
        light_info = []
        for light_name, device in light_devices.items():
            try:
                # Get the latest device state
                states = await overkiz_client.get_state(device.device_url)
                # Find the on/off state
                state = "Unknown"
                for state_obj in states:
                    if state_obj.name == "core:OnOffState":
                        state = state_obj.value
                        break
                        
                light_info.append(f"- {light_name}: {state}")
            except Exception:
                light_info.append(f"- {light_name}: Status unavailable")
        
        return [
            types.TextContent(
                type="text",
                text="Available lights:\n" + "\n".join(light_info),
            )
        ]
    
    elif name == "light-status":
        if not arguments:
            raise ValueError("Missing arguments")
            
        light_name = arguments.get("name")
        if not light_name:
            raise ValueError("Missing light name")
            
        if not light_devices:
            return [
                types.TextContent(
                    type="text",
                    text="No light devices available. Make sure the Overkiz client is properly initialized.",
                )
            ]
            
        if light_name not in light_devices:
            return [
                types.TextContent(
                    type="text",
                    text=f"Light '{light_name}' not found. Available lights: {', '.join(light_devices.keys())}",
                )
            ]
            
        # Get the status of the light
        device = light_devices[light_name]
        try:
            # Refresh device status
            states = await overkiz_client.get_state(device.device_url)
            # Get the current state
            state = "Unknown"
            for state_obj in states:
                if state_obj.name == "core:OnOffState":
                    state = state_obj.value
                    break
                    
            return [
                types.TextContent(
                    type="text",
                    text=f"Light '{light_name}' is currently {state}",
                )
            ]
        except Exception as e:
            return [
                types.TextContent(
                    type="text",
                    text=f"Failed to get status for light '{light_name}': {str(e)}",
                )
            ]
    
    elif name == "light-on":
        if not arguments:
            raise ValueError("Missing arguments")
            
        light_name = arguments.get("name")
        if not light_name:
            raise ValueError("Missing light name")
            
        if not light_devices:
            return [
                types.TextContent(
                    type="text",
                    text="No light devices available. Make sure the Overkiz client is properly initialized.",
                )
            ]
            
        if light_name not in light_devices:
            return [
                types.TextContent(
                    type="text",
                    text=f"Light '{light_name}' not found. Available lights: {', '.join(light_devices.keys())}",
                )
            ]
            
        # Turn on the light
        device = light_devices[light_name]
        try:
            # Create ON command
            command = Command("on")
            execution_id = await overkiz_client.execute_commands(device.device_url, [command])
            
            # Wait for execution to complete
            current_execution = await overkiz_client.get_current_execution(execution_id)
            while current_execution and current_execution.state != ExecutionState.COMPLETED:
                await asyncio.sleep(1)
                current_execution = await overkiz_client.get_current_execution(execution_id)
                
            # Notify clients that resources have changed
            await server.request_context.session.send_resource_list_changed()
                
            return [
                types.TextContent(
                    type="text",
                    text=f"Successfully turned on light '{light_name}'",
                )
            ]
        except Exception as e:
            return [
                types.TextContent(
                    type="text",
                    text=f"Failed to turn on light '{light_name}': {str(e)}",
                )
            ]
    
    elif name == "light-off":
        if not arguments:
            raise ValueError("Missing arguments")
            
        light_name = arguments.get("name")
        if not light_name:
            raise ValueError("Missing light name")
            
        if not light_devices:
            return [
                types.TextContent(
                    type="text",
                    text="No light devices available. Make sure the Overkiz client is properly initialized.",
                )
            ]
            
        if light_name not in light_devices:
            return [
                types.TextContent(
                    type="text",
                    text=f"Light '{light_name}' not found. Available lights: {', '.join(light_devices.keys())}",
                )
            ]
            
        # Turn off the light
        device = light_devices[light_name]
        try:
            # Create OFF command
            command = Command("off")
            execution_id = await overkiz_client.execute_commands(device.device_url, [command])
            
            # Wait for execution to complete
            current_execution = await overkiz_client.get_current_execution(execution_id)
            while current_execution and current_execution.state != ExecutionState.COMPLETED:
                await asyncio.sleep(1)
                current_execution = await overkiz_client.get_current_execution(execution_id)
                
            # Notify clients that resources have changed
            await server.request_context.session.send_resource_list_changed()
                
            return [
                types.TextContent(
                    type="text",
                    text=f"Successfully turned off light '{light_name}'",
                )
            ]
        except Exception as e:
            return [
                types.TextContent(
                    type="text",
                    text=f"Failed to turn off light '{light_name}': {str(e)}",
                )
            ]
    
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
                server_version="0.1.2",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
