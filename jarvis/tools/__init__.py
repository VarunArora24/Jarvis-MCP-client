# Import tool modules to trigger decorators and populate global tool registry
from jarvis.tools.file import (
    read_file, write_file, create_file, delete_file, 
    list_directory, search_files, search_folders, 
    recursive_search, open_folder, open_file, find_project
)
from jarvis.tools.system import run_terminal_command, open_application, get_system_info
from jarvis.tools.web import web_search, open_url
from jarvis.tools.python import execute_python_code
from jarvis.tools.git import git_status, git_commit, git_log
from jarvis.tools.memory import save_fact, forget_fact, update_fact

# Expose a clean list of all tools in package
__all__ = [
    "read_file",
    "write_file",
    "create_file",
    "delete_file",
    "list_directory",
    "search_files",
    "search_folders",
    "recursive_search",
    "open_folder",
    "open_file",
    "find_project",
    "run_terminal_command",
    "open_application",
    "get_system_info",
    "web_search",
    "open_url",
    "execute_python_code",
    "git_status",
    "git_commit",
    "git_log",
    "save_fact",
    "forget_fact",
    "update_fact"
]
