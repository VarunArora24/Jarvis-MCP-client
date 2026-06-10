import sys
import subprocess
from pathlib import Path
from typing import Dict, Any
from jarvis.registry import registry
from jarvis.utils.security import validate_path
from jarvis.utils.logging import logger

@registry.register(name="execute_python_code", dangerous=True)
def execute_python_code(code: str) -> Dict[str, Any]:
    """
    Run arbitrary Python 3 code locally and capture stdout/stderr.
    The code runs in a subprocess using the active virtualenv's Python binary.

    Args:
        code: The Python source code to execute.
    """
    logger.info("Tool call: execute_python_code")
    
    # Define temp file path in current working directory (which is whitelisted)
    temp_file = Path.cwd() / "_jarvis_temp_exec.py"
    
    # Validate the path (standard safety pass)
    safe_temp_file = validate_path(temp_file)
    
    try:
        # Write code to temp script
        safe_temp_file.write_text(code, encoding="utf-8")
        
        # Run python in subprocess, setting a 30s timeout
        result = subprocess.run(
            [sys.executable, str(safe_temp_file)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode
        }
        
    except subprocess.TimeoutExpired as e:
        return {
            "stdout": e.stdout or "",
            "stderr": f"Execution timed out (30s limit). {e.stderr or ''}",
            "return_code": -1
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": f"Error running Python code: {str(e)}",
            "return_code": -1
        }
    finally:
        # Always clean up the temp file
        if safe_temp_file.exists():
            try:
                safe_temp_file.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete temporary execution file: {e}")
                pass
