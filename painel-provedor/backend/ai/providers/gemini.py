"""Gemini via API nativa (google-genai).

Chaves novas do AI Studio (`AQ.…`) falham no endpoint OpenAI-compatible
(`Authorization: Bearer` → 401 ACCESS_TOKEN_TYPE_UNSUPPORTED).
Usamos `google.genai` com `x-goog-api-key` e mantemos a interface
`client.chat.completions.create` esperada pelo ai.service.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from ai.providers.base import BaseAIProvider


def _openai_tools_to_gemini(tools: Optional[List[Dict[str, Any]]]) -> Optional[List[types.Tool]]:
    if not tools:
        return None
    declarations = []
    for t in tools:
        fn = (t or {}).get("function") or {}
        name = (fn.get("name") or "").strip()
        if not name:
            continue
        params = fn.get("parameters") or {"type": "object", "properties": {}}
        declarations.append(
            types.FunctionDeclaration(
                name=name,
                description=fn.get("description") or "",
                parameters=params,
            )
        )
    if not declarations:
        return None
    return [types.Tool(function_declarations=declarations)]


def _tool_choice_config(tool_choice: Any) -> Optional[types.ToolConfig]:
    if tool_choice is None or tool_choice == "auto":
        return types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.AUTO,
            )
        )
    if tool_choice == "none":
        return types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.NONE,
            )
        )
    if tool_choice == "required":
        return types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.ANY,
            )
        )
    if isinstance(tool_choice, dict):
        name = ((tool_choice.get("function") or {}).get("name") or "").strip()
        if name:
            return types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode=types.FunctionCallingConfigMode.ANY,
                    allowed_function_names=[name],
                )
            )
    return None


def _messages_to_gemini(messages: List[Dict[str, Any]]):
    system_chunks: List[str] = []
    contents: List[types.Content] = []
    call_id_to_name: Dict[str, str] = {}

    for msg in messages or []:
        role = (msg or {}).get("role")
        content = (msg or {}).get("content")

        if role == "system":
            text = (content or "").strip()
            if text:
                system_chunks.append(text)
            continue

        if role == "user":
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=content or "")],
                )
            )
            continue

        if role == "assistant":
            parts: List[types.Part] = []
            if content:
                parts.append(types.Part.from_text(text=str(content)))
            for tc in (msg.get("tool_calls") or []):
                tc_id = tc.get("id") or f"call_{uuid.uuid4().hex[:20]}"
                fn = tc.get("function") or {}
                name = (fn.get("name") or "").strip()
                if not name:
                    continue
                call_id_to_name[tc_id] = name
                args_raw = fn.get("arguments") or "{}"
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
                except json.JSONDecodeError:
                    args = {}
                if not isinstance(args, dict):
                    args = {"value": args}
                parts.append(types.Part.from_function_call(name=name, args=args))
            if parts:
                contents.append(types.Content(role="model", parts=parts))
            continue

        if role == "tool":
            tc_id = msg.get("tool_call_id") or ""
            name = call_id_to_name.get(tc_id) or "tool"
            raw = content if content is not None else "{}"
            try:
                response_data = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                response_data = {"result": raw}
            if not isinstance(response_data, dict):
                response_data = {"result": response_data}
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name=name,
                            response=response_data,
                        )
                    ],
                )
            )

    system_instruction = "\n\n".join(system_chunks) if system_chunks else None
    return system_instruction, contents


def _response_to_openai(response) -> SimpleNamespace:
    text_bits: List[str] = []
    tool_calls: List[SimpleNamespace] = []

    candidates = getattr(response, "candidates", None) or []
    if candidates:
        content = getattr(candidates[0], "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            text = getattr(part, "text", None)
            if text:
                text_bits.append(text)
            fc = getattr(part, "function_call", None)
            if fc and getattr(fc, "name", None):
                args = dict(fc.args) if getattr(fc, "args", None) else {}
                tool_calls.append(
                    SimpleNamespace(
                        id=f"call_{uuid.uuid4().hex[:24]}",
                        type="function",
                        function=SimpleNamespace(
                            name=fc.name,
                            arguments=json.dumps(args, ensure_ascii=False),
                        ),
                    )
                )

    # Fallback: response.text (quando sem candidates/parts tipados)
    if not text_bits and not tool_calls:
        fallback = (getattr(response, "text", None) or "").strip()
        if fallback:
            text_bits.append(fallback)

    message = SimpleNamespace(
        content="\n".join(text_bits).strip() or None,
        tool_calls=tool_calls or None,
    )
    usage_meta = getattr(response, "usage_metadata", None)
    usage = None
    if usage_meta:
        usage = SimpleNamespace(
            prompt_tokens=getattr(usage_meta, "prompt_token_count", None),
            completion_tokens=getattr(usage_meta, "candidates_token_count", None),
            total_tokens=getattr(usage_meta, "total_token_count", None),
        )
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


class _GeminiChatCompletions:
    def __init__(self, api_key: str, default_model: str):
        self._client = genai.Client(api_key=api_key)
        self._default_model = default_model

    def create(self, **kwargs):
        model = kwargs.get("model") or self._default_model
        messages = kwargs.get("messages") or []
        tools = kwargs.get("tools")
        tool_choice = kwargs.get("tool_choice", "auto")
        temperature = kwargs.get("temperature")
        max_tokens = kwargs.get("max_tokens")

        system_instruction, contents = _messages_to_gemini(messages)
        if not contents:
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="")],
                )
            ]

        gemini_tools = _openai_tools_to_gemini(tools)
        config_kwargs: Dict[str, Any] = {
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if temperature is not None:
            config_kwargs["temperature"] = temperature
        if max_tokens is not None:
            config_kwargs["max_output_tokens"] = max_tokens
        if gemini_tools:
            config_kwargs["tools"] = gemini_tools
            tool_cfg = _tool_choice_config(tool_choice)
            if tool_cfg:
                config_kwargs["tool_config"] = tool_cfg

        response = self._client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        return _response_to_openai(response)


class _GeminiOpenAICompatClient:
    """Espelha o mínimo da superfície OpenAI usada em ai.service."""

    def __init__(self, api_key: str, default_model: str):
        self.chat = SimpleNamespace(
            completions=_GeminiChatCompletions(api_key, default_model)
        )


class GeminiProvider(BaseAIProvider):
    provider_name = "gemini"

    def client(self):
        if not self.api_key:
            return None
        return _GeminiOpenAICompatClient(self.api_key, self.model)
