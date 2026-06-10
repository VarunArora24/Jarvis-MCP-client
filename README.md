# 🎙️ Jarvis — Premium Personal AI Assistant & MCP Server

Jarvis is a production-grade, local-first personal AI assistant built around the **Model Context Protocol (MCP)** architecture. 

It is designed to run locally, manage persistent knowledge memories, execute terminal commands/python code safely, search folders/projects, and serve as an extensible tool server for MCP clients like Cursor, VS Code, and Claude Desktop.

---

## ✨ Key Features

1. **Voice-First Immersive UI**
   * Boots directly into a minimalist **Immersive Voice Mode** featuring a full-screen visual voice orb and status animations.
   * Hide/show sidebar diagnostics, timeline chat bubbles, and command prompt inputs seamlessly via the **Toggle Panels** button or by pressing `Escape`.

2. **High-Fidelity Canvas Voice Reactor**
   * Rendered dynamically at 60 FPS using GPU-accelerated HTML5 Canvas.
   * **Layer 1 (Central Core)**: Dark core center outlined by a glowing neon cyan (`#00E5FF`) border and axis crosshairs.
   * **Layer 2 (Mechanical Rings)**: A thick mechanical concentric ring overlaid with thin ticks.
   * **Layer 3 (Segmented Blocks)**: 12 glowing rectangular blocks rotating independently (accelerates and reverses when Jarvis is thinking).
   * **Layer 4 (Audio Ribbon)**: A continuous, thick organic spectrum ribbon deforming dynamically to microphone volume or simulated speech amplitudes using a multi-tone gradient (`#FF4DFF` -> `#6E5BFF` -> `#00E5FF`).
   * **Layer 5 (Outer Energy Ring)**: Rotating dashed rings and neon outer quadrant energy brackets.

3. **Robust FileSystemAgent Toolset**
   * **`find_project`**: Fuzzy searches workspace directories, scores candidates (based on exact, prefix, substring overlaps, and fuzzy SequenceMatcher ratios), ranks them with modification recency boosts, and opens the best candidate in Windows Explorer.
   * **`search_files` & `search_folders`**: High-performance recursive searches limited to whitelisted directory scopes.
   * **`recursive_search`**: Scans a specific folder recursively for files and subfolders.
   * **`open_file` & `open_folder`**: Safely opens files/folders using native Windows default handlers or Explorer.

4. **Rigorous Security Boundaries**
   * **Path Validation**: Prevents any read, write, or search operation outside whitelisted paths (configured via `.env`) or inside blacklisted paths (such as Windows system directories).
   * **Dangerous Tool Interception**: Pauses execution and displays a security prompt requiring explicit user authorization before launching dangerous commands (terminal commands, Python script execution, file deletions).
   * **Anti-Screenshot Policy**: Enforces strict instructions prohibiting the agent from scanning the desktop or taking screenshots without asking the user for explicit consent in its conversational response first.

5. **Persistent Memory System**
   * Automatically records short-term context and learns facts about your preferences, tools, or folders to recall across restarts.

6. **Double Transport MCP Server**
   * Exposes all tool registries via standard I/O (`stdio`) or HTTP Server-Sent Events (`sse`) to hook up directly to IDEs.

---

## 📂 Project Structure

```text
MCP-Server/
├── requirements.txt         # Package dependencies
├── pyproject.toml           # Setuptools configuration
├── jarvis/
│   ├── main.py              # CLI Entrypoint, HTTP server & MCP Server bootstrap
│   ├── config.py            # Environment settings and paths validation configuration
│   ├── registry.py          # Decorator-based tool collector and schemas compiler
│   ├── agent/
│   │   ├── loop.py          # Agent reasoning loop (Gemini / OpenAI function calling)
│   │   └── memory.py        # Persistent JSON facts database and message context
│   ├── mcp/
│   │   └── server.py        # FastMCP protocol implementation wrapping registered tools
│   ├── tools/
│   │   ├── file.py          # FileSystemAgent: list_dir, find_project, search_files, etc.
│   │   ├── system.py        # OS interaction: run_terminal_command, open_application
│   │   ├── web.py           # Web tools: web_search, open_url
│   │   ├── python.py        # Python interpreter sandbox
│   │   └── git.py           # Git version control commands
│   ├── ui/
│   │   ├── app.py           # PyWebView GUI frame and HTTP app endpoints
│   │   └── web/             # Frontend HTML / CSS / JS visual assets
│   └── utils/
│       ├── logging.py       # Console Rich log handler & file logs handler
│       └── security.py      # Whitelist validation and prompt authorizations
```

---

## 🚀 Setup & Installation

### 1. Requirements
* Python 3.12+
* Windows OS (configured for default folder opening and audio transcription)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Setup Configuration
Copy the `.env.example` template to `.env`:
```bash
copy .env.example .env
```
Edit the `.env` file to supply your credentials and safe path whitelists:
```env
# Gemini API Key (if using gemini provider)
GEMINI_API_KEY=your_gemini_api_key_here

# LLM Provider settings (options: gemini, ollama, groq, openai, openrouter)
JARVIS_LLM_PROVIDER=ollama
JARVIS_LLM_MODEL=qwen2.5-coder:3b

# Local paths allowed to be read, searched, or written to by the agent
JARVIS_WHITELIST_PATHS=C:\path\to\your\allowed\workspace
JARVIS_BLACKLIST_PATHS=C:\Windows,C:\Program Files,C:\Program Files (x86)
```

---

## 🎮 How to Run

### 1. Launch Desktop GUI (Default Mode)
Runs the desktop GUI application opening in fullscreen **Immersive Voice Mode**:
```bash
python -m jarvis.main
```
* **Toggle Panels**: Click the **Toggle Panels** button in the top right or press `Escape` to expand the Diagnostics Sidebars, Memory feeds, Chat timelines, and bottom command inputs.
* **Mute/Voice Loop**: Click the status orb canvas to toggle the microphone capturing loop.

### 2. Launch interactive terminal Chat Mode
Runs the reasoning loop directly inside the console terminal:
```bash
python -m jarvis.main --cli
```

### 3. Launch HTTP Server (Asset Web Host)
```bash
python -m jarvis.main --server
```

### 4. Start as Model Context Protocol (MCP) Server
Allows external tools and IDEs (like Cursor or VS Code) to interact with Jarvis's registry:
* **Standard I/O Transport (Default)**:
  ```bash
  python -m jarvis.main --mcp
  ```
* **Server-Sent Events (SSE HTTP) Transport**:
  ```bash
  python -m jarvis.main --mcp --sse
  ```

---

## 🛡️ Extending Tools

Extending Jarvis is simple. Write a standard Python function inside `jarvis/tools/` and register it using the decorator. Jarvis will automatically reflect the schema to your LLM and expose it via the MCP Server:

```python
from jarvis.registry import registry
from jarvis.utils.security import validate_path

@registry.register(name="calculate_hash", dangerous=False)
def calculate_hash(file_path: str, algorithm: str = "sha256") -> str:
    """
    Calculate the hash of a file.

    Args:
        file_path: Path of the file to hash.
        algorithm: Hash algorithm to use (e.g., md5, sha1, sha256).
    """
    # 1. Enforce path whitelist containment safety
    safe_path = validate_path(file_path)
    
    # 2. Run execution logic
    import hashlib
    hasher = hashlib.new(algorithm)
    with open(safe_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
            
    return hasher.hexdigest()
```
