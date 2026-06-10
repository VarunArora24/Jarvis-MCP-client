import logging
import sys
from pathlib import Path
from rich.logging import RichHandler
from jarvis.config import settings

def setup_logger(name: str = "jarvis") -> logging.Logger:
    """Configures and returns a production-grade logger for Jarvis."""
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers if logger is already configured
    if logger.handlers:
        return logger
        
    logger.setLevel(settings.log_level)
    logger.propagate = False

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - [%(levelname)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Rich CLI logging to stderr (to not interfere with stdout stdout-based protocols like MCP stdio)
    # Note: MCP uses stdout for protocol messages, so all developer/agent logging MUST go to stderr.
    rich_handler = RichHandler(
        console=None,  # default is to print to stderr
        show_time=True,
        show_path=False,
        omit_repeated_times=False,
        keywords=["tool", "executing", "Gemini", "security", "warning", "error", "success"]
    )
    rich_handler.setLevel(settings.log_level)
    logger.addHandler(rich_handler)

    # 2. File Logging (rotating or simple file handler)
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "jarvis.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)  # Always record debug logs to the file
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

# Shared logger instance
logger = setup_logger()
