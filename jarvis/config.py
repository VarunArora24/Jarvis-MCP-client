import os
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

class Settings(BaseModel):
    gemini_api_key: str = Field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", "")
    )
    llm_provider: str = Field(default="gemini")
    llm_model: str = Field(default="gemini-1.5-flash")
    llm_api_key: str = Field(default="")
    llm_base_url: str = Field(default="")
    whitelist_paths: List[Path] = Field(default_factory=list)
    blacklist_paths: List[Path] = Field(default_factory=list)
    confirmation_required: bool = Field(default=True)
    memory_file: Path = Field(default=Path("jarvis_memory.json"))
    log_level: str = Field(default="INFO")

    def __init__(self, **data):
        super().__init__(**data)
        
        # Load and parse LLM provider settings
        self.llm_provider = os.getenv("JARVIS_LLM_PROVIDER", "gemini").lower()
        self.llm_model = os.getenv("JARVIS_LLM_MODEL", "")
        self.llm_api_key = os.getenv("JARVIS_LLM_API_KEY", "")
        self.llm_base_url = os.getenv("JARVIS_LLM_BASE_URL", "")
        
        # Apply provider-specific defaults
        if self.llm_provider == "gemini":
            if not self.llm_model:
                self.llm_model = "gemini-1.5-flash"
            if not self.llm_api_key:
                self.llm_api_key = os.getenv("GEMINI_API_KEY", "")
        elif self.llm_provider == "ollama":
            if not self.llm_model:
                self.llm_model = "llama3.1"
            if not self.llm_base_url:
                self.llm_base_url = "http://localhost:11434/v1"
            if not self.llm_api_key:
                self.llm_api_key = "ollama"
        elif self.llm_provider == "groq":
            if not self.llm_model:
                self.llm_model = "llama-3.3-70b-versatile"
            if not self.llm_base_url:
                self.llm_base_url = "https://api.groq.com/openai/v1"
            if not self.llm_api_key:
                self.llm_api_key = os.getenv("GROQ_API_KEY", "")
        elif self.llm_provider == "openai":
            if not self.llm_model:
                self.llm_model = "gpt-4o"
            if not self.llm_base_url:
                self.llm_base_url = "https://api.openai.com/v1"
            if not self.llm_api_key:
                self.llm_api_key = os.getenv("OPENAI_API_KEY", "")
        elif self.llm_provider == "openrouter":
            if not self.llm_model:
                self.llm_model = "meta-llama/llama-3.3-70b-instruct"
            if not self.llm_base_url:
                self.llm_base_url = "https://openrouter.ai/api/v1"
            if not self.llm_api_key:
                self.llm_api_key = os.getenv("OPENROUTER_API_KEY", "")

        # Load and parse whitelist paths from environment
        whitelist_raw = os.getenv("JARVIS_WHITELIST_PATHS", "")
        if whitelist_raw:
            # Split by comma or semicolon and resolve path
            paths = [p.strip() for p in whitelist_raw.replace(";", ",").split(",") if p.strip()]
            self.whitelist_paths = [Path(p).resolve() for p in paths]
        else:
            # Default to current working directory and user home directory if not specified
            self.whitelist_paths = [
                Path.cwd().resolve(),
                Path.home().resolve()
            ]

        # Load and parse blacklist paths from environment
        blacklist_raw = os.getenv("JARVIS_BLACKLIST_PATHS", "")
        if blacklist_raw:
            paths = [p.strip() for p in blacklist_raw.replace(";", ",").split(",") if p.strip()]
            self.blacklist_paths = [Path(p).resolve() for p in paths]
        else:
            # Default Windows system paths
            self.blacklist_paths = [
                Path("C:/Windows").resolve(),
                Path("C:/Program Files").resolve(),
                Path("C:/Program Files (x86)").resolve(),
            ]

        # Parse confirmation setting
        conf_raw = os.getenv("JARVIS_CONFIRMATION_REQUIRED", "true").lower()
        self.confirmation_required = conf_raw in ("true", "1", "yes")

        # Memory file path
        mem_raw = os.getenv("JARVIS_MEMORY_FILE", "jarvis_memory.json")
        self.memory_file = Path(mem_raw).resolve()

        # Log level
        self.log_level = os.getenv("JARVIS_LOG_LEVEL", "INFO").upper()

# Instantiate single settings instance
settings = Settings()
