"""LangChain tool adapters for fixture-backed harness tools."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Optional

from sandboxed_agent_eval_harness.integrations.common import require_optional_dependency
from sandboxed_agent_eval_harness.sandbox import FileSystemSandbox
from sandboxed_agent_eval_harness.schemas import JsonDict
from sandboxed_agent_eval_harness.tools import FixtureToolExecutor, ToolRegistry, default_tool_registry
from sandboxed_agent_eval_harness.tracing import TraceLogger


class LangChainToolAdapter:
    """Expose harness tools as LangChain-compatible callables without changing harness semantics."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        *,
        executor: Optional[FixtureToolExecutor] = None,
        logger: Optional[TraceLogger] = None,
    ) -> None:
        self.registry = registry or default_tool_registry()
        self.executor = executor or FixtureToolExecutor(self.registry)
        self.logger = logger

    def tool_descriptors(self, tool_names: Optional[Iterable[str]] = None) -> list[JsonDict]:
        names = list(tool_names or self.registry.names())
        descriptors: list[JsonDict] = []
        for tool_name in names:
            tool = self.registry.get(tool_name)
            descriptors.append(
                {
                    "tool_name": tool.tool_name,
                    "langchain_name": self.langchain_tool_name(tool.tool_name),
                    "description": self._description_for(tool.tool_name),
                    "input_schema": dict(tool.input_schema),
                    "output_schema": dict(tool.output_schema),
                    "permissions": list(tool.permissions),
                    "side_effects": list(tool.side_effects),
                    "state_mutation": dict(tool.state_mutation),
                    "failure_modes": list(tool.failure_modes),
                }
            )
        return descriptors

    def invoke_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        sandbox: FileSystemSandbox,
    ) -> JsonDict:
        validated_arguments = self.registry.validate_input(tool_name, arguments)
        if self.logger is not None:
            self.logger.log_tool_call(
                tool_name,
                validated_arguments,
                metadata={
                    "integration": "langchain",
                    "langchain_tool_name": self.langchain_tool_name(tool_name),
                },
            )
        result = self.executor.execute(tool_name, validated_arguments, sandbox)
        if self.logger is not None:
            self.logger.log_tool_result(
                tool_name,
                result,
                metadata={
                    "integration": "langchain",
                    "langchain_tool_name": self.langchain_tool_name(tool_name),
                },
            )
        return result

    def to_langchain_tools(
        self,
        *,
        sandbox: FileSystemSandbox,
        tool_names: Optional[Iterable[str]] = None,
        structured_tool_factory: Optional[Callable[..., Any]] = None,
    ) -> list[Any]:
        """Build LangChain StructuredTool objects when LangChain is installed.

        Tests and default CI can inject `structured_tool_factory`, so the default path never
        imports LangChain unless a caller intentionally asks for native objects.
        """

        factory = structured_tool_factory
        if factory is None:
            tools_module = require_optional_dependency("langchain_core.tools")
            factory = tools_module.StructuredTool.from_function

        langchain_tools = []
        for descriptor in self.tool_descriptors(tool_names):
            tool_name = descriptor["tool_name"]

            def _make_run(harness_tool_name: str) -> Callable[..., JsonDict]:
                def _run(**kwargs: Any) -> JsonDict:
                    return self.invoke_tool(harness_tool_name, kwargs, sandbox=sandbox)

                return _run

            langchain_tools.append(
                factory(
                    func=_make_run(tool_name),
                    name=descriptor["langchain_name"],
                    description=descriptor["description"],
                    args_schema=self._args_schema_model(descriptor["langchain_name"], descriptor["input_schema"]),
                )
            )
        return langchain_tools

    @staticmethod
    def langchain_tool_name(tool_name: str) -> str:
        return tool_name.replace(".", "__")

    @staticmethod
    def _description_for(tool_name: str) -> str:
        return f"Fixture-backed harness tool `{tool_name}`; outputs remain validated by deterministic harness validators."

    @staticmethod
    def _args_schema_model(model_name: str, input_schema: Mapping[str, Any]) -> Any:
        pydantic_module = require_optional_dependency("pydantic")
        create_model = pydantic_module.create_model
        properties = input_schema.get("properties", {})
        required = set(input_schema.get("required", []))
        fields = {}
        for name, schema in properties.items():
            annotation = _python_type_for_json_schema(schema)
            fields[name] = (annotation, ... if name in required else None)
        return create_model(f"{model_name.title().replace('_', '')}Args", **fields)


def _python_type_for_json_schema(schema: Mapping[str, Any]) -> type[Any]:
    schema_type = schema.get("type")
    if schema_type == "string":
        return str
    if schema_type == "integer":
        return int
    if schema_type == "number":
        return float
    if schema_type == "boolean":
        return bool
    if schema_type == "array":
        return list
    if schema_type == "object":
        return dict
    return object
