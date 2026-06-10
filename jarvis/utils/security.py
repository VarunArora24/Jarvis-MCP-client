import sys
from pathlib import Path
from typing import Union
from rich.console import Console
from jarvis.config import settings
from jarvis.utils.logging import logger

# Create a console that writes to stderr so it doesn't corrupt stdout (which is used by MCP stdio)
error_console = Console(stderr=True)

class SecurityError(PermissionError):
    """Exception raised when a tool execution violates security constraints."""
    pass

def validate_path(path: Union[str, Path]) -> Path:
    """
    Validates a file path against whitelist and blacklist constraints.
    Returns the resolved absolute path if valid, raises SecurityError otherwise.
    """
    try:
        resolved_path = Path(path).resolve()
    except Exception as e:
        raise SecurityError(f"Failed to resolve path '{path}': {e}")

    # Check blacklist first
    for blacklist_dir in settings.blacklist_paths:
        try:
            # Check if path is equal to or is a child of the blacklist directory
            if resolved_path == blacklist_dir or blacklist_dir in resolved_path.parents:
                logger.warning(f"Security Block: Path '{resolved_path}' is inside blacklisted directory '{blacklist_dir}'")
                raise SecurityError(
                    f"Access denied: Path '{resolved_path}' is inside blacklisted directory '{blacklist_dir}'"
                )
        except ValueError:
            # parents check might throw ValueError on different Windows drives (e.g., C: and D:)
            continue

    # Check whitelist
    is_whitelisted = False
    for whitelist_dir in settings.whitelist_paths:
        try:
            if resolved_path == whitelist_dir or whitelist_dir in resolved_path.parents:
                is_whitelisted = True
                break
        except ValueError:
            continue

    if not is_whitelisted:
        logger.warning(f"Security Block: Path '{resolved_path}' is not in any whitelisted directory.")
        raise SecurityError(
            f"Access denied: Path '{resolved_path}' is outside whitelisted directories. "
            f"Allowed directories: {[str(p) for p in settings.whitelist_paths]}"
        )

    return resolved_path

def confirm_action(action_description: str, is_interactive: bool = True) -> bool:
    """
    Prompts the user for confirmation of a dangerous action.
    If in non-interactive mode (or MCP mode), fails the action if settings require confirmation.
    """
    if not settings.confirmation_required:
        logger.info(f"Auto-approved dangerous action (confirmation disabled): {action_description}")
        return True

    if not is_interactive:
        logger.warning(f"Action blocked: confirmation required but running in non-interactive/MCP mode: {action_description}")
        raise SecurityError(
            f"Action blocked: Confirmation required for dangerous action '{action_description}', "
            "but Jarvis is running in non-interactive or MCP server mode."
        )

    # Prompt user on stderr
    error_console.print(f"\n[bold yellow]⚠️  SECURITY WARNING:[/bold yellow] Jarvis wants to perform a dangerous action:")
    error_console.print(f"  [cyan]{action_description}[/cyan]")
    
    try:
        # We explicitly use sys.__stdin__ or input to read from the console.
        # Print confirmation request to stderr
        error_console.print("[bold green]Do you want to allow this action? (y/N): [/bold green]", end="")
        sys.stderr.flush()
        # Read from stdin
        response = sys.stdin.readline().strip().lower()
        if response in ("y", "yes"):
            logger.info(f"User approved action: {action_description}")
            return True
        else:
            logger.warning(f"User denied action: {action_description}")
            return False
    except Exception as e:
        logger.error(f"Error during user confirmation: {e}")
        return False
