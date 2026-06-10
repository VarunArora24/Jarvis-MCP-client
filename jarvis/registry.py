import inspect
import re
from typing import Callable, Any, Dict, List, get_type_hints
from pydantic import BaseModel
from jarvis.utils.logging import logger

class Tool(BaseModel):
    name: str
    description: str
    func: Callable[..., Any] = None
    dangerous: bool = False
    parameters_schema: Dict[str, Any]

    model_config = {"arbitrary_types_allowed": True}

    def run(self, *args, **kwargs) -> Any:
        """Executes the wrapped tool function."""
        if not self.func:
            raise ValueError(f"Tool '{self.name}' has no execution function defined.")
        return self.func(*args, **kwargs)

    def get_gemini_schema(self) -> Dict[str, Any]:
        """Returns the schema formatted for Gemini (uppercase types, e.g., STRING)."""
        def format_type(t: Dict[str, Any]) -> Dict[str, Any]:
            new_t = {}
            for k, v in t.items():
                if k == "type" and isinstance(v, str):
                    new_t[k] = v.upper()
                    # Fix integer to INTEGER, boolean to BOOLEAN, etc.
                    if new_t[k] == "INT":
                        new_t[k] = "INTEGER"
                    elif new_t[k] == "FLOAT":
                        new_t[k] = "NUMBER"
                    elif new_t[k] == "STR":
                        new_t[k] = "STRING"
                    elif new_t[k] == "BOOL":
                        new_t[k] = "BOOLEAN"
                    elif new_t[k] == "DICT":
                        new_t[k] = "OBJECT"
                    elif new_t[k] == "LIST":
                        new_t[k] = "ARRAY"
                elif k == "properties" and isinstance(v, dict):
                    new_t[k] = {pk: format_type(pv) for pk, pv in v.items()}
                elif k == "items" and isinstance(v, dict):
                    new_t[k] = format_type(v)
                else:
                    new_t[k] = v
            return new_t
            
        schema = format_type(self.parameters_schema)
        return {
            "name": self.name,
            "description": self.description,
            "parameters": schema
        }

    def get_mcp_schema(self) -> Dict[str, Any]:
        """Returns the schema formatted for MCP (lowercase types, e.g., string)."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.parameters_schema
        }

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Tool] = {}

    def register(self, name: str = None, dangerous: bool = False) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """
        Decorator to register a Python function as an agent tool.
        Extracts type annotations and docstrings to generate JSON schemas automatically.
        """
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            tool_name = name or func.__name__
            doc = func.__doc__ or ""
            
            # Clean docstring to extract description and parameter descriptions
            lines = [line.strip() for line in doc.split("\n")]
            description = ""
            param_docs = {}
            
            # Simple docstring parsing:
            # First non-empty lines are description until "Args:" or similar header
            in_args = False
            desc_lines = []
            for line in lines:
                if not line:
                    continue
                if line.lower().startswith(("args:", "parameters:", "inputs:")):
                    in_args = True
                    continue
                if in_args:
                    # Parse parameter: "param_name: description" or "param_name (type): description"
                    match = re.match(r"^([\w_]+)\s*(?:\([^)]+\))?\s*:\s*(.+)$", line)
                    if match:
                        param_name, param_desc = match.groups()
                        param_docs[param_name] = param_desc.strip()
                else:
                    desc_lines.append(line)
            
            description = " ".join(desc_lines).strip() or f"Execute {tool_name}."
            
            # Generate JSON Schema
            schema = self._generate_schema(func, param_docs)
            
            tool = Tool(
                name=tool_name,
                description=description,
                func=func,
                dangerous=dangerous,
                parameters_schema=schema
            )
            
            self.tools[tool_name] = tool
            logger.debug(f"Registered tool: {tool_name} (dangerous={dangerous})")
            return func
            
        return decorator

    def _generate_schema(self, func: Callable[..., Any], param_docs: Dict[str, str]) -> Dict[str, Any]:
        """Inspects the function signature and generates standard JSON Schema."""
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)
        
        properties = {}
        required = []
        
        for name, param in sig.parameters.items():
            if name == "self":
                continue
                
            # Determine standard python types
            hint = type_hints.get(name, str)
            json_type = "string"
            items_schema = None
            
            # Map Python types to lower-case JSON Schema types
            if hint == int:
                json_type = "integer"
            elif hint == float:
                json_type = "number"
            elif hint == bool:
                json_type = "boolean"
            elif hint == list or getattr(hint, "__origin__", None) == list:
                json_type = "array"
                # Handle List[str] type logic simply
                args = getattr(hint, "__args__", None)
                if args:
                    item_type = args[0]
                    if item_type == int:
                        items_schema = {"type": "integer"}
                    elif item_type == float:
                        items_schema = {"type": "number"}
                    elif item_type == bool:
                        items_schema = {"type": "boolean"}
                    else:
                        items_schema = {"type": "string"}
                else:
                    items_schema = {"type": "string"}
            elif hint == dict or getattr(hint, "__origin__", None) == dict:
                json_type = "object"
                
            param_def = {"type": json_type}
            
            if items_schema:
                param_def["items"] = items_schema
                
            # Add description if parsed from docstring
            if name in param_docs:
                param_def["description"] = param_docs[name]
                
            # Check if parameter has no default value
            if param.default == inspect.Parameter.empty:
                required.append(name)
                
            properties[name] = param_def
            
        return {
            "type": "object",
            "properties": properties,
            "required": required
        }

    def get_gemini_tools(self) -> List[Dict[str, Any]]:
        """Returns tool definitions formatted for Gemini's client config."""
        return [tool.get_gemini_schema() for tool in self.tools.values()]

    def get_mcp_tools(self) -> List[Dict[str, Any]]:
        """Returns tool definitions formatted for MCP list response."""
        return [tool.get_mcp_schema() for tool in self.tools.values()]

# Global registry instance
registry = ToolRegistry()
