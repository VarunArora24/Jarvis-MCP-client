import os
import platform
import subprocess
import json
from typing import Dict, Any, List
from jarvis.registry import registry
from jarvis.utils.logging import logger

@registry.register(name="run_terminal_command", dangerous=True)
def run_terminal_command(command: str) -> Dict[str, Any]:
    """
    Run a shell command on the host terminal.

    Args:
        command: The terminal command to execute.
    """
    logger.info(f"Tool call: run_terminal_command(command='{command}')")
    try:
        # Run command in shell, limit execution to 90 seconds
        result = subprocess.run(
            command,
            shell=True,
            text=True,
            capture_output=True,
            timeout=90
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode
        }
    except subprocess.TimeoutExpired as e:
        return {
            "stdout": e.stdout or "",
            "stderr": f"Command execution timed out (limit 90s). {e.stderr or ''}",
            "return_code": -1
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": f"Failed to execute command: {str(e)}",
            "return_code": -1
        }

# Risky system application executables
RISKY_APPS = {
    "cmd.exe", "powershell.exe", "pwsh.exe", "powershell_ise.exe",
    "regedit.exe", "reg.exe", "msiexec.exe", "diskpart.exe", "format.com",
    "cscript.exe", "wscript.exe", "mshta.exe", "control.exe", "mmc.exe",
    "bash.exe", "sh.exe", "zsh.exe", "vssadmin.exe", "certutil.exe",
    "rundll32.exe", "regsvr32.exe", "schtasks.exe", "sc.exe"
}

# Risky script or configuration extensions
RISKY_EXTS = {
    ".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
    ".msc", ".reg", ".scr"
}

# Pre-defined mapping of common UWP apps to protocols on Windows
UWP_MAP = {
    "clock": "ms-clock:",
    "alarms": "ms-clock:",
    "settings": "ms-settings:",
    "calculator": "ms-calculator:",
    "calendar": "outlookcal:",
    "mail": "outlookmail:",
    "weather": "bingweather:",
    "camera": "microsoft.windows.camera:",
    "maps": "bingmaps:",
    "store": "ms-windows-store:",
    "photos": "ms-photos:",
    "paint 3d": "ms-paint:"
}

from pathlib import Path
from typing import Optional

def resolve_shortcut_target(path: Path) -> Path:
    """Resolve the target path of a .lnk shortcut file on Windows using PowerShell."""
    if path.suffix.lower() != ".lnk":
        return path
        
    import subprocess
    try:
        # Resolve target using PowerShell COM object
        ps_cmd = f"$sh = New-Object -ComObject WScript.Shell; $sh.CreateShortcut('{path}').TargetPath"
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            return Path(res.stdout.strip())
    except Exception as e:
        logger.warning(f"Failed to resolve shortcut '{path}': {e}")
        
    return path

def get_installed_start_apps() -> List[Dict[str, str]]:
    """Query Windows StartApps (modern UWP apps, standard installed software shortcuts)."""
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            if isinstance(data, dict):
                return [data]
            elif isinstance(data, list):
                return data
    except Exception as e:
        logger.warning(f"Failed to query Get-StartApps: {e}")
    return []

def find_installed_app_by_id(app_name: str) -> Optional[str]:
    """Search installed apps via Get-StartApps and return its AppID/URI if found."""
    search_name = app_name.lower().strip()
    
    normalize_map = {
        "vs code": "visual studio code",
        "vscode": "visual studio code",
        "code": "visual studio code",
        "chrome": "google chrome",
        "excel": "microsoft excel",
        "word": "microsoft word",
        "powerpoint": "microsoft powerpoint",
        "edge": "microsoft edge",
        "acrobat": "adobe acrobat",
        "pdf reader": "adobe acrobat",
        "brave browser": "brave",
        "brave": "brave",
        "clash": "clash of clans",
        "stumble": "stumble guys",
        "fall": "fall guys",
    }
    
    search_name = normalize_map.get(search_name, search_name)
    apps = get_installed_start_apps()
    
    exact_matches = []
    prefix_matches = []
    substring_matches = []
    
    for app in apps:
        name = app.get("Name", "").lower()
        appid = app.get("AppID", "")
        if not name or not appid:
            continue
            
        if name == search_name:
            exact_matches.append(appid)
        elif name.startswith(search_name):
            prefix_matches.append((appid, len(name)))
        elif search_name in name:
            substring_matches.append((appid, abs(len(name) - len(search_name))))
            
    if exact_matches:
        return exact_matches[0]
    if prefix_matches:
        prefix_matches.sort(key=lambda x: x[1])
        return prefix_matches[0][0]
    if substring_matches:
        substring_matches.sort(key=lambda x: x[1])
        return substring_matches[0][0]
        
    return None

def validate_safe_application(path: Path) -> None:
    """Raises SecurityError if the resolved application target is risky."""
    from jarvis.utils.security import SecurityError
    
    # 1. Resolve target if it is a shortcut
    target = resolve_shortcut_target(path)
    
    # 2. Check if the target basename is in RISKY_APPS
    basename = target.name.lower()
    if basename in RISKY_APPS:
        raise SecurityError(
            f"Blocked opening application '{path.name}' because its target '{target.name}' is a risky system tool."
        )
        
    # 3. Check if the target suffix is a risky script/executable extension
    suffix = target.suffix.lower()
    if suffix in RISKY_EXTS:
        raise SecurityError(
            f"Blocked opening application '{path.name}' because its target has a risky file type '{suffix}'."
        )
        
    # 4. If it's a .url file, check that it doesn't point to a risky file:// URL
    if path.suffix.lower() == ".url":
        try:
            url_val = ""
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip().startswith("URL="):
                        url_val = line.split("URL=", 1)[1].strip()
                        break
            if url_val:
                url_lower = url_val.lower()
                if url_lower.startswith("file:"):
                    from urllib.parse import urlparse
                    parsed = urlparse(url_val)
                    file_path = Path(parsed.path)
                    if file_path.suffix.lower() in RISKY_EXTS or file_path.name.lower() in RISKY_APPS:
                        raise SecurityError(f"Blocked opening URL shortcut pointing to risky target: {url_val}")
        except Exception as e:
            if isinstance(e, SecurityError):
                raise
            logger.warning(f"Failed to validate .url file target: {e}")

def find_desktop_or_start_menu_app(app_name: str) -> Optional[Path]:
    """
    Search recursively for a shortcut (.lnk) or executable (.exe) matching app_name
    in user and system Start Menu programs and Desktop directories.
    """
    search_name = app_name.lower().strip()
    
    # Normalization map for common shorthand names
    normalize_map = {
        "vs code": "visual studio code",
        "vscode": "visual studio code",
        "code": "visual studio code",
        "chrome": "google chrome",
        "excel": "microsoft excel",
        "word": "microsoft word",
        "powerpoint": "microsoft powerpoint",
        "edge": "microsoft edge",
        "acrobat": "adobe acrobat",
        "pdf reader": "adobe acrobat",
        "brave browser": "brave",
        "brave": "brave",
    }
    
    search_name = normalize_map.get(search_name, search_name)
    
    search_dirs = []
    
    # Desktop directories
    user_desktop = Path.home() / "Desktop"
    if user_desktop.exists():
        search_dirs.append(user_desktop)
        
    onedrive_desktop = Path.home() / "OneDrive" / "Desktop"
    if onedrive_desktop.exists():
        search_dirs.append(onedrive_desktop)
        
    public_desktop = Path("C:/Users/Public/Desktop")
    if public_desktop.exists():
        search_dirs.append(public_desktop)
        
    # Start Menu Programs directories
    user_start_menu = Path.home() / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs"
    if user_start_menu.exists():
        search_dirs.append(user_start_menu)
        
    system_start_menu = Path("C:/ProgramData/Microsoft/Windows/Start Menu/Programs")
    if system_start_menu.exists():
        search_dirs.append(system_start_menu)
        
    candidates = []
    for directory in search_dirs:
        try:
            for path in directory.rglob("*"):
                try:
                    if path.is_file() and path.suffix.lower() in (".lnk", ".exe", ".url"):
                        candidates.append(path)
                except Exception:
                    continue
        except Exception:
            continue
            
    exact_matches = []
    prefix_matches = []
    substring_matches = []
    
    for path in candidates:
        stem = path.stem.lower()
        if stem == search_name:
            exact_matches.append(path)
        elif stem.startswith(search_name):
            prefix_matches.append(path)
        elif search_name in stem or stem in search_name:
            substring_matches.append(path)
            
    if exact_matches:
        return exact_matches[0]
    if prefix_matches:
        prefix_matches.sort(key=lambda p: len(p.stem))
        return prefix_matches[0]
    if substring_matches:
        substring_matches.sort(key=lambda p: abs(len(p.stem) - len(search_name)))
        return substring_matches[0]
        
    return None

@registry.register(name="open_application", dangerous=True)
def open_application(app_name: str, arguments: str = "") -> str:
    """
    Open a desktop application (e.g. notepad, calc, explorer).

    Args:
        app_name: The executable name or system command to start the application.
        arguments: Optional command-line arguments to pass to the application (e.g. a whitelisted file path for notepad, a directory path for explorer, or a URL for a browser).
    """
    logger.info(f"Tool call: open_application(app_name='{app_name}', arguments='{arguments}')")
    from jarvis.utils.security import SecurityError
    
    # Safe fallback map
    app_map = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "paint": "mspaint.exe",
        "mspaint": "mspaint.exe",
        "explorer": "explorer.exe"
    }
    
    search_name = app_name.lower().strip()
    
    if search_name in app_map:
        cmd = app_map[search_name]
    elif search_name in UWP_MAP:
        cmd = f"explorer.exe {UWP_MAP[search_name]}"
    else:
        # 1. First, search for direct shortcut/exe files on Desktop and Start Menu
        app_path = find_desktop_or_start_menu_app(app_name)
        if app_path:
            validate_safe_application(app_path)
            if app_path.suffix.lower() in (".url", ".lnk"):
                cmd = f'explorer.exe "{app_path}"'
            else:
                cmd = f'"{app_path}"'
        else:
            # 2. Fallback to searching all installed start apps via Get-StartApps AppID
            appid = find_installed_app_by_id(app_name)
            if appid:
                # Check for safety inside AppID (should not launch command line interpreters or script runners)
                appid_lower = appid.lower()
                for risky in RISKY_APPS:
                    if risky in appid_lower:
                        raise SecurityError(f"Blocked opening application with AppID '{appid}' because it contains a risky system tool.")
                for risky in RISKY_EXTS:
                    if risky in appid_lower:
                        raise SecurityError(f"Blocked opening application with AppID '{appid}' because of risky file type target.")
                
                # If the AppID contains a protocol scheme (like steam:// or googleplaygames://), open it directly.
                # Otherwise, launch it from the Windows shell Applications Folder.
                if "://" in appid:
                    cmd = f'explorer.exe "{appid}"'
                else:
                    cmd = f'explorer.exe "shell:AppsFolder\\{appid}"'
            else:
                raise FileNotFoundError(
                    f"Application '{app_name}' could not be located on Desktop, in the Start Menu, or in the known safe list."
                )
            
    if arguments:
        arg_lower = arguments.strip().lower()
        is_url = any(arg_lower.startswith(proto) for proto in ("http://", "https://", "www."))
        
        # Strip outer quotes and check for internal double quotes to prevent shell injection
        clean_arguments = arguments.strip(' "\'')
        if '"' in clean_arguments:
            raise SecurityError("Double quotes are not allowed in application arguments for security reasons.")
            
        if not is_url:
            from pathlib import Path
            try:
                # Check if arguments contains a path
                arg_path = Path(clean_arguments)
                if arg_path.is_absolute() or arg_path.exists() or '\\' in clean_arguments or '/' in clean_arguments:
                    from jarvis.utils.security import validate_path
                    validate_path(arg_path)
            except Exception as e:
                if isinstance(e, SecurityError):
                    raise
                    
        cmd = f'{cmd} "{clean_arguments}"'
        
    try:
        # Popen runs it in the background without blocking Jarvis
        subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return f"Successfully sent command to start application: '{cmd}'"
    except Exception as e:
        raise RuntimeError(f"Failed to open application '{app_name}': {str(e)}")

@registry.register(name="get_system_info")
def get_system_info() -> Dict[str, Any]:
    """
    Retrieve information about the computer's OS, CPU, and memory.
    """
    logger.info("Tool call: get_system_info()")
    
    import getpass
    try:
        username = getpass.getuser()
    except Exception:
        username = os.environ.get("USERNAME", os.environ.get("USER", "User"))

    info = {
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "total_ram_gb": None,
        "free_ram_gb": None,
        "logical_processors": os.cpu_count(),
        "username": username
    }
    
    # On Windows, retrieve RAM details using native wmic commands
    if platform.system() == "Windows":
        try:
            # Get physical memory in bytes
            mem_out = subprocess.run(
                "wmic ComputerSystem get TotalPhysicalMemory",
                shell=True, capture_output=True, text=True
            ).stdout
            # Extract digits
            mem_digits = "".join(filter(str.isdigit, mem_out))
            if mem_digits:
                info["total_ram_gb"] = round(int(mem_digits) / (1024**3), 2)
                
            # Get free physical memory in KB
            free_out = subprocess.run(
                "wmic OS get FreePhysicalMemory",
                shell=True, capture_output=True, text=True
            ).stdout
            free_digits = "".join(filter(str.isdigit, free_out))
            if free_digits:
                info["free_ram_gb"] = round(int(free_digits) / (1024**2), 2)
        except Exception as e:
            logger.warning(f"Could not retrieve memory statistics: {e}")
            
    return info
