from jarvis.registry import registry
from jarvis.config import settings
from jarvis.agent.memory import LongTermMemory
from jarvis.utils.logging import logger

@registry.register(name="save_fact")
def save_fact(fact: str) -> str:
    """
    Save an important fact about the user or their workspace to long-term memory.
    Use this to remember names, preferences, or project details across sessions.

    Args:
        fact: The fact to memorize (e.g., "The user's preferred editor is VS Code").
    """
    logger.info(f"Tool call: save_fact(fact='{fact}')")
    memory = LongTermMemory(settings.memory_file)
    memory.add_fact(fact)
    return f"Successfully saved fact to long-term memory: '{fact}'"

@registry.register(name="forget_fact")
def forget_fact(fact: str) -> str:
    """
    Remove an outdated or incorrect fact from long-term memory.

    Args:
        fact: The exact fact text to remove.
    """
    logger.info(f"Tool call: forget_fact(fact='{fact}')")
    memory = LongTermMemory(settings.memory_file)
    memory.remove_fact(fact)
    return f"Successfully removed fact from memory: '{fact}'"

@registry.register(name="update_fact")
def update_fact(old_fact: str, new_fact: str) -> str:
    """
    Update an existing fact in long-term memory with new or corrected information.
    Use this when a fact about the user or their workspace changes (e.g. name update, new preference).

    Args:
        old_fact: The exact text of the outdated or incorrect fact to replace.
        new_fact: The new fact text to save in its place.
    """
    logger.info(f"Tool call: update_fact(old_fact='{old_fact}', new_fact='{new_fact}')")
    memory = LongTermMemory(settings.memory_file)
    memory.remove_fact(old_fact)
    memory.add_fact(new_fact)
    return f"Successfully updated fact: replaced '{old_fact}' with '{new_fact}'"

