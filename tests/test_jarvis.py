import pytest
from pathlib import Path
from jarvis.config import settings
from jarvis.registry import ToolRegistry, Tool
from jarvis.agent.memory import ConversationMemory, LongTermMemory
from jarvis.utils.security import validate_path, SecurityError

def test_path_validation(tmp_path):
    """Verifies that path containment checks correctly enforce whitelists/blacklists."""
    # Temporarily set whitelist to a mock directory
    original_whitelist = settings.whitelist_paths
    settings.whitelist_paths = [tmp_path.resolve()]
    
    try:
        # File inside whitelist should resolve and be allowed
        inside_file = tmp_path / "test.txt"
        inside_file.write_text("hello")
        resolved = validate_path(inside_file)
        assert resolved == inside_file.resolve()
        
        # File outside whitelist should raise SecurityError
        outside_file = Path("C:/Windows/System32/cmd.exe") if Path("C:/Windows").exists() else Path("/etc/passwd")
        with pytest.raises(SecurityError) as exc_info:
            validate_path(outside_file)
        assert "Access denied" in str(exc_info.value)
        
    finally:
        # Restore whitelist
        settings.whitelist_paths = original_whitelist


def test_tool_registry():
    """Verifies that registry decorators parse signatures and docstrings correctly."""
    mock_registry = ToolRegistry()
    
    @mock_registry.register(name="test_math_tool", dangerous=False)
    def test_math_tool(a: int, b: str, c: bool = True) -> str:
        """
        Add elements together.

        Args:
            a: The first parameter.
            b: The second parameter.
            c: The third parameter.
        """
        return f"{a}-{b}-{c}"
        
    assert "test_math_tool" in mock_registry.tools
    tool = mock_registry.tools["test_math_tool"]
    assert tool.dangerous is False
    assert tool.description == "Add elements together."
    
    # Check MCP schema parameter types
    schema = tool.parameters_schema
    assert schema["type"] == "object"
    assert schema["properties"]["a"]["type"] == "integer"
    assert schema["properties"]["a"]["description"] == "The first parameter."
    assert schema["properties"]["b"]["type"] == "string"
    assert schema["properties"]["c"]["type"] == "boolean"
    assert "c" not in schema["required"]  # c has default value
    assert "a" in schema["required"]
    assert "b" in schema["required"]
    
    # Check Gemini schema type formatting
    gemini_schema = tool.get_gemini_schema()
    assert gemini_schema["name"] == "test_math_tool"
    assert gemini_schema["parameters"]["properties"]["a"]["type"] == "INTEGER"


def test_memory_systems(tmp_path):
    """Verifies that short-term and persistent memories store items correctly."""
    # Test persistent memory
    mem_file = tmp_path / "memory.json"
    memory = LongTermMemory(mem_file)
    
    memory.add_fact("The user likes Python 3.12")
    assert "The user likes Python 3.12" in memory.get_facts()
    
    # Reload from file
    memory2 = LongTermMemory(mem_file)
    assert "The user likes Python 3.12" in memory2.get_facts()
    
    # Test short term conversation limits
    conv = ConversationMemory(limit=3)
    conv.add_message("system", "sys-prompt")
    conv.add_message("user", "msg1")
    conv.add_message("model", "msg2")
    conv.add_message("user", "msg3")  # This should cause pruning
    
    msgs = conv.get_messages()
    # It should keep system prompt and prune oldest entries
    assert len(msgs) == 3
    assert msgs[0]["parts"] == "sys-prompt"
    assert msgs[1]["parts"] == "msg2"
    assert msgs[2]["parts"] == "msg3"


def test_agent_system_instruction(monkeypatch, tmp_path):
    """Verifies that the agent can generate system instructions correctly without raising NameError/etc."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock_key")
    # Redirect memory path so we don't write to settings default memory file
    original_memory_file = settings.memory_file
    settings.memory_file = tmp_path / "memory.json"
    
    from google import genai
    monkeypatch.setattr(genai, "Client", lambda api_key: None)
    
    try:
        from jarvis.agent.loop import JarvisAgent
        agent = JarvisAgent(is_interactive=False)
        instruction = agent._get_system_instruction()
        assert "Jarvis" in instruction
        assert "Workspace" in instruction
    finally:
        # Restore settings
        settings.memory_file = original_memory_file


def test_app_finding_and_validation(tmp_path, monkeypatch):
    """Verify application matching and safety verification."""
    from jarvis.tools.system import (
        find_desktop_or_start_menu_app,
        validate_safe_application,
    )
    from jarvis.utils.security import SecurityError
    
    # Mock home folder so it points to tmp_path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    
    # Create mock Desktop
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    
    # Create some mock shortcut files
    brave_lnk = desktop / "Brave.lnk"
    brave_lnk.touch()
    
    cmd_lnk = desktop / "cmd.lnk"
    cmd_lnk.touch()
    
    # Test normalization and matching
    assert find_desktop_or_start_menu_app("brave") == brave_lnk
    assert find_desktop_or_start_menu_app("brave browser") == brave_lnk
    
    # Mock shortcut resolution for safe app
    monkeypatch.setattr(
        "jarvis.tools.system.resolve_shortcut_target",
        lambda p: Path("C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe")
    )
    # This should pass without raising
    validate_safe_application(brave_lnk)
    
    # Mock shortcut resolution for risky app
    monkeypatch.setattr(
        "jarvis.tools.system.resolve_shortcut_target",
        lambda p: Path("C:/Windows/System32/cmd.exe")
    )
    with pytest.raises(SecurityError) as exc_info:
        validate_safe_application(cmd_lnk)
    assert "Blocked opening application" in str(exc_info.value)


def test_open_application_args(monkeypatch, tmp_path):
    """Test argument quoting, URL validation bypass, and double quote injection blocks in open_application."""
    from jarvis.tools.system import open_application
    from jarvis.utils.security import SecurityError
    import subprocess
    
    # Mock Popen to see what command is run
    commands_run = []
    def mock_popen(cmd, *args, **kwargs):
        commands_run.append(cmd)
        class MockProcess:
            pass
        return MockProcess()
        
    monkeypatch.setattr(subprocess, "Popen", mock_popen)
    
    # Mock search so we find Brave
    monkeypatch.setattr(
        "jarvis.tools.system.find_desktop_or_start_menu_app",
        lambda name: Path("C:/Users/mockuser/Desktop/Brave.lnk")
    )
    monkeypatch.setattr(
        "jarvis.tools.system.validate_safe_application",
        lambda path: None
    )
    
    # Test safe UWP clock launch
    open_application("clock")
    assert commands_run[-1] == "explorer.exe ms-clock:"
    
    # Test browser URL query
    open_application("brave", "https://search.brave.com/search?q=hello&source=web")
    expected_path = Path("C:/Users/mockuser/Desktop/Brave.lnk")
    assert commands_run[-1] == f'explorer.exe "{expected_path}" "https://search.brave.com/search?q=hello&source=web"'
    
    # Test path validation for local files (mock validate_path)
    import jarvis.utils.security
    validate_path_calls = []
    def mock_validate_path(path):
        validate_path_calls.append(path)
        return Path(path)
    monkeypatch.setattr(jarvis.utils.security, "validate_path", mock_validate_path)
    
    open_application("notepad", "C:\\my_file.txt")
    assert len(validate_path_calls) == 1
    assert "notepad.exe \"C:\\my_file.txt\"" in commands_run[-1]
    
    # Test shell injection protection
    with pytest.raises(SecurityError):
        open_application("notepad", 'hello" & calc.exe')

