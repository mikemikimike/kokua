"""The skills toolset: AIMU's authoring tools, guarded against toolset names and followed by a registry refresh."""

from __future__ import annotations

from aimu.skills import make_skill_authoring_tool, make_skill_script_tool, make_skill_update_tool

from kokua.config import MCPServerConfig
from kokua.config.schema import AgentConfig
from kokua.core.agents import build_registry
from kokua.registry.context import LiveState, ToolsetContext
from kokua.registry.registry import ToolsetError
from kokua.toolsets.skills import TOOLSET
from tests.channels import _config
from tests.helpers import allow_all_gates


def _tools(config, **state_fields) -> dict:
    state = LiveState(gate_for=allow_all_gates, config=config, registry=build_registry(config), **state_fields)
    tools = TOOLSET.build(ToolsetContext(state=state, agent=None, agent_name="assistant"))
    return {fn.__name__: fn for fn in tools}


def _skills_config(tmp_path, **overrides):
    agents = {"assistant": AgentConfig(available=["skills", "web"])}
    return _config(tmp_path, agents=agents, default_confirm=[], default_review=[], **overrides)


def test_the_wrapped_tools_keep_aimus_names_and_schemas(tmp_path):
    config = _skills_config(tmp_path)
    originals = [
        make_skill_authoring_tool(None, config.skills_dir),
        make_skill_update_tool(None, config.skills_dir),
        make_skill_script_tool(None, None, config.skills_dir),
    ]

    tools = _tools(config)

    assert list(tools) == ["author_skill", "update_skill", "add_skill_script"]
    for original in originals:
        assert tools[original.__name__].__tool_spec__ == original.__tool_spec__


async def test_author_skill_refuses_a_toolset_name_and_writes_nothing(tmp_path):
    server = MCPServerConfig(url="https://files.example/mcp", name="files")
    config = _skills_config(tmp_path, mcp_servers=[server])
    author_skill = _tools(config)["author_skill"]

    for name in ("web", "files"):  # a Kokua toolset, a configured MCP server
        result = await author_skill(name=name, description="d", body="b")
        assert result.startswith(f"Nothing was written: {name!r} is already a toolset name")
        assert not (config.skills_dir / name).exists()


async def test_author_skill_refuses_a_reserved_name_and_writes_nothing(tmp_path):
    config = _skills_config(tmp_path)
    author_skill = _tools(config)["author_skill"]

    for name in ("core", "all"):
        result = await author_skill(name=name, description="d", body="b")
        assert result.startswith(f"Nothing was written: {name!r} is already a toolset name (reserved)")
        assert not (config.skills_dir / name).exists()


async def test_each_tool_refreshes_skills_after_it_writes(tmp_path):
    config = _skills_config(tmp_path)
    refreshed = []
    tools = _tools(config, refresh_skills=lambda: refreshed.append(True))

    result = await tools["author_skill"](name="weekly-digest", description="Digest the week.", body="Do it.")
    assert result.startswith("Created skill 'weekly-digest'")
    await tools["update_skill"](skill_name="weekly-digest", body="Do it better.")

    assert refreshed == [True, True]


async def test_a_refresh_collision_reaches_the_model_instead_of_raising(tmp_path):
    def colliding():
        raise ToolsetError("toolset name 'x' is claimed by two providers.")

    tools = _tools(_skills_config(tmp_path), refresh_skills=colliding)

    result = await tools["author_skill"](name="weekly-digest", description="Digest the week.", body="Do it.")

    assert result.startswith("Created skill 'weekly-digest'")
    assert "toolset name 'x' is claimed by two providers." in result
