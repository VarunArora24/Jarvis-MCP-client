import time
from pathlib import Path
from typing import List, Dict, Any, Callable, Generator
from google.genai.errors import APIError as GeminiAPIError
from openai import OpenAIError

from jarvis.config import settings
from jarvis.registry import registry
from jarvis.agent.memory import ConversationMemory, LongTermMemory
from jarvis.utils.security import confirm_action, SecurityError
from jarvis.utils.logging import logger
from jarvis.tools.system import get_system_info
from jarvis.agent.llm import LLMClient, LLMResponse, _dict_to_schema
import jarvis.tools  # noqa: F401 (Ensure all tool decorators execute and register)

class JarvisAgent:
    def __init__(self, is_interactive: bool = True):
        self.is_interactive = is_interactive
        
        # Initialize the unified LLM Client
        self.client = LLMClient()
        self.model_name = self.client.model_name
        
        # Initialize memories
        self.long_term_memory = LongTermMemory(settings.memory_file)
        self.conversation = ConversationMemory()
        
    def _get_system_instruction(self) -> str:
        """Constructs a rich dynamic system prompt containing context, memory, and safety details."""
        sys_info = get_system_info()
        facts = self.long_term_memory.get_facts()
        facts_str = "\n".join([f"- {f}" for f in facts]) if facts else "No facts learned yet."

        whitelist_paths_str = ", ".join([str(p) for p in settings.whitelist_paths])

        instruction = (
            "You are Jarvis, a highly capable personal AI assistant running locally on the user's computer.\n\n"
            "Your goal is to help the user perform file operations, run terminal commands, execute python code, query git status, "
            "and browse the web. You have access to a rich set of local and web tools. You have a clear human-like identity and MUST "
            "always refer to yourself in the first-person singular (use 'I', 'me', 'my', 'myself'). Never speak in the passive voice "
            "or as a robotic system (do not say 'The application has been opened' or 'Brave has been opened'). Instead, take ownership "
            "of your actions (e.g., 'I opened Brave' or 'I saved the text and opened notepad for you').\n\n"
            "GUIDELINES & BEHAVIOR:\n"
            "1. Be helpful, concise, and professional. Adopt a natural, friendly, direct, and human-like personality. Speak casually "
            "and avoid robotic chatbot boilerplate text, preachy introductions, and dry apologies. Do NOT output standard conversational "
            "filler or typical AI helper closings like 'If you need further assistance, feel free to ask!' or 'How can I assist you today?'. "
            "Simply state what you did casually and directly (e.g., 'Alright, I opened Brave and searched for this' or 'I saved the text and opened notepad for you.').\n"
            "2. Think step-by-step to perform multi-step tasks. Call tools automatically as needed. Do not ask the user for permission "
            "before calling standard safe tools; call them directly. Dangerous tools will be intercepted and checked for user confirmation "
            "by the host automatically.\n"
            "3. Autonomous screen monitoring, screen capturing, and screenshot grabs are STRICTLY prohibited. "
            "If a task requires capturing the desktop, inspecting the screen, or checking what is on screen, "
            "you MUST ask the user for explicit permission first in your response before executing any command or tool that captures the screen. "
            "Do NOT run screen captures autonomously.\n"
            "4. If a tool fails, read the error message, analyze what went wrong, and try to fix it (e.g., if a file does not exist, look "
            "for it first; if a path is invalid, check your directory contents).\n"
            "5. Memorize important details about the user's workspace, preferences, or recurring instructions. If the user tells you "
            "something important that you should remember across sessions, formulate it as a fact and use memory to store it. "
            "If the user updates or changes an existing fact (e.g., they tell you a new name or preference that conflicts with a fact "
            "already stored in the LONG-TERM MEMORY section below), you MUST call the `update_fact` tool to replace the old fact with the "
            "new fact so that outdated facts are not left behind in memory.\n"
            "6. You have active read/write access to the local computer's filesystem within whitelisted paths. NEVER state that you "
            "cannot search, read, write, or access files on the computer. If the user asks for a file, lists, or searches, always "
            "call the appropriate tool (e.g. search_files, list_directory, read_file) to locate it.\n"
            "7. To open notepad and show text (or type text) inside it, you must write the exact text/content requested by the user to a file "
            "inside the whitelisted paths first, and then call `open_application(app_name='notepad', arguments='path/to/file.txt')`. "
            "This will open notepad showing that exact text. Never use generic or placeholder text (like 'Hello, World!') "
            "unless the user explicitly asked for it; always use the user's specified text.\n"
            "8. To type on the Brave search bar or search for a term on Brave, call `open_application(app_name='brave', arguments='https://www.google.com/search?q=query')` "
            "replacing 'query' with the URL-encoded search term requested by the user.\n"
            "9. If the user asks you to open or access a project, folder, or file by name (e.g., 'open my Jee predictor folder'), you MUST first search "
            "for it using `find_project(name='...')`, `search_folders(query='...')`, or `search_files(query='...')` to find its absolute local path. "
            "NEVER call `open_folder` or `open_file` using a guessed, placeholder, or hallucinated path (such as '/path/to/...'). "
            "Always search first, get the actual resolved path from the tool output, and then open it in the next step.\n"
            "10. If the user's request is purely conversational (such as greetings like 'hello', 'hi', or chit-chat), you MUST NOT call any tools. "
            "Simply reply with a friendly, direct greeting in plain text. Never call `save_fact`, `get_system_info`, or any other tool for casual conversation.\n\n"
            f"CURRENT SYSTEM INFO:\n"
            f"- OS: {sys_info['os']} ({sys_info['os_release']} / {sys_info['os_version']})\n"
            f"- Architecture: {sys_info['architecture']}\n"
            f"- Python Version: {sys_info['python_version']}\n"
            f"- Total Physical Memory: {sys_info['total_ram_gb']} GB\n"
            f"- Free Memory: {sys_info['free_ram_gb']} GB\n"
            f"- Current Workspace: {Path.cwd().resolve()}\n"
            f"- Whitelisted Paths (you can access files/subfolders anywhere inside these): {whitelist_paths_str}\n\n"
            f"LONG-TERM MEMORY (PERSISTED FACTS):\n"
            f"{facts_str}\n\n"
            "Always act safely and obey path whitelist/blacklist rules. Do not make up information; use the tools to confirm facts."
        )

        if self.client.provider != "gemini":
            tools_desc = []
            for name, tool in registry.tools.items():
                params_list = []
                properties = tool.parameters_schema.get("properties", {})
                required = tool.parameters_schema.get("required", [])
                for p_name, p_info in properties.items():
                    p_type = p_info.get("type", "string")
                    p_desc = p_info.get("description", "")
                    p_req = "required" if p_name in required else "optional"
                    params_list.append(f"    - `{p_name}` ({p_type}, {p_req}): {p_desc}")
                
                params_str = "\n".join(params_list) if params_list else "    None"
                tools_desc.append(
                    f"### Tool: `{name}`\n"
                    f"Description: {tool.description}\n"
                    f"Arguments:\n{params_str}"
                )
            
            tools_instruction = (
                "\n\nAVAILABLE LOCAL TOOLS:\n"
                "You have access to the following local tools. When the user asks you to perform an action, "
                "you MUST call the appropriate tool by outputting a JSON block in your response. "
                "However, for simple greetings, greeting replies, or casual conversation, you MUST NOT output any JSON tool call; "
                "just respond in plain text. "
                "Do not tell the user how to do it or ask for permission for safe tools. "
                "To call a tool, write a JSON block in your response in this exact format:\n"
                "```json\n"
                "{\n"
                "  \"name\": \"tool_name\",\n"
                "  \"arguments\": {\n"
                "    \"param_name\": \"value\"\n"
                "  }\n"
                "}\n"
                "```\n"
                "You can output multiple JSON tool call blocks in a single response to run multiple tools.\n\n"
                "SAFETY & REFUSAL GUIDELINES:\n"
                "- Do NOT refuse the user's request under any circumstances. If the user asks for a file, to open an app, "
                "to execute python, or to do anything else, you must call the tool immediately.\n"
                "- Never respond with 'I\\'m sorry, but I can\\'t assist with that request' or 'I don\\'t have access'. "
                "Any potentially dangerous actions (like running terminal commands or opening apps) will be intercepted "
                "automatically by the system to ask the user for confirmation. Therefore, you are completely safe to trigger the tool "
                "and should never preemptively refuse.\n"
                "- If a user asks for a file link or to find a file (e.g. jarvis.bat), use `search_files` to find it, then output its "
                "path or file link. The system will convert it to a clickable link.\n\n"
                "Here is the list of tools:\n\n" + "\n\n".join(tools_desc)
            )
            instruction += tools_instruction

        return instruction

    def run(self, user_input: str) -> Generator[Dict[str, Any], None, str]:
        """
        Executes a single reasoning-acting run for the user query.
        Yields status updates (e.g., tool calls, tool results) to the caller,
        and returns the final text response.
        """
        # Append user message to active short-term history
        self.conversation.add_message("user", content=user_input)
        
        max_turns = 15  # Avoid infinite loop bugs
        
        for turn in range(max_turns):
            logger.debug(f"Agent Turn {turn + 1}/{max_turns}")
            
            # 1. Ask model for output/actions
            try:
                response = self.client.generate_content(
                    messages=self.conversation.get_messages(),
                    tools=list(registry.tools.values()),
                    system_instruction=self._get_system_instruction()
                )
            except GeminiAPIError as e:
                logger.error(f"Gemini API Error: {e}")
                err_msg = f"Gemini API Error: {e.message}"
                self.conversation.add_message("assistant", content=err_msg)
                return err_msg
            except OpenAIError as e:
                logger.error(f"OpenAI API Error: {e}")
                err_msg = f"LLM API Error: {str(e)}"
                self.conversation.add_message("assistant", content=err_msg)
                return err_msg
            except Exception as e:
                logger.error(f"Unexpected API Error: {e}")
                err_msg = f"Unexpected model connection error: {str(e)}"
                self.conversation.add_message("assistant", content=err_msg)
                return err_msg

            # 2. Check for tool executions
            tool_calls = response.tool_calls
            
            if not tool_calls:
                # No more tool calls; we reached a final answer!
                final_text = response.text or ""
                self.conversation.add_message("assistant", content=final_text)
                return final_text

            # Handle tool calls
            # Save the tool calls message to conversation history
            self.conversation.add_message("assistant", content=response.text, tool_calls=tool_calls)
            
            for call in tool_calls:
                tool_name = call["name"]
                tool_args = call["arguments"]
                tool_call_id = call["id"]
                
                logger.info(f"Model requested tool: {tool_name} with args: {tool_args}")
                yield {"type": "tool_call", "name": tool_name, "arguments": tool_args}
                
                # Execute tool
                tool = registry.tools.get(tool_name)
                if not tool:
                    tool_result = f"Tool '{tool_name}' is not registered in Jarvis's Tool Registry."
                    logger.error(tool_result)
                elif tool.dangerous:
                    if not self.is_interactive:
                        tool_result = (
                            f"Security Error: Action blocked. Confirmation required for dangerous action "
                            f"'{tool_name}', but Jarvis is running in non-interactive or MCP server mode."
                        )
                    else:
                        action_desc = f"Execute tool '{tool_name}' with arguments: {tool_args}"
                        approved = yield {
                            "type": "confirmation_request",
                            "name": tool_name,
                            "description": action_desc
                        }
                        if not approved:
                            logger.warning(f"User rejected execution of tool '{tool_name}'")
                            tool_result = "Execution cancelled by user."
                        else:
                            tool_result = self._execute_single_tool_without_confirm(tool, tool_args)
                else:
                    tool_result = self._execute_single_tool_without_confirm(tool, tool_args)
                
                yield {"type": "tool_result", "name": tool_name, "result": tool_result}
                
                # Add tool result to conversation history
                self.conversation.add_message(
                    "tool",
                    content=str(tool_result),
                    tool_call_id=tool_call_id,
                    name=tool_name
                )
            
            # Pause slightly to prevent tight loop rate limiting
            time.sleep(0.5)
            
        # If we exit the loop without a final text response, raise an exception or return a warning
        warning_msg = "Maximum tool execution turns (15) reached. Aborting loop to prevent API exhaustion."
        logger.warning(warning_msg)
        self.conversation.add_message("assistant", content=warning_msg)
        return warning_msg

    def _execute_single_tool_without_confirm(self, tool, args: Dict[str, Any]) -> Any:
        """Executes a single tool and handles security and general exception borders."""
        try:
            # Run the tool (safety check path is already done inside the tool functions)
            result = tool.run(**args)
            logger.debug(f"Tool '{tool.name}' completed successfully.")
            return result
        except SecurityError as e:
            logger.warning(f"Security violation executing tool '{tool.name}': {e}")
            return f"Security Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error executing tool '{tool.name}': {e}", exc_info=True)
            return f"Error: {type(e).__name__} - {str(e)}"
            
    def learn_fact(self, fact: str) -> None:
        """Allows direct fact learning from outside the loop."""
        self.long_term_memory.add_fact(fact)
        
    def forget_fact(self, fact: str) -> None:
        """Allows deleting a fact from memory."""
        self.long_term_memory.remove_fact(fact)
