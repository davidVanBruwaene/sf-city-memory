"""Add the sf-city MCP server to Claude Desktop. Run it from Terminal.app: it quits Claude, edits the config, reopens Claude."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
ENTRY = {"command": str(HERE / ".venv/bin/python"), "args": [str(HERE / "city_mcp.py")], "env": {"CITY_USER": "david"}}


def running():
    # Match the app binary by path: Claude Code's own processes run as a lowercase .../claude.app/.../claude.
    ps = subprocess.run(["ps", "-axo", "comm="], capture_output=True, text=True).stdout
    return any(line.strip().endswith("/Claude.app/Contents/MacOS/Claude") for line in ps.splitlines())


def add(config):
    d = json.loads(config.read_text())
    d.setdefault("mcpServers", {})["sf-city"] = ENTRY
    tmp = config.with_name(config.name + ".tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, config)
    return list(d["mcpServers"])


def main():
    # Claude rewrites this file from memory while it runs, so the edit only survives if Claude is closed.
    if running():
        print("Waiting for Claude to quit: press Cmd+Q in Claude now, and confirm if it asks.")
        subprocess.run(["osascript", "-e", 'quit app "Claude"'], capture_output=True)
        for _ in range(1200):
            if not running():
                break
            time.sleep(0.5)
        else:
            sys.exit("Claude is still running after 10 minutes: quit it with Cmd+Q and run this again")
    print("sf-city added; local MCP servers:", ", ".join(add(CONFIG)))
    subprocess.run(["open", "-a", "Claude"])
    print("Claude is reopening: start a new chat, click + then Connectors, and sf-city should be listed")


if __name__ == "__main__":
    main()
