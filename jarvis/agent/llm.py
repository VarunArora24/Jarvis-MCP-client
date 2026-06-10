import os
import json
import time
import re
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types as gemini_types
from google.genai.errors import APIError as GeminiAPIError
from openai import OpenAI
from openai import OpenAIError

from jarvis.config import settings
from jarvis.utils.logging import logger

def _dict_to_schema(d: Dict[str, Any]) -> gemini_types.Schema:
    """Recursively converts a standard JSON Schema dictionary to a Gemini types.Schema object."""
    if not isinstance(d, dict):
        return d
        
    properties = {}
    if "properties" in d:
        for k, v in d["properties"].items():
            properties[k] = _dict_to_schema(v)
            
    items = None
    if "items" in d:
        items = _dict_to_schema(d["items"])
        
    # Standardize types to uppercase strings as expected by the Gemini API
    schema_type = d.get("type", "STRING").upper()
    if schema_type == "INT":
        schema_type = "INTEGER"
    elif schema_type == "FLOAT":
        schema_type = "NUMBER"
    elif schema_type == "STR":
        schema_type = "STRING"
    elif schema_type == "BOOL":
        schema_type = "BOOLEAN"
    elif schema_type == "DICT":
        schema_type = "OBJECT"
    elif schema_type == "LIST":
        schema_type = "ARRAY"
        
    return gemini_types.Schema(
        type=schema_type,
        description=d.get("description"),
        properties=properties if properties else None,
        required=d.get("required"),
        items=items
    )


def try_parse_json_tool_call(text: str) -> Optional[List[Dict[str, Any]]]:
    """Tries to extract and parse a tool call from the text if it is formatted as JSON."""
    clean_text = text.strip()
    
    # Remove markdown code block wraps if present (e.g. ```json ... ```)
    if clean_text.startswith("```"):
        lines = clean_text.splitlines()
        if len(lines) >= 3:
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            clean_text = "\n".join(lines).strip()
            
    try:
        data = json.loads(clean_text)
        # Check if it's a dictionary representing a tool call
        if isinstance(data, dict):
            name = data.get("name") or data.get("function") or data.get("tool")
            args = data.get("arguments") or data.get("parameters") or data.get("args") or {}
            
            if name and isinstance(name, str):
                return [{
                    "id": f"parsed_{int(time.time())}",
                    "name": name,
                    "arguments": args
                }]
        # Check if it's a list of tool calls
        elif isinstance(data, list):
            calls = []
            for item in data:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("function") or item.get("tool")
                    args = item.get("arguments") or item.get("parameters") or item.get("args") or {}
                    if name and isinstance(name, str):
                        calls.append({
                            "id": f"parsed_{len(calls)}_{int(time.time())}",
                            "name": name,
                            "arguments": args
                        })
            if calls:
                return calls
    except Exception:
        pass
    return None


def extract_and_parse_tool_calls(text: str) -> Optional[List[Dict[str, Any]]]:
    if not text:
        return None
        
    # First try parsing the entire text as a single JSON
    parsed = try_parse_json_tool_call(text)
    if parsed:
        return parsed
        
    # Extract all top-level balanced curly-brace blocks {...}
    blocks = []
    stack = 0
    start = -1
    for i, char in enumerate(text):
        if char == "{":
            if stack == 0:
                start = i
            stack += 1
        elif char == "}":
            if stack > 0:
                stack -= 1
                if stack == 0:
                    blocks.append(text[start:i+1])
                    
    calls = []
    for block in blocks:
        parsed_block = try_parse_json_tool_call(block)
        if parsed_block:
            calls.extend(parsed_block)
            
    if calls:
        return calls
        
    return None


def _strip_json_from_text(text: str) -> Optional[str]:
    """Helper to remove JSON blocks or curly-bracket contents from the text response to avoid rendering it to the user."""
    if not text:
        return text
        
    # If the text is a valid JSON dict/list on its own, strip it completely
    try:
        data = json.loads(text.strip())
        if isinstance(data, (dict, list)):
            return None
    except Exception:
        pass
        
    # Extract all top-level balanced curly-brace blocks {...}
    blocks = []
    stack = 0
    start = -1
    for i, char in enumerate(text):
        if char == "{":
            if stack == 0:
                start = i
            stack += 1
        elif char == "}":
            if stack > 0:
                stack -= 1
                if stack == 0:
                    blocks.append((start, i+1))
                    
    # Rebuild text, excluding valid JSON blocks
    cleaned = text
    for start_idx, end_idx in reversed(blocks):
        try:
            # Check if this block is actually valid JSON before stripping
            json.loads(text[start_idx:end_idx])
            cleaned = cleaned[:start_idx] + cleaned[end_idx:]
        except Exception:
            pass
            
    # Remove empty code blocks or stray formatting leftovers
    cleaned = re.sub(r"```(?:json)?\s*```", "", cleaned)
    cleaned = cleaned.strip()
    return cleaned if cleaned else None


class LLMResponse:
    """Standardized response from the LLM, containing optional text and/or tool calls."""
    def __init__(self, text: Optional[str] = None, tool_calls: Optional[List[Dict[str, Any]]] = None):
        self.text = text
        self.tool_calls = tool_calls  # List of dicts: [{"id": "...", "name": "...", "arguments": {...}}]


class LLMClient:
    """Unified client that routes content generation requests to Gemini or OpenAI-compatible LLMs."""
    def __init__(self):
        self.provider = settings.llm_provider.lower()
        self.model_name = settings.llm_model
        
        logger.info(f"Initializing LLM Client with provider: '{self.provider}', model: '{self.model_name}'")
        
        if self.provider == "gemini":
            if not settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is not set in environment or config.")
            self.gemini_client = genai.Client(api_key=settings.gemini_api_key)
        else:
            # Setup OpenAI-compatible client (ollama, groq, openai, openrouter)
            self.openai_client = OpenAI(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key
            )

    def generate_content(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Any],
        system_instruction: str
    ) -> LLMResponse:
        """Invokes the selected model provider to generate content with tools."""
        if self.provider == "gemini":
            return self._generate_gemini(messages, tools, system_instruction)
        else:
            return self._generate_openai(messages, tools, system_instruction)

    def _generate_gemini(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Any],
        system_instruction: str
    ) -> LLMResponse:
        # 1. Map generic message history to Gemini types
        gemini_messages = []
        for msg in messages:
            role = msg["role"]
            if role == "user":
                gemini_messages.append(
                    gemini_types.Content(role="user", parts=[gemini_types.Part.from_text(text=msg["content"])])
                )
            elif role == "assistant":
                if "tool_calls" in msg and msg["tool_calls"]:
                    parts = [
                        gemini_types.Part(
                            function_call=gemini_types.FunctionCall(
                                name=tc["name"],
                                args=tc["arguments"]
                            )
                        ) for tc in msg["tool_calls"]
                    ]
                    gemini_messages.append(gemini_types.Content(role="model", parts=parts))
                else:
                    gemini_messages.append(
                        gemini_types.Content(role="model", parts=[gemini_types.Part.from_text(text=msg.get("content", ""))])
                    )
            elif role == "tool":
                gemini_messages.append(
                    gemini_types.Content(
                        role="tool",
                        parts=[
                            gemini_types.Part(
                                function_response=gemini_types.FunctionResponse(
                                    name=msg["name"],
                                    response={"result": msg["content"]}
                                )
                            )
                        ]
                    )
                )

        # 2. Convert tools schema to Gemini
        gemini_tools = []
        if tools:
            declarations = []
            for tool in tools:
                schema = tool.get_gemini_schema()
                params_dict = schema.get("parameters", {})
                gemini_params = _dict_to_schema(params_dict)
                declarations.append(
                    gemini_types.FunctionDeclaration(
                        name=tool.name,
                        description=tool.description,
                        parameters=gemini_params
                    )
                )
            gemini_tools = [gemini_types.Tool(function_declarations=declarations)]

        # 3. Call Gemini
        config = gemini_types.GenerateContentConfig(
            tools=gemini_tools if gemini_tools else None,
            system_instruction=system_instruction,
            temperature=0.2
        )

        response = self.gemini_client.models.generate_content(
            model=self.model_name,
            contents=gemini_messages,
            config=config
        )

        # 4. Parse responses
        function_calls = response.function_calls
        tool_calls = None
        text = response.text
        
        if function_calls:
            tool_calls = []
            for i, call in enumerate(function_calls):
                tool_calls.append({
                    "id": f"call_{i}_{int(time.time())}",
                    "name": call.name,
                    "arguments": call.args or {}
                })
        elif text:
            # Fallback parsing
            tool_calls = extract_and_parse_tool_calls(text)
            if tool_calls:
                text = _strip_json_from_text(text)

        return LLMResponse(
            text=text,
            tool_calls=tool_calls
        )

    def _generate_openai(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Any],
        system_instruction: str
    ) -> LLMResponse:
        # 1. Map generic message history to OpenAI types
        openai_messages = []
        
        # Prepend system instruction
        openai_messages.append({"role": "system", "content": system_instruction})
        
        for msg in messages:
            role = msg["role"]
            if role == "user":
                openai_messages.append({"role": "user", "content": msg["content"]})
            elif role == "assistant":
                if "tool_calls" in msg and msg["tool_calls"]:
                    openai_messages.append({
                        "role": "assistant",
                        "content": msg.get("content"),
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": json.dumps(tc["arguments"])
                                }
                            } for tc in msg["tool_calls"]
                        ]
                    })
                else:
                    openai_messages.append({"role": "assistant", "content": msg.get("content", "")})
            elif role == "tool":
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "name": msg["name"],
                    "content": str(msg["content"])
                })

        # 2. Map tools schema to OpenAI
        openai_tools = []
        if tools:
            for tool in tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters_schema
                    }
                })

        # 3. Call OpenAI/Ollama/Groq
        kwargs = {
            "model": self.model_name,
            "messages": openai_messages,
            "temperature": 0.2
        }
        if openai_tools:
            kwargs["tools"] = openai_tools

        response = self.openai_client.chat.completions.create(**kwargs)
        
        # 4. Parse responses
        choice = response.choices[0]
        assistant_msg = choice.message
        
        text = assistant_msg.content
        tool_calls = None
        
        if assistant_msg.tool_calls:
            tool_calls = []
            for tc in assistant_msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
                except Exception as e:
                    logger.error(f"Failed to parse tool call arguments JSON: {e}")
                    args = {}
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": args
                })
        elif text:
            # Fallback parser for models that output tool calls as JSON in text content
            tool_calls = extract_and_parse_tool_calls(text)
            if tool_calls:
                text = _strip_json_from_text(text)

        return LLMResponse(
            text=text,
            tool_calls=tool_calls
        )
