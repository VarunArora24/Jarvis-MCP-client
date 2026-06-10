import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from jarvis.config import settings
from jarvis.utils.logging import logger

class LongTermMemory:
    """Manages persistent key-value and factual memory for Jarvis using a local JSON file."""
    
    def __init__(self, memory_file: Path):
        self.memory_file = memory_file
        self.data: Dict[str, Any] = {
            "facts": [],
            "preferences": {},
            "workspace_metadata": {}
        }
        self.load()

    def load(self) -> None:
        """Loads memory data from the persistent JSON file."""
        if not self.memory_file.exists():
            logger.info(f"Memory file not found. Creating new memory state at '{self.memory_file}'")
            self.save()
            return

        try:
            content = self.memory_file.read_text(encoding="utf-8")
            if not content.strip():
                # Empty file
                self.save()
                return
            self.data = json.loads(content)
            # Ensure required structures exist
            if "facts" not in self.data:
                self.data["facts"] = []
            if "preferences" not in self.data:
                self.data["preferences"] = {}
            if "workspace_metadata" not in self.data:
                self.data["workspace_metadata"] = {}
            logger.debug("Successfully loaded long-term memory.")
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing memory JSON: {e}. Starting with empty memory.")
            self.save()
        except Exception as e:
            logger.error(f"Failed to load memory file: {e}")

    def save(self) -> None:
        """Saves current memory data to the JSON file."""
        try:
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            self.memory_file.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            logger.debug("Saved long-term memory to disk.")
        except Exception as e:
            logger.error(f"Failed to save memory file: {e}")

    def get(self, category: str, key: str, default: Any = None) -> Any:
        """Retrieve a value from a memory category (e.g. 'preferences')."""
        category_data = self.data.get(category, {})
        if isinstance(category_data, dict):
            return category_data.get(key, default)
        return default

    def set(self, category: str, key: str, value: Any) -> None:
        """Set a value in a memory category."""
        if category not in self.data or not isinstance(self.data[category], dict):
            self.data[category] = {}
        self.data[category][key] = value
        self.save()

    def add_fact(self, fact: str) -> None:
        """Append a newly learned fact about the user or system."""
        fact = fact.strip()
        if fact and fact not in self.data["facts"]:
            self.data["facts"].append(fact)
            logger.info(f"Jarvis learned a new fact: '{fact}'")
            self.save()

    def remove_fact(self, fact: str) -> None:
        """Remove an existing fact from long-term memory."""
        if fact in self.data["facts"]:
            self.data["facts"].remove(fact)
            self.save()

    def get_facts(self) -> List[str]:
        """Get all facts stored in long-term memory."""
        return self.data.get("facts", [])


class ConversationMemory:
    """Manages short-term context/message history for the active chat thread."""
    
    def __init__(self, limit: int = 40):
        # We store messages as structured dicts, e.g. {"role": "user", "content": "..."}
        self.messages: List[Dict[str, Any]] = []
        self.limit = limit

    def add_message(
        self,
        role: str,
        content: Optional[Any] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None,
        parts: Optional[Any] = None
    ) -> None:
        """Add a message to the conversation history, enforcing token-limit pruning."""
        msg = {"role": role}
        
        if content is not None:
            if isinstance(content, str):
                msg["content"] = content
                msg["parts"] = content  # Compatibility with tests
            else:
                msg["parts"] = content
                # Try to extract text content if it's a list/object (like Gemini parts)
                try:
                    if isinstance(content, list) and len(content) > 0 and hasattr(content[0], "text"):
                        msg["content"] = content[0].text
                    elif hasattr(content, "text"):
                        msg["content"] = content.text
                except Exception:
                    pass
        
        if parts is not None:
            msg["parts"] = parts
            if isinstance(parts, str):
                msg["content"] = parts
                
        if tool_calls is not None:
            msg["tool_calls"] = tool_calls
        if tool_call_id is not None:
            msg["tool_call_id"] = tool_call_id
        if name is not None:
            msg["name"] = name

        self.messages.append(msg)
        
        # Enforce simple turn limits to keep context window bounds clean
        # Keep system instructions intact, prune middle dialog if necessary.
        if len(self.messages) > self.limit:
            # We keep the first message (usually system prompt) and the last (limit - 1) messages.
            system_msg = self.messages[0] if self.messages[0]["role"] == "system" else None
            if system_msg:
                self.messages = [system_msg] + self.messages[-(self.limit - 1):]
            else:
                self.messages = self.messages[-self.limit:]
            logger.debug(f"Pruned conversation memory to stay within history limits (limit={self.limit}).")

    def get_messages(self) -> List[Dict[str, Any]]:
        """Retrieve the current conversation thread messages."""
        return self.messages

    def clear(self) -> None:
        """Resets the conversation history."""
        self.messages = []
