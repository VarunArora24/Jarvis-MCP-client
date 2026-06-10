import inspect
from mcp.server.fastmcp import FastMCP
from jarvis.registry import registry
from jarvis.utils.logging import logger
from jarvis.utils.security import SecurityError, confirm_action

# Initialize the FastMCP server
mcp_server = FastMCP("Jarvis")

# Force-import tools package to execute decorator registration
import jarvis.tools  # noqa: F401

def create_mcp_wrapper(tool_item):
    """
    Creates a wrapper around a registry tool to execute it within the Jarvis security boundaries.
    In MCP server mode, dangerous tools are run non-interactively (is_interactive=False),
    blocking accidental execution of destructive operations unless confirmation is globally disabled.
    """
    func = tool_item.func
    
    def mcp_tool_wrapper(*args, **kwargs):
        logger.info(f"MCP Server call: {tool_item.name} with args={kwargs}")
        
        try:
            # Enforce path validations for file tools inside the tool wrapper if applicable
            # Since the tools themselves call validate_path, path security is automatically enforced!
            
            # Enforce dangerous tool confirmation (non-interactive mode)
            if tool_item.dangerous:
                action_desc = f"MCP tool execution of '{tool_item.name}' with arguments: {kwargs}"
                # confirm_action will raise SecurityError if is_interactive=False
                confirm_action(action_desc, is_interactive=False)
                
            # Execute the tool
            result = tool_item.run(*args, **kwargs)
            return result
        except SecurityError as e:
            logger.warning(f"MCP Security Block for tool '{tool_item.name}': {e}")
            return f"Security Error: {str(e)}"
        except Exception as e:
            logger.error(f"MCP Exception executing tool '{tool_item.name}': {e}", exc_info=True)
            return f"Error: {type(e).__name__} - {str(e)}"

    # Copy function metadata so FastMCP reflection extracts schemas correctly
    mcp_tool_wrapper.__name__ = func.__name__
    mcp_tool_wrapper.__doc__ = func.__doc__
    mcp_tool_wrapper.__signature__ = inspect.signature(func)
    
    return mcp_tool_wrapper

# Dynamically register all tools from the Tool Registry to FastMCP
for name, tool in registry.tools.items():
    wrapped_func = create_mcp_wrapper(tool)
    mcp_server.tool(name=name)(wrapped_func)
    logger.debug(f"Exposed tool '{name}' to MCP Server interface.")

def run_mcp_server(transport: str = "stdio") -> None:
    """Launches the FastMCP server on the specified transport (stdio or sse)."""
    logger.info(f"Starting Jarvis MCP Server on transport: {transport}")
    if transport == "sse":
        # FastMCP uses sse transport configuration
        mcp_server.run(transport="sse")
    else:
        # Default to stdio transport (perfect for desktop clients)
        mcp_server.run(transport="stdio")
