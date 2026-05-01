"""Typed tool registry and tool declarations."""

from sandboxed_agent_eval_harness.tools.execution import (
    FixtureToolExecutor,
    ToolExecutionError,
)
from sandboxed_agent_eval_harness.tools.registry import (
    DuplicateToolError,
    ToolRegistry,
    ToolRegistryError,
    UnknownToolError,
    default_tool_registry,
    default_tool_specs,
)

__all__ = [
    "DuplicateToolError",
    "FixtureToolExecutor",
    "ToolRegistry",
    "ToolRegistryError",
    "ToolExecutionError",
    "UnknownToolError",
    "default_tool_registry",
    "default_tool_specs",
]
