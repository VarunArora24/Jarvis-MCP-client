import os
import re
import fnmatch
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Dict, Any
from jarvis.config import settings
from jarvis.registry import registry
from jarvis.utils.security import validate_path
from jarvis.utils.logging import logger

@registry.register(name="read_file")
def read_file(path: str) -> str:
    """
    Read the contents of a file.

    Args:
        path: The path of the file to read.
    """
    logger.info(f"Tool call: read_file(path='{path}')")
    safe_path = validate_path(path)
    if not safe_path.is_file():
        raise FileNotFoundError(f"Path '{path}' is not a file.")
    return safe_path.read_text(encoding="utf-8")

@registry.register(name="write_file")
def write_file(path: str, content: str) -> str:
    """
    Write or overwrite contents of a file.

    Args:
        path: The path of the file to write to.
        content: The text content to write into the file.
    """
    logger.info(f"Tool call: write_file(path='{path}', content_len={len(content)})")
    safe_path = validate_path(path)
    # Ensure parent directory is also safe and exists
    validate_path(safe_path.parent)
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path.write_text(content, encoding="utf-8")
    return f"Successfully wrote {len(content)} characters to '{path}'"

@registry.register(name="create_file")
def create_file(path: str, content: str = "") -> str:
    """
    Create a new file. Fails if the file already exists.

    Args:
        path: The path of the file to create.
        content: Optional content to initialize the file with.
    """
    logger.info(f"Tool call: create_file(path='{path}')")
    safe_path = validate_path(path)
    if safe_path.exists():
        raise FileExistsError(f"File '{path}' already exists.")
    validate_path(safe_path.parent)
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path.write_text(content, encoding="utf-8")
    return f"Successfully created new file at '{path}'"

@registry.register(name="delete_file", dangerous=True)
def delete_file(path: str) -> str:
    """
    Delete a file. This is a destructive operation.

    Args:
        path: The path of the file to delete.
    """
    logger.info(f"Tool call: delete_file(path='{path}')")
    safe_path = validate_path(path)
    if not safe_path.exists():
        raise FileNotFoundError(f"File '{path}' does not exist.")
    if not safe_path.is_file():
        raise IsADirectoryError(f"Path '{path}' is a directory, not a file. Delete folder is not supported.")
    
    safe_path.unlink()
    return f"Successfully deleted file '{path}'"

@registry.register(name="list_directory")
def list_directory(path: str = ".") -> List[Dict[str, Any]]:
    """
    List contents of a directory.

    Args:
        path: The directory path to list. Defaults to the current workspace root.
    """
    logger.info(f"Tool call: list_directory(path='{path}')")
    safe_path = validate_path(path)
    if not safe_path.is_dir():
        raise NotADirectoryError(f"Path '{path}' is not a directory.")

    contents = []
    for item in safe_path.iterdir():
        try:
            stat = item.stat()
            contents.append({
                "name": item.name,
                "path": str(item.resolve().as_posix()),
                "type": "directory" if item.is_dir() else "file",
                "size_bytes": stat.st_size if item.is_file() else None,
                "modified_time": stat.st_mtime
            })
        except Exception:
            continue
    return contents

def _scan_directory(root: Path, query: str, find_dirs: bool, find_files: bool) -> List[Dict[str, Any]]:
    matches = []
    is_wildcard = any(char in query for char in ["*", "?", "[", "]"])
    pattern = query if is_wildcard else f"*{query}*"
    
    skipped_dirs = {
        "node_modules", ".git", ".venv", "venv", "env", "__pycache__", 
        ".gemini", ".idea", ".vscode", "AppData", "Application Data", "Local Settings", "Temp"
    }
    
    def walk(directory: Path):
        try:
            for item in directory.iterdir():
                try:
                    validate_path(item)
                except Exception:
                    continue
                
                if item.is_dir():
                    if item.name in skipped_dirs or item.name.startswith("."):
                        continue
                    if find_dirs and (fnmatch.fnmatch(item.name.lower(), pattern.lower()) or (not is_wildcard and query.lower() in item.name.lower())):
                        try:
                            stat = item.stat()
                            matches.append({
                                "name": item.name,
                                "path": str(item.resolve().as_posix()),
                                "modified_time": stat.st_mtime
                            })
                        except Exception:
                            pass
                    walk(item)
                elif item.is_file() and find_files:
                    if fnmatch.fnmatch(item.name.lower(), pattern.lower()) or (not is_wildcard and query.lower() in item.name.lower()):
                        try:
                            stat = item.stat()
                            matches.append({
                                "name": item.name,
                                "path": str(item.resolve().as_posix()),
                                "modified_time": stat.st_mtime,
                                "size_bytes": stat.st_size
                            })
                        except Exception:
                            pass
        except PermissionError:
            pass
        except Exception:
            pass
            
    walk(root)
    return matches

@registry.register(name="search_files")
def search_files(query: str) -> List[Dict[str, Any]]:
    """
    Search recursively for files in whitelisted directories matching a wildcard or substring query.
    Results are sorted by modification time (recency).

    Args:
        query: The substring or wildcard pattern to match in filename (e.g. "report" or "*.ipynb").
    """
    logger.info(f"Tool call: search_files(query='{query}')")
    
    roots = list(settings.whitelist_paths)
    
    all_matches = []
    seen_paths = set()
    for root in roots:
        if not root.is_dir():
            continue
        try:
            results = _scan_directory(root, query, find_dirs=False, find_files=True)
            for r in results:
                if r["path"] not in seen_paths:
                    seen_paths.add(r["path"])
                    all_matches.append(r)
        except Exception:
            continue
            
    all_matches.sort(key=lambda x: x["modified_time"], reverse=True)
    return all_matches[:100]

@registry.register(name="search_folders")
def search_folders(query: str) -> List[Dict[str, Any]]:
    """
    Search recursively for folders in whitelisted directories matching a wildcard or substring query.
    Results are sorted by modification time (recency).

    Args:
        query: The substring or wildcard pattern to match in folder name.
    """
    logger.info(f"Tool call: search_folders(query='{query}')")
    
    roots = list(settings.whitelist_paths)
    
    all_matches = []
    seen_paths = set()
    for root in roots:
        if not root.is_dir():
            continue
        try:
            results = _scan_directory(root, query, find_dirs=True, find_files=False)
            for r in results:
                if r["path"] not in seen_paths:
                    seen_paths.add(r["path"])
                    all_matches.append(r)
        except Exception:
            continue
            
    all_matches.sort(key=lambda x: x["modified_time"], reverse=True)
    return all_matches[:100]

@registry.register(name="recursive_search")
def recursive_search(root: str, query: str) -> List[Dict[str, Any]]:
    """
    Recursively search a specific root directory for files and folders matching a query.
    Results are sorted by modification time.

    Args:
        root: The root directory path to search in.
        query: The substring or wildcard pattern to search for in file/folder names.
    """
    logger.info(f"Tool call: recursive_search(root='{root}', query='{query}')")
    safe_root = validate_path(root)
    if not safe_root.is_dir():
        raise NotADirectoryError(f"Path '{root}' is not a directory.")

    matches = _scan_directory(safe_root, query, find_dirs=True, find_files=True)
    matches.sort(key=lambda x: x["modified_time"], reverse=True)
    return matches[:100]

@registry.register(name="open_folder")
def open_folder(path: str) -> str:
    """
    Open a folder in Windows Explorer.

    Args:
        path: The directory path to open.
    """
    logger.info(f"Tool call: open_folder(path='{path}')")
    safe_path = validate_path(path)
    if not safe_path.is_dir():
        raise NotADirectoryError(f"Path '{path}' is not a directory.")
    
    try:
        os.startfile(safe_path)
        return f"Successfully opened folder '{path}' in Explorer."
    except Exception as e:
        raise OSError(f"Failed to open folder: {e}")

@registry.register(name="open_file")
def open_file(path: str) -> str:
    """
    Open a file using its default application on Windows.

    Args:
        path: The file path to open.
    """
    logger.info(f"Tool call: open_file(path='{path}')")
    safe_path = validate_path(path)
    if not safe_path.is_file():
        raise FileNotFoundError(f"Path '{path}' is not a file.")
        
    try:
        os.startfile(safe_path)
        return f"Successfully opened file '{path}' in default application."
    except Exception as e:
        raise OSError(f"Failed to open file: {e}")

def _normalize_project_name(s: str) -> str:
    return " ".join(re.findall(r'[a-zA-Z0-9]+', s.lower()))

def _score_project_match(item_name: str, target_name: str) -> float:
    norm_item = _normalize_project_name(item_name)
    norm_target = _normalize_project_name(target_name)
    
    if not norm_item or not norm_target:
        return 0.0
        
    score = 0.0
    
    # Exact normalized match
    if norm_item == norm_target:
        score = 100.0
    # Prefix match
    elif norm_item.startswith(norm_target):
        score = 85.0
    # Substring match
    elif norm_target in norm_item:
        score = 70.0
    elif norm_item in norm_target:
        score = 50.0
    else:
        # Word overlap check
        target_words = set(norm_target.split())
        item_words = set(norm_item.split())
        if target_words and item_words:
            intersection = target_words.intersection(item_words)
            if intersection:
                overlap = len(intersection) / len(target_words)
                score = 30.0 + overlap * 30.0
                
    # Fuzzy similarity ratio boost (up to 20 points)
    similarity = SequenceMatcher(None, norm_item, norm_target).ratio()
    score += similarity * 20.0
    
    return score

@registry.register(name="find_project")
def find_project(name: str) -> str:
    """
    Search standard workspace directories for a project matching 'name'.
    Scoring ranks matches by (exact, prefix, substring, recency boost, fuzzy similarity) and opens the best match in Explorer.

    Args:
        name: The name of the project to find and open.
    """
    logger.info(f"Tool call: find_project(name='{name}')")
    
    search_dirs = list(settings.whitelist_paths)
    curr = Path.cwd().resolve()
    for _ in range(3):
        try:
            validate_path(curr)
            if curr not in search_dirs:
                search_dirs.insert(0, curr)
        except Exception:
            pass
        curr = curr.parent
        
    extra_dirs = [
        Path.home() / "Documents",
        Path.home() / "Documents" / "stuff" / "Coding",
        Path.home() / "Desktop",
    ]
    for d in extra_dirs:
        try:
            validate_path(d)
            if d.is_dir() and d not in search_dirs:
                search_dirs.append(d)
        except Exception:
            pass
            
    candidates = []
    
    for base_dir in search_dirs:
        try:
            validate_path(base_dir)
        except Exception:
            continue
            
        try:
            for item in base_dir.iterdir():
                try:
                    validate_path(item)
                except Exception:
                    continue
                if not item.is_dir():
                    continue
                if item.name.startswith(".") or item.name.startswith("__"):
                    continue
                    
                score = _score_project_match(item.name, name)
                
                # We require a baseline matching score of 35.0 to consider a match
                if score < 35.0:
                    continue
                    
                try:
                    mtime = item.stat().st_mtime
                    recency_boost = min(10.0, (mtime / 1e8) % 10)
                    score += recency_boost
                except Exception:
                    mtime = 0
                    
                candidates.append({
                    "path": item,
                    "score": score,
                    "mtime": mtime
                })
        except Exception:
            continue
            
    if not candidates:
        return f"No project directories found matching '{name}'."
        
    candidates.sort(key=lambda x: (x["score"], x["mtime"]), reverse=True)
    best_match = candidates[0]["path"]
    
    try:
        os.startfile(best_match)
        return f"Found and opened best match project '{best_match.name}' at '{best_match.resolve().as_posix()}' (Scoring: {candidates[0]['score']:.1f})."
    except Exception as e:
        return f"Found project '{best_match.name}' at '{best_match.resolve().as_posix()}' but failed to open: {e}"
