# hex-dashboard-mcp

MCP server for building and maintaining Hex notebooks from Claude Code. Wraps the Hex API with design-system-aware chart injection, notebook diagnostics, and full cell lifecycle management.

## What it does

**18 tools** across five categories:

**Cell management** — read, create, update, and delete cells (CODE, SQL, MARKDOWN). Supports positional insertion and label-based identification.

**Run management** — trigger runs, poll status, cancel, view history. `run_and_wait` blocks until completion so the published app updates automatically without manual refresh.

**Chart injection** — `inject_plotly_chart`, `inject_pydeck_map`, and `inject_html_component` write fully styled code into cells using a built-in dark design system (Inter font, indigo accent palette, dark surfaces). KPI cards, section headers, and alert banners are templated.

**Diagnostics** — `diagnose_notebook` cross-references cell sources with run errors to surface root causes. `inspect_filter_behavior` reproduces failures with specific filter inputs.

**Design system** — `get_design_system` returns all tokens (colors, fonts, chart defaults). `apply_workspace_palette` sets the chart color sequence workspace-wide.

## Setup

Requires Python 3.11+ and a Hex API token (generate one from your workspace settings under API keys).

```bash
python -m venv .venv
.venv/bin/pip install fastmcp httpx
```

### Claude Code Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "hex-dashboard": {
      "command": "/path/to/hex-dashboard-mcp/.venv/bin/python",
      "args": ["/path/to/hex-dashboard-mcp/server.py"],
      "env": {
        "HEX_API_KEY": "your_hex_api_key",
        "HEX_API_URL": "https://app.hex.tech/api/v1"
      }
    }
  }
}
```

### Claude Code CLI

```bash
claude mcp add --scope user --transport stdio hex-dashboard \
  /path/to/hex-dashboard-mcp/.venv/bin/python /path/to/hex-dashboard-mcp/server.py
```

Set `HEX_API_KEY` and `HEX_API_URL` in your shell environment.

## Using with the Hex CLI

The [official Hex CLI](https://github.com/hex-inc/hex-cli) (`brew install hex-inc/hex-cli/hex`) complements this MCP well. Use each where it's strongest:

| Task | Tool |
|---|---|
| List projects, cells, runs | `hex` CLI (`--json \| jq`) |
| Quick status checks | `hex` CLI |
| Create/update/delete cells | MCP |
| Inject styled charts, maps, HTML | MCP |
| Run + auto-poll after edits | MCP (`run_and_wait`) |
| Diagnose failures | MCP (`diagnose_notebook`) |

Rule of thumb: **reading = CLI, writing/styling = MCP.**

## Skill file

`CLAUDE.md` contains agent instructions for Claude Code — the design system spec, workflow guidance, troubleshooting playbook, and tool selection rules. Install it as a Claude Code skill or place it alongside the server for automatic pickup.

## Tools reference

| Tool | Description |
|---|---|
| `list_projects` | List workspace projects |
| `get_project` | Project details + all cells |
| `get_cell_source` | Read a cell's source |
| `create_cell` | Add a new cell (CODE/SQL/MARKDOWN) |
| `update_cell_source` | Write to an existing cell |
| `delete_cell` | Remove a cell |
| `run_project` | Trigger a run |
| `run_and_wait` | Run and block until completion |
| `get_run_status` | Poll run status |
| `get_run_history` | Recent run history |
| `cancel_run` | Cancel a running execution |
| `diagnose_notebook` | Full diagnostic sweep |
| `inspect_filter_behavior` | Test specific filter combinations |
| `inject_plotly_chart` | Write a styled Plotly chart |
| `inject_pydeck_map` | Write a styled PyDeck map |
| `inject_html_component` | Write KPI cards, headers, banners |
| `get_design_system` | Return design tokens |
| `apply_workspace_palette` | Set workspace chart colors |
