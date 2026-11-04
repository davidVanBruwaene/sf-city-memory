#!/bin/zsh
# Double-click in Finder: quits Claude, adds the sf-city MCP server to Claude Desktop, reopens Claude.
cd "$(dirname "$0")" && .venv/bin/python connect_claude.py
echo "Done. You can close this window."
