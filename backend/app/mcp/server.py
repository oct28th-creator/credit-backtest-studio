"""MCP stdio server over app.agent.tools.

Run it:
    python -m app.mcp.server

Register it with Claude Code (from the repo root):
    claude mcp add backtest -- backend/venv/bin/python -m app.mcp.server

Design notes
------------
* One MCP tool per registry entry — the registry is the contract, and it is
  already JSON-Schema shaped. Duplicating the definitions here would create
  two sources of truth that drift.
* Every compute-spending call is charged to one session for the whole MCP
  connection, so an external agent cannot spend more than an in-app one. The
  budget is generous but finite, and the error says so plainly.
* Results are returned as compact JSON text. The tools already strip chart
  payloads down to decision-relevant numbers (see tools._compact), which is
  what makes them reasonable to hand a model.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

# The API's package root, so `python -m app.mcp.server` works from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.agent import budget as budget_mod  # noqa: E402
from app.agent import tools as agent_tools  # noqa: E402
from app.core.runs import ConfigInvalid, RunNotFound  # noqa: E402
from app.db.engine import init_db  # noqa: E402

logger = logging.getLogger("backtest.mcp")

SERVER_NAME = "backtest-studio"
# One connection, one budget. Wider than a UI session because an external
# agent is expected to sweep, but still bounded.
CONNECTION_BUDGET = budget_mod.Budget(max_experiments=40, max_llm_calls=0,
                                      max_wall_seconds=3600)

_INSTRUCTIONS = """\
Credit strategy backtesting platform.

Every run is immutable and content-addressed: the same manifest_sha always
means the same numbers, and a variation is a new run linked by lineage.

Before spending compute, call search_experiments — an identical experiment may
already exist, and submit_experiment reuses it for free when the manifest
matches.

check_guardrails is not advisory. A blocking finding (disparate impact under
the four-fifths rule, an approved book under 500 accounts, a protected
attribute used as a model input, a reject-inference method whose error exceeds
the effect it reports) means the result may not be presented as a candidate
strategy, whatever the metrics say.

A single run cannot separate a strategy difference from a sampling difference.
Call replicate_across_seeds before claiming one strategy beats another; if the
ranking flips across seeds, the difference is noise.

list_environments tells you what the assumed world may NOT be used to claim.
Do not draw conclusions outside those bounds.
"""


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


async def serve() -> None:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    import mcp.types as types

    init_db()
    session = budget_mod.create(goal="mcp connection", budget=CONNECTION_BUDGET)
    server: Server = Server(SERVER_NAME, instructions=_INSTRUCTIONS)

    @server.list_tools()
    async def list_tools() -> list:
        out = []
        for spec in agent_tools.describe():
            description = spec["description"]
            if spec["spends_compute"]:
                description += (
                    f" [spends compute — charged to this connection's budget of "
                    f"{CONNECTION_BUDGET.max_experiments} experiments]"
                )
            out.append(types.Tool(
                name=spec["name"],
                description=description,
                inputSchema=spec["input_schema"],
            ))
        return out

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list:
        try:
            result = await agent_tools.call(name, arguments or {}, session=session)
        except budget_mod.BudgetExceeded as exc:
            payload = {"error": "budget_exceeded", "detail": str(exc),
                       "session": session.to_dict()}
        except (agent_tools.ToolError, ConfigInvalid) as exc:
            payload = {"error": "invalid_request", "detail": str(exc)}
        except RunNotFound as exc:
            payload = {"error": "not_found", "detail": str(exc)}
        except Exception as exc:  # noqa: BLE001 — report, never kill the connection
            logger.exception("mcp tool %s failed", name)
            payload = {"error": type(exc).__name__, "detail": str(exc)}
        else:
            payload = result
        return [types.TextContent(type="text", text=_json(payload))]

    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("%s MCP server ready — %d tools, session %s",
                SERVER_NAME, len(agent_tools.REGISTRY), session.session_id)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream,
                         server.create_initialization_options())


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
