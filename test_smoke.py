import asyncio
import sys
sys.path.insert(0, "src")
import mcp_overkiz.server as srv

# --- mock devices (no network) ---
class FakeState:
    def __init__(self, name, value):
        self.name = name
        self.value = value

class FakeDef:
    commands = ["up", "down", "stop", "setPosition"]
class FakeDefNoSet:
    commands = ["up", "down", "stop"]

class FakeDevice:
    def __init__(self, label, widget, states, definition=None, ui_class="RollerShutter"):
        self.label = label
        self.widget = widget
        self.ui_class = ui_class
        self.device_url = f"https://fake/{label}"
        self.states = states
        self.definition = definition or FakeDef()
    def supports_command(self, cmd):
        return cmd in self.definition.commands

lights = [FakeDevice("Salon", "OnOffLight", [FakeState("core:OnOffState", "OFF")], ui_class="Light")]
covers = [
    FakeDevice("Volet Salon", "PositionableRollerShutter", [FakeState("core:PositionState", 100)]),
    FakeDevice("Volet Cuisine", "UpDownRollerShutter", [FakeState("core:PositionState", 0)]),
    FakeDevice("Lame Bureau", "PositionableVenetianBlind", [FakeState("core:PositionState", 124)]),
    FakeDevice("Persienne Simple", "UpDownRollerShutter", [], FakeDefNoSet()),
]

assert srv.is_cover_device(covers[0])
assert srv.is_cover_device(covers[3])
assert srv.format_cover_position(100) == "open (100%)"
assert srv.format_cover_position(0) == "closed (0%)"
assert "unknown" in srv.format_cover_position(124)
assert "50" in srv.format_cover_position(50)
assert not srv.is_cover_device(lights[0])
assert srv.state_name_value([FakeState("core:OnOffState", "OFF")], "core:OnOffState") == "OFF"
assert srv.state_name_value([], "core:OnOffState") is None

srv.overkiz_client = object()
srv.light_devices = {d.label: d for d in lights}
srv.cover_devices = {d.label: d for d in covers}

async def main():
    tools = await srv.handle_list_tools()
    names = sorted(t.name for t in tools)
    print("TOOLS:", names)
    expected = {"list-lights", "light-status", "light-on", "light-off",
                "list-covers", "cover-status", "cover-up", "cover-down", "cover-stop", "cover-position"}
    assert expected <= set(names), expected - set(names)

    res = await srv.handle_call_tool("list-covers", {})
    print(res[0].text)
    res = await srv.handle_call_tool("cover-status", {"name": "Volet Cuisine"})
    print(res[0].text)
    res = await srv.handle_call_tool("cover-position", {"name": "Persienne Simple", "position": 40})
    print("no-setpos:", res[0].text)
    res = await srv.handle_call_tool("cover-position", {"name": "Volet Salon", "position": "abc"})
    print("badpos:", res[0].text)
    res = await srv.handle_call_tool("cover-status", {"name": "inexistant"})
    print("notfound:", res[0].text)
    # unknown tool
    try:
        await srv.handle_call_tool("nope", {})
        assert False
    except ValueError as e:
        print("unknown ok:", e)

    # resource listing
    from pydantic import AnyUrl
    rs = await srv.handle_list_resources()
    schemes = sorted(r.uri.scheme for r in rs)
    print("RESOURCE SCHEMES:", schemes)
    out = await srv.handle_read_resource(AnyUrl("cover://Volet%20Salon"))
    print("READ cover:", out)
    out = await srv.handle_read_resource(AnyUrl("light://Salon"))
    print("READ light:", out)

asyncio.run(main())
print("ALL OK")
