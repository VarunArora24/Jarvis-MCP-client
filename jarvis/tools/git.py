import subprocess
from pathlib import Path
from typing import Dict, Any
from jarvis.registry import registry
from jarvis.utils.security import validate_path
from jarvis.utils.logging import logger

def _run_git_command(args: list[str], repo_path: Path) -> Dict[str, Any]:
    """Helper to run a git CLI subprocess in a specific repository directory."""
    try:
        # Check if git executable exists by running a quick version query first
        subprocess.run(["git", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {
            "stdout": "",
            "stderr": "Git is not installed or not found in system PATH.",
            "return_code": -1
        }

    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=30
        )
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "return_code": result.returncode
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": f"Failed to execute git command: {str(e)}",
            "return_code": -1
        }

@registry.register(name="git_status")
def git_status(repo_path: str = ".") -> str:
    """
    Get the current status of a git repository (working directory and staging area).

    Args:
        repo_path: The directory path of the git repository. Defaults to the current workspace root.
    """
    logger.info(f"Tool call: git_status(repo_path='{repo_path}')")
    safe_path = validate_path(repo_path)
    
    res = _run_git_command(["status"], safe_path)
    if res["return_code"] != 0:
        return f"Error running git status:\nStdout: {res['stdout']}\nStderr: {res['stderr']}"
    return res["stdout"] or "No status details returned."

@registry.register(name="git_log")
def git_log(repo_path: str = ".", limit: int = 10) -> str:
    """
    Get the git commit log.

    Args:
        repo_path: The directory path of the git repository. Defaults to the current workspace root.
        limit: Max number of commit entries to display. Defaults to 10.
    """
    logger.info(f"Tool call: git_log(repo_path='{repo_path}', limit={limit})")
    safe_path = validate_path(repo_path)
    
    args = ["log", f"-n", str(limit), "--oneline"]
    res = _run_git_command(args, safe_path)
    if res["return_code"] != 0:
        return f"Error running git log:\nStdout: {res['stdout']}\nStderr: {res['stderr']}"
    return res["stdout"] or "No commit logs found."

@registry.register(name="git_commit", dangerous=True)
def git_commit(repo_path: str = ".", message: str = "Update", auto_add: bool = True) -> str:
    """
    Stage and commit changes to git.

    Args:
        repo_path: The directory path of the git repository. Defaults to current workspace root.
        message: The commit message.
        auto_add: If true, runs 'git add -A' before committing. Defaults to True.
    """
    logger.info(f"Tool call: git_commit(repo_path='{repo_path}', message='{message}')")
    safe_path = validate_path(repo_path)
    
    if auto_add:
        # Run git add -A
        add_res = _run_git_command(["add", "-A"], safe_path)
        if add_res["return_code"] != 0:
            return f"Error adding files to staging:\nStdout: {add_res['stdout']}\nStderr: {add_res['stderr']}"

    # Run commit
    commit_res = _run_git_command(["commit", "-m", message], safe_path)
    if commit_res["return_code"] != 0:
        # Check if there is nothing to commit
        if "nothing to commit" in commit_res["stdout"].lower() or "nothing to commit" in commit_res["stderr"].lower():
            return "No changes to commit. Working tree is clean."
        return f"Error committing changes:\nStdout: {commit_res['stdout']}\nStderr: {commit_res['stderr']}"
        
    return f"Successfully committed changes:\n{commit_res['stdout']}"
