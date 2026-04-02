"""
Hex Dashboard MCP Server
Wraps the Hex API with design-focused tools for Claude Code.
Handles chart injection, auto-run, diagnostics, and design system application.
"""

import asyncio
import json
import os
import time
from typing import Any, Optional

import httpx
from fastmcp import FastMCP

# ─── Config ───────────────────────────────────────────────────────────────────

HEX_API_KEY = os.environ.get("HEX_API_KEY", "")
HEX_API_URL = os.environ.get("HEX_API_URL", "https://app.hex.tech/api/v1")
HEX_APP_URL = os.environ.get("HEX_APP_URL", "https://app.hex.tech")

if not HEX_API_KEY:
    raise RuntimeError("HEX_API_KEY environment variable is required")

HEADERS = {
    "Authorization": f"Bearer {HEX_API_KEY}",
    "Content-Type": "application/json",
}

mcp = FastMCP(
    "hex-dashboard",
    instructions="""
    You are working with a Hex Enterprise workspace to build and maintain
    data dashboards. You have access to tools for reading and writing notebook
    cells, triggering runs, monitoring run status, and diagnosing failures.

    Always follow the design system defined in CLAUDE.md. When iterating on
    a dashboard, update cells then call run_and_wait so the app view reflects
    changes without the user needing to refresh or rerun manually.
    """,
)

# ─── Design System ────────────────────────────────────────────────────────────

DESIGN_SYSTEM = {
    "colors": {
        "bg": "#0D0D0F",
        "surface": "#16161A",
        "surface_raised": "#1E1E24",
        "border": "#2A2A30",
        "text_primary": "#F0F0F5",
        "text_muted": "#6B6B7A",
        "text_disabled": "#3D3D47",
        "accent": "#6366F1",
        "accent_2": "#22D3EE",
        "accent_3": "#F59E0B",
        "accent_4": "#A78BFA",
        "accent_5": "#34D399",
        "positive": "#10B981",
        "negative": "#F43F5E",
        "warning": "#F59E0B",
        "chart_sequence": [
            "#6366F1", "#22D3EE", "#F59E0B",
            "#A78BFA", "#34D399", "#F43F5E",
            "#38BDF8", "#FB923C", "#4ADE80",
        ],
    },
    "font": "Inter, DM Sans, system-ui, sans-serif",
    "font_size": {"tick": 11, "label": 13, "title": 15},
    "map_style": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
}

DS = DESIGN_SYSTEM  # shorthand


def plotly_layout_defaults(title: str = "", height: int = 400) -> dict:
    """Return a Plotly layout dict matching the design system."""
    c = DS["colors"]
    return {
        "title": {
            "text": title,
            "font": {"family": DS["font"], "size": DS["font_size"]["title"], "color": c["text_primary"]},
            "x": 0,
            "xanchor": "left",
            "pad": {"l": 4},
        },
        "height": height,
        "paper_bgcolor": c["surface"],
        "plot_bgcolor": c["surface"],
        "font": {"family": DS["font"], "color": c["text_muted"], "size": DS["font_size"]["tick"]},
        "xaxis": {
            "gridcolor": c["border"],
            "linecolor": c["border"],
            "tickfont": {"color": c["text_muted"], "size": DS["font_size"]["tick"]},
            "title_font": {"color": c["text_primary"], "size": DS["font_size"]["label"]},
            "zeroline": False,
        },
        "yaxis": {
            "gridcolor": c["border"],
            "linecolor": c["border"],
            "tickfont": {"color": c["text_muted"], "size": DS["font_size"]["tick"]},
            "title_font": {"color": c["text_primary"], "size": DS["font_size"]["label"]},
            "zeroline": False,
        },
        "legend": {
            "bgcolor": "rgba(0,0,0,0)",
            "font": {"color": c["text_muted"], "size": DS["font_size"]["tick"]},
            "borderwidth": 0,
        },
        "margin": {"l": 48, "r": 16, "t": 40, "b": 40},
        "hoverlabel": {
            "bgcolor": c["surface_raised"],
            "bordercolor": c["accent"],
            "font": {"family": DS["font"], "color": c["text_primary"], "size": 12},
        },
        "colorway": DS["colors"]["chart_sequence"],
    }


# ─── HTTP helpers ─────────────────────────────────────────────────────────────

async def hex_get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{HEX_API_URL}{path}", headers=HEADERS, params=params)
        r.raise_for_status()
        return r.json()


async def hex_post(path: str, body: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{HEX_API_URL}{path}", headers=HEADERS, json=body or {})
        r.raise_for_status()
        return r.json()


async def hex_patch(path: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.patch(f"{HEX_API_URL}{path}", headers=HEADERS, json=body)
        r.raise_for_status()
        return r.json()


async def hex_delete(path: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.delete(f"{HEX_API_URL}{path}", headers=HEADERS)
        r.raise_for_status()
        return r.json() if r.content else {}


# ─── Project tools ────────────────────────────────────────────────────────────

@mcp.tool()
async def list_projects(search: str = "", limit: int = 20) -> str:
    """
    List Hex projects in the workspace. Optionally filter by name substring.
    Returns project IDs, names, and app URLs needed for other tools.
    """
    params = {"limit": limit}
    if search:
        params["search"] = search
    data = await hex_get("/projects", params=params)
    projects = data.get("values", data) if isinstance(data, dict) else data
    results = []
    for p in projects[:limit]:
        results.append({
            "id": p.get("id"),
            "name": p.get("title") or p.get("name"),
            "status": p.get("status"),
            "app_url": f"{HEX_APP_URL}/app/{p.get('id')}/latest",
            "edit_url": f"{HEX_APP_URL}/hex/{p.get('id')}",
            "last_edited": p.get("lastEditedAt") or p.get("updatedAt"),
        })
    return json.dumps(results, indent=2)


@mcp.tool()
async def get_project(project_id: str) -> str:
    """
    Get full details of a Hex project including all cells with their
    type, source, and position. Use this before editing to understand
    the current notebook structure.
    """
    data = await hex_get(f"/projects/{project_id}")
    # Cells are a separate endpoint in the Hex API
    cells_data = await hex_get("/cells", params={"projectId": project_id, "limit": 100})
    raw_cells = cells_data.get("values", cells_data) if isinstance(cells_data, dict) else cells_data
    cells = []
    for cell in raw_cells:
        # Extract source from nested contents structure
        contents = cell.get("contents", {})
        source = ""
        for key in ("codeCell", "sqlCell", "markdownCell"):
            if key in contents:
                source = contents[key].get("source", "")
                break
        cells.append({
            "id": cell.get("id"),
            "type": cell.get("cellType"),
            "label": cell.get("label"),
            "source": source[:500],  # truncate for readability
        })
    return json.dumps({
        "id": data.get("id"),
        "name": data.get("title"),
        "description": data.get("description"),
        "app_url": f"{HEX_APP_URL}/app/{project_id}/latest",
        "edit_url": f"{HEX_APP_URL}/hex/{project_id}",
        "cells": cells,
    }, indent=2)


@mcp.tool()
async def get_cell_source(project_id: str, cell_id: str) -> str:
    """
    Read the full source code of a specific cell (Python, SQL, or HTML).
    Use this before updating to understand what's already there.
    """
    data = await hex_get(f"/cells/{cell_id}")
    contents = data.get("contents", {})
    cell_type = data.get("cellType", "")
    source = ""
    for key in ("codeCell", "sqlCell", "markdownCell"):
        if key in contents:
            source = contents[key].get("source", "")
            break
    return json.dumps({
        "id": data.get("id"),
        "type": cell_type,
        "label": data.get("label"),
        "source": source,
    }, indent=2)


@mcp.tool()
async def update_cell_source(project_id: str, cell_id: str, source: str, cell_type: str = "CODE") -> str:
    """
    Write new source code to a cell (Python, SQL, or Markdown).
    cell_type: CODE | SQL | MARKDOWN (default CODE). Used to wrap source
    in the correct API structure.
    After updating cells, call run_and_wait to push changes to the app view.
    The published app refreshes automatically when a run completes — no
    manual page refresh needed.
    """
    # Map cell type to the API's contents key
    type_key_map = {"CODE": "codeCell", "SQL": "sqlCell", "MARKDOWN": "markdownCell"}
    content_key = type_key_map.get(cell_type.upper(), "codeCell")
    body = {"contents": {content_key: {"source": source}}}
    data = await hex_patch(f"/cells/{cell_id}", body)
    return json.dumps({
        "success": True,
        "cell_id": cell_id,
        "preview": source[:200],
    })


@mcp.tool()
async def create_cell(
    project_id: str,
    cell_type: str,
    source: str,
    label: str = "",
    insert_after_cell_id: str = None,
    data_connection_id: str = None,
) -> str:
    """
    Create a new cell in a Hex project.

    cell_type: CODE | SQL | MARKDOWN
    source: the cell's source code / SQL / markdown content
    label: optional display label for the cell
    insert_after_cell_id: optional cell ID to insert after (otherwise appends to end)
    data_connection_id: required for SQL cells — the Hex data connection UUID
    """
    type_key_map = {"CODE": "codeCell", "SQL": "sqlCell", "MARKDOWN": "markdownCell"}
    content_key = type_key_map.get(cell_type.upper(), "codeCell")

    body: dict = {
        "projectId": project_id,
        "cellType": cell_type.upper(),
        "contents": {content_key: {"source": source}},
    }
    if label:
        body["label"] = label
    if insert_after_cell_id:
        body["location"] = {"insertAfterCellId": insert_after_cell_id}
    if data_connection_id and cell_type.upper() == "SQL":
        body["dataConnectionId"] = data_connection_id

    data = await hex_post("/cells", body)
    return json.dumps({
        "id": data.get("id"),
        "type": data.get("cellType"),
        "label": data.get("label"),
        "project_id": project_id,
    }, indent=2)


@mcp.tool()
async def delete_cell(cell_id: str) -> str:
    """
    Delete a cell from a Hex project. Use with caution — this is irreversible.
    Always get_project() first to confirm the cell ID and contents before deleting.
    """
    await hex_delete(f"/cells/{cell_id}")
    return json.dumps({"deleted": True, "cell_id": cell_id})


# ─── Run management ───────────────────────────────────────────────────────────

@mcp.tool()
async def run_project(project_id: str, inputs: dict = None) -> str:
    """
    Trigger a Hex project run. Returns a run_id for status polling.
    Use run_and_wait instead if you want to block until completion.
    """
    body = {}
    if inputs:
        body["inputParams"] = inputs
    data = await hex_post(f"/projects/{project_id}/runs", body)
    return json.dumps({
        "run_id": data.get("runId") or data.get("id"),
        "status": data.get("status"),
        "project_id": project_id,
    })


@mcp.tool()
async def get_run_status(project_id: str, run_id: str) -> str:
    """
    Poll the status of a project run.
    Status values: PENDING, RUNNING, COMPLETED, ERRORED, KILLED, UNABLE_TO_ALLOCATE_KERNEL.
    Check elapsedTime and any trace/error details on ERRORED runs.
    """
    data = await hex_get(f"/projects/{project_id}/runs/{run_id}")
    return json.dumps({
        "run_id": run_id,
        "status": data.get("status"),
        "elapsed_ms": data.get("elapsedTime"),
        "error": data.get("error") or data.get("errorMessage"),
        "trace": data.get("trace"),
        "cells_errored": [
            c for c in data.get("cells", []) if c.get("status") == "ERRORED"
        ],
    }, indent=2)


@mcp.tool()
async def run_and_wait(
    project_id: str,
    inputs: dict = None,
    timeout_seconds: int = 300,
) -> str:
    """
    Run a Hex project and poll until it completes or errors.
    This is the primary tool for pushing notebook changes to the app view —
    after updating cells, call this and the published app will reflect the
    new results automatically without any manual refresh.

    Returns the final run status with error details if it failed.
    """
    run_resp = json.loads(await run_project(project_id, inputs))
    run_id = run_resp["run_id"]

    start = time.time()
    poll_interval = 3
    while True:
        elapsed = time.time() - start
        if elapsed > timeout_seconds:
            return json.dumps({
                "status": "TIMEOUT",
                "run_id": run_id,
                "message": f"Run did not complete within {timeout_seconds}s",
            })

        status_resp = json.loads(await get_run_status(project_id, run_id))
        status = status_resp["status"]

        if status in ("COMPLETED", "ERRORED", "CANCELLED", "KILLED"):
            status_resp["app_url"] = f"{HEX_APP_URL}/app/{project_id}/latest"
            status_resp["message"] = (
                "App view updated — no page refresh needed."
                if status == "COMPLETED"
                else f"Run {status}. Check error and cells_errored for details."
            )
            return json.dumps(status_resp, indent=2)

        await asyncio.sleep(poll_interval)
        poll_interval = min(poll_interval * 1.4, 15)  # back off, max 15s


@mcp.tool()
async def cancel_run(project_id: str, run_id: str) -> str:
    """Cancel a running Hex project run."""
    await hex_delete(f"/projects/{project_id}/runs/{run_id}")
    return json.dumps({"cancelled": True, "run_id": run_id})


@mcp.tool()
async def get_run_history(project_id: str, limit: int = 10) -> str:
    """
    Get recent run history for a project. Useful for spotting patterns
    in recurring failures (specific filters, specific times, etc).
    """
    data = await hex_get(f"/projects/{project_id}/runs", {"limit": limit})
    runs = data.get("runs", data) if isinstance(data, dict) else data
    results = []
    for r in runs:
        results.append({
            "run_id": r.get("runId") or r.get("id"),
            "status": r.get("status"),
            "started_at": r.get("startTime") or r.get("createdAt"),
            "elapsed_ms": r.get("elapsedTime"),
            "error": (r.get("error") or "")[:300],
            "triggered_by": r.get("triggerSource"),
        })
    return json.dumps(results, indent=2)


# ─── Diagnostics ─────────────────────────────────────────────────────────────

@mcp.tool()
async def diagnose_notebook(project_id: str, run_id: str = None) -> str:
    """
    Full diagnostic sweep of a Hex notebook.
    - Reads all cell sources
    - Pulls the most recent (or specified) run's error details
    - Identifies which cells failed and surfaces the error trace
    - Flags common issues: filter edge cases, missing variables,
      data type mismatches, empty dataframes, schema drift

    Use this whenever a notebook fails to load, shows blank charts,
    or behaves incorrectly when filters are applied.
    """
    # Get project + cells
    project_raw = await hex_get(f"/projects/{project_id}")
    cells_data = await hex_get("/cells", params={"projectId": project_id, "limit": 100})
    cells = cells_data.get("values", cells_data) if isinstance(cells_data, dict) else cells_data

    cell_snapshots = []
    for cell in cells:
        contents = cell.get("contents", {})
        source = ""
        for key in ("codeCell", "sqlCell", "markdownCell"):
            if key in contents:
                source = contents[key].get("source", "")
                break
        cell_snapshots.append({
            "id": cell.get("id"),
            "type": cell.get("cellType"),
            "label": cell.get("label") or cell.get("id"),
            "source_preview": source[:400],
        })

    # Get run details
    run_details = None
    if run_id:
        run_details = json.loads(await get_run_status(project_id, run_id))
    else:
        history = json.loads(await get_run_history(project_id, limit=3))
        if history:
            latest = history[0]
            if latest.get("run_id"):
                run_details = json.loads(
                    await get_run_status(project_id, latest["run_id"])
                )

    # Analyse
    issues = []
    recommendations = []

    if run_details:
        status = run_details.get("status")
        error = run_details.get("error") or ""
        errored_cells = run_details.get("cells_errored", [])

        if status == "ERRORED":
            issues.append(f"Run failed: {error[:500]}")

        if errored_cells:
            issues.append(f"Cells that errored: {errored_cells}")

        # Common pattern detection
        patterns = {
            "KeyError": "A DataFrame column referenced in code doesn't exist — check column names after filters reduce the dataset.",
            "Empty DataFrame": "Filter combination returns zero rows. Add a guard: `if df.empty: raise ValueError('No data for selected filters')`",
            "NoneType": "A variable is None — likely a Hex input widget returned no value or an upstream cell didn't produce output.",
            "AttributeError": "Method called on wrong type — often happens when a cell assumes a DataFrame but gets None.",
            "MemoryError": "Query returns too much data. Add LIMIT or date range guards in SQL.",
            "JSONDecodeError": "API response or data source returned malformed JSON.",
            "timeout": "Query exceeded time limit. Optimize SQL or add an index.",
            "permission": "Data connection permission issue — check connection credentials in workspace settings.",
            "SSL": "Network/SSL error connecting to data source. May be transient.",
        }
        for pattern, advice in patterns.items():
            if pattern.lower() in error.lower():
                recommendations.append(advice)

    return json.dumps({
        "project_id": project_id,
        "project_name": project_raw.get("title"),
        "cell_count": len(cells),
        "cells": cell_snapshots,
        "run_status": run_details,
        "issues_found": issues,
        "recommendations": recommendations,
        "edit_url": f"{HEX_APP_URL}/hex/{project_id}",
    }, indent=2)


@mcp.tool()
async def inspect_filter_behavior(
    project_id: str,
    filter_inputs: dict,
) -> str:
    """
    Trigger a run with specific filter input values to diagnose why
    a particular filter combination causes incorrect data or blank charts.

    Pass the filter widget names and values as filter_inputs dict.
    Example: {"date_range": "2024-01-01,2024-03-31", "region": "EMEA"}

    The tool runs the project, waits for completion, and surfaces
    any errors specific to those inputs.
    """
    result = json.loads(await run_and_wait(project_id, inputs=filter_inputs, timeout_seconds=180))
    return json.dumps({
        "filter_inputs_tested": filter_inputs,
        "run_result": result,
        "diagnosis": (
            "Run completed successfully with these filters."
            if result.get("status") == "COMPLETED"
            else f"Run failed with these filters. Error: {result.get('error')}. "
                 f"This confirms the filter combination is problematic — check cells_errored."
        ),
    }, indent=2)


# ─── Chart injection ──────────────────────────────────────────────────────────

@mcp.tool()
async def inject_plotly_chart(
    project_id: str,
    cell_id: str,
    chart_type: str,
    dataframe_var: str,
    x_col: str,
    y_col: str,
    color_col: str = None,
    title: str = "",
    height: int = 400,
    extra_kwargs: str = "",
    auto_run: bool = True,
) -> str:
    """
    Write a fully styled Plotly chart into a Hex Python cell.
    Design system (dark theme, color palette, typography) is applied automatically.

    chart_type: line | bar | scatter | area | histogram | box | heatmap | funnel | treemap
    dataframe_var: name of the DataFrame variable already defined in the notebook
    x_col / y_col: column names for axes
    color_col: optional column for series coloring
    extra_kwargs: any additional px.chart() keyword args as a string, e.g. 'barmode="group"'
    auto_run: if True, immediately triggers run_and_wait to push to app view
    """
    c = DS["colors"]
    layout = plotly_layout_defaults(title, height)

    # Map chart types to px functions
    px_map = {
        "line": "line",
        "bar": "bar",
        "scatter": "scatter",
        "area": "area",
        "histogram": "histogram",
        "box": "box",
        "heatmap": "density_heatmap",
        "funnel": "funnel",
        "treemap": "treemap",
    }
    px_func = px_map.get(chart_type, "line")

    color_arg = f', color="{color_col}"' if color_col else ""
    y_arg = f', y="{y_col}"' if chart_type not in ("histogram", "treemap") else ""
    x_arg = f', x="{x_col}"' if chart_type != "treemap" else f', path=["{x_col}"]'
    extra = f", {extra_kwargs}" if extra_kwargs else ""

    chart_sequence_str = json.dumps(c["chart_sequence"])

    source = f"""import plotly.express as px
import plotly.graph_objects as go

_CHART_COLORS = {chart_sequence_str}
_LAYOUT = {json.dumps(layout, indent=4)}

fig = px.{px_func}(
    {dataframe_var}{x_arg}{y_arg}{color_arg},
    color_discrete_sequence=_CHART_COLORS{extra}
)

fig.update_layout(**_LAYOUT)

# Additional trace styling
fig.update_traces(
    marker_line_width=0,
    opacity=0.88,
)

fig.show()
"""
    await update_cell_source(project_id, cell_id, source)

    if auto_run:
        run_result = json.loads(await run_and_wait(project_id))
        return json.dumps({"injected": True, "chart_type": chart_type, "run": run_result})

    return json.dumps({"injected": True, "chart_type": chart_type, "auto_run": False})


@mcp.tool()
async def inject_pydeck_map(
    project_id: str,
    cell_id: str,
    dataframe_var: str,
    lat_col: str,
    lon_col: str,
    layer_type: str = "ScatterplotLayer",
    color_col: str = None,
    elevation_col: str = None,
    radius: int = 200,
    title: str = "",
    auto_run: bool = True,
) -> str:
    """
    Write a styled PyDeck map into a Hex Python cell using the dark map style.

    layer_type: ScatterplotLayer | HexagonLayer | H3HexagonLayer |
                ColumnLayer | ArcLayer | PathLayer | GeoJsonLayer
    color_col: column with pre-computed [R, G, B] or [R, G, B, A] values.
               If omitted, uses accent color.
    elevation_col: column for 3D height (ColumnLayer / HexagonLayer)
    auto_run: if True, triggers run_and_wait to push to app view
    """
    c = DS["colors"]
    map_style = DS["map_style"]

    # Default color: accent indigo
    default_color = [99, 102, 241, 200]

    color_expr = f"[{dataframe_var}['{color_col}'] for _ in range(len({dataframe_var}))]" \
        if color_col else str(default_color)

    elevation_expr = f'elevation_scale=50, get_elevation="{elevation_col}",' \
        if elevation_col else ""

    layer_configs = {
        "ScatterplotLayer": f"""pdk.Layer(
    "ScatterplotLayer",
    data={dataframe_var},
    get_position=["[lon_col]", "[lat_col]"],
    get_color={default_color},
    get_radius={radius},
    pickable=True,
    opacity=0.85,
    stroked=False,
)""".replace("[lon_col]", lon_col).replace("[lat_col]", lat_col),

        "HexagonLayer": f"""pdk.Layer(
    "HexagonLayer",
    data={dataframe_var},
    get_position=["[lon_col]", "[lat_col]"],
    radius={radius},
    {elevation_expr}
    elevation_range=[0, 500],
    pickable=True,
    extruded=True,
    colorRange=[
        [99, 102, 241, 80],
        [99, 102, 241, 140],
        [99, 102, 241, 200],
        [34, 211, 238, 200],
        [34, 211, 238, 240],
        [240, 240, 245, 255],
    ],
)""".replace("[lon_col]", lon_col).replace("[lat_col]", lat_col),

        "ColumnLayer": f"""pdk.Layer(
    "ColumnLayer",
    data={dataframe_var},
    get_position=["[lon_col]", "[lat_col]"],
    get_elevation="{elevation_col or 'value'}",
    elevation_scale=10,
    radius={radius},
    get_fill_color={default_color},
    pickable=True,
    extruded=True,
    auto_highlight=True,
)""".replace("[lon_col]", lon_col).replace("[lat_col]", lat_col),
    }

    layer_code = layer_configs.get(
        layer_type,
        layer_configs["ScatterplotLayer"]
    )

    source = f"""import pydeck as pdk
import pandas as pd

# ── Map config ────────────────────────────────────────────
_MAP_STYLE = "{map_style}"
_DEFAULT_COLOR = {default_color}

# ── Compute view state from data ──────────────────────────
_center_lat = {dataframe_var}["{lat_col}"].mean()
_center_lon = {dataframe_var}["{lon_col}"].mean()

view_state = pdk.ViewState(
    latitude=_center_lat,
    longitude=_center_lon,
    zoom=10,
    pitch=45,
    bearing=0,
)

# ── Layer ─────────────────────────────────────────────────
layer = {layer_code}

# ── Render ────────────────────────────────────────────────
deck = pdk.Deck(
    layers=[layer],
    initial_view_state=view_state,
    map_style=_MAP_STYLE,
    tooltip={
        "html": "<b>{" + lat_col + "}</b>, {" + lon_col + "}<br/>",
        "style": {
            "backgroundColor": "#16161A",
            "color": "#F0F0F5",
            "fontFamily": "Inter, system-ui",
            "fontSize": "12px",
            "border": "1px solid #6366F1",
            "padding": "8px 12px",
        },
    },
)

deck
"""
    await update_cell_source(project_id, cell_id, source)

    if auto_run:
        run_result = json.loads(await run_and_wait(project_id))
        return json.dumps({"injected": True, "layer_type": layer_type, "run": run_result})

    return json.dumps({"injected": True, "layer_type": layer_type, "auto_run": False})


@mcp.tool()
async def inject_html_component(
    project_id: str,
    cell_id: str,
    component_type: str,
    props: dict,
    auto_run: bool = True,
) -> str:
    """
    Write a styled HTML component into a Hex HTML cell.
    These render in the published app with no Python needed.

    component_type:
      kpi_row        — row of metric cards (props: metrics=[{label, value, delta, delta_type}])
      section_header — section title + subtitle (props: title, subtitle)
      data_table     — styled HTML table (props: dataframe_var, max_rows)
      alert_banner   — info/warning/error banner (props: message, level)
      divider        — styled horizontal rule (props: label)
    """
    c = DS["colors"]
    font = DS["font"]

    base_style = f"""
    <style>
      * {{ box-sizing: border-box; margin: 0; padding: 0; }}
      body, .hex-component {{
        background: transparent;
        font-family: {font};
        color: {c['text_primary']};
      }}
    </style>
    """

    if component_type == "kpi_row":
        metrics = props.get("metrics", [])
        cards_html = ""
        for m in metrics:
            delta = m.get("delta", "")
            dtype = m.get("delta_type", "neutral")  # positive | negative | neutral
            delta_color = {
                "positive": c["positive"],
                "negative": c["negative"],
                "neutral": c["text_muted"],
            }.get(dtype, c["text_muted"])

            delta_html = f'<span style="color:{delta_color};font-size:12px;font-weight:500;">{delta}</span>' if delta else ""

            cards_html += f"""
            <div style="
                background:{c['surface']};
                border:1px solid {c['border']};
                border-radius:8px;
                padding:16px 20px;
                flex:1;
                min-width:140px;
            ">
                <div style="color:{c['text_muted']};font-size:11px;font-weight:500;
                            text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">
                    {m.get('label', '')}
                </div>
                <div style="font-size:24px;font-weight:600;color:{c['text_primary']};
                            letter-spacing:-0.02em;margin-bottom:4px;">
                    {m.get('value', '—')}
                </div>
                {delta_html}
            </div>"""

        html = f"""{base_style}
        <div class="hex-component" style="display:flex;gap:12px;flex-wrap:wrap;padding:4px 0;">
            {cards_html}
        </div>"""

    elif component_type == "section_header":
        html = f"""{base_style}
        <div class="hex-component" style="padding:8px 0 4px;">
            <div style="font-size:17px;font-weight:600;color:{c['text_primary']};
                        letter-spacing:-0.02em;">{props.get('title', '')}</div>
            <div style="font-size:13px;color:{c['text_muted']};margin-top:4px;">
                {props.get('subtitle', '')}</div>
            <div style="height:1px;background:{c['border']};margin-top:12px;"></div>
        </div>"""

    elif component_type == "alert_banner":
        level = props.get("level", "info")
        level_colors = {
            "info": c["accent_2"],
            "warning": c["warning"],
            "error": c["negative"],
        }
        lvl_color = level_colors.get(level, c["accent_2"])
        html = f"""{base_style}
        <div class="hex-component" style="
            background:{c['surface']};
            border-left:3px solid {lvl_color};
            border-radius:4px;
            padding:12px 16px;
            font-size:13px;
            color:{c['text_primary']};
        ">
            {props.get('message', '')}
        </div>"""

    elif component_type == "divider":
        label = props.get("label", "")
        html = f"""{base_style}
        <div class="hex-component" style="display:flex;align-items:center;gap:12px;padding:8px 0;">
            <div style="flex:1;height:1px;background:{c['border']};"></div>
            <span style="font-size:11px;font-weight:500;color:{c['text_muted']};
                         text-transform:uppercase;letter-spacing:0.06em;">{label}</span>
            <div style="flex:1;height:1px;background:{c['border']};"></div>
        </div>"""

    else:
        html = f"<p style='color:{c['negative']};'>Unknown component_type: {component_type}</p>"

    await update_cell_source(project_id, cell_id, html.strip())

    if auto_run:
        run_result = json.loads(await run_and_wait(project_id))
        return json.dumps({"injected": True, "component_type": component_type, "run": run_result})

    return json.dumps({"injected": True, "component_type": component_type, "auto_run": False})


# ─── Design system helpers ────────────────────────────────────────────────────

@mcp.tool()
async def get_design_system() -> str:
    """
    Return the active design system tokens (colors, fonts, chart defaults).
    Use this to stay consistent when writing custom chart code.
    """
    return json.dumps({
        "design_system": DS,
        "plotly_layout_example": plotly_layout_defaults("Chart Title", 400),
        "usage_notes": {
            "chart_sequence": "Use DS['colors']['chart_sequence'] for multi-series color order.",
            "surface": "Use 'surface' for chart paper_bgcolor and plot_bgcolor.",
            "border": "Use 'border' for gridlines and axis lines.",
            "text_muted": "Use 'text_muted' for axis tick labels and legend text.",
            "text_primary": "Use 'text_primary' for chart titles and axis titles.",
        },
    }, indent=2)


@mcp.tool()
async def apply_workspace_palette(project_id: str) -> str:
    """
    Apply the design system color palette to the Hex workspace custom styling.
    This sets the active chart color palette for all Chart cells in the workspace.
    Requires admin permissions.
    """
    palette_colors = DS["colors"]["chart_sequence"]
    try:
        result = await hex_patch("/workspace/styling", {
            "colorPalette": palette_colors,
        })
        return json.dumps({"success": True, "palette_applied": palette_colors})
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
            "note": "Workspace styling may require admin role. "
                    "You can also set this manually in Settings > Styling.",
            "palette_to_apply": palette_colors,
        })


if __name__ == "__main__":
    mcp.run()
