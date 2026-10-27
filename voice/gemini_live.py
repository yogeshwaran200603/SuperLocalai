"""
SuperLocal Voice Assistant: Gemini Live Provider Module
Implements real-time bidirectional audio streaming and function calling via the
Gemini Multimodal Live WebSocket API (BidiGenerateContent).
Automatically falls back to local pipeline on quota error, session limits, or model errors.
"""

import os
import json
import base64
import asyncio
from typing import Optional, Callable, Dict, Any, List

try:
    import websockets
except ImportError:
    websockets = None

from config import LIVE_MODEL, GEMINI_API_KEY
from providers.tool_converter import func_to_schema


class GeminiLiveFallbackError(Exception):
    """Raised when Gemini Live encounters a session limit, quota exhaustion, or model error requiring fallback."""
    pass


class GeminiLiveProvider:
    """
    Manages live bidirectional streaming connection with Gemini Multimodal Live API.
    """
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        tools: Optional[List[Callable]] = None,
        tool_executor: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
    ):
        self.api_key = api_key or GEMINI_API_KEY
        self.model = model or LIVE_MODEL
        self.tools = tools or []
        self.tool_executor = tool_executor

        self.ws = None
        self.is_connected = False
        self._stop_requested = False

    def build_setup_message(self) -> Dict[str, Any]:
        """Constructs the initial BidiGenerateContentSetup payload."""
        function_declarations = []
        for t in self.tools:
            try:
                schema = func_to_schema(t)
                fn = schema.get("function", {})
                params = fn.get("parameters", {})
                # Live API expects uppercase parameter types
                function_declarations.append({
                    "name": fn.get("name"),
                    "description": fn.get("description"),
                    "parameters": {
                        "type": "OBJECT",
                        "properties": params.get("properties", {}),
                        "required": params.get("required", []),
                    }
                })
            except Exception:
                pass

        setup_dict: Dict[str, Any] = {
            "model": f"models/{self.model}",
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": "Puck"
                        }
                    }
                }
            }
        }
        if function_declarations:
            setup_dict["tools"] = [{"functionDeclarations": function_declarations}]

        return {"setup": setup_dict}

    async def connect(self):
        """Establishes WebSocket connection and completes configuration handshake."""
        if not websockets:
            raise GeminiLiveFallbackError("The 'websockets' library is not available.")
        if not self.api_key:
            raise GeminiLiveFallbackError("GEMINI_API_KEY is not configured.")

        uri = (
            f"wss://generativelanguage.googleapis.com/ws/"
            f"google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={self.api_key}"
        )

        try:
            self.ws = await websockets.connect(uri, ping_interval=20, ping_timeout=20)
            setup_msg = self.build_setup_message()
            await self.ws.send(json.dumps(setup_msg))
            self.is_connected = True
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                reason = "Gemini Live daily/minute quota exhausted (429)."
            elif "404" in err_msg or "not found" in err_msg.lower():
                reason = f"Gemini Live model '{self.model}' not supported or not found."
            else:
                reason = f"Connection error: {err_msg}"
            raise GeminiLiveFallbackError(reason)

    async def send_audio_chunk(self, pcm_bytes: bytes):
        """Sends a 16kHz mono PCM audio chunk encoded as base64."""
        if not self.ws or not self.is_connected:
            return

        b64_data = base64.b64encode(pcm_bytes).decode("utf-8")
        msg = {
            "realtimeInput": {
                "mediaChunks": [
                    {
                        "mimeType": "audio/pcm;rate=16000",
                        "data": b64_data,
                    }
                ]
            }
        }
        await self.ws.send(json.dumps(msg))

    async def send_tool_response(self, call_id: str, output: Dict[str, Any]):
        """Sends function execution results back to the Live session."""
        if not self.ws or not self.is_connected:
            return

        msg = {
            "toolResponse": {
                "functionResponses": [
                    {
                        "response": {"output": output},
                        "id": call_id,
                    }
                ]
            }
        }
        await self.ws.send(json.dumps(msg))

    async def receive_events(self, on_audio_received: Optional[Callable[[bytes], None]] = None, on_interrupted: Optional[Callable[[], None]] = None):
        """Listens for streaming server events, handling audio playback, interruptions, and tool calls."""
        if not self.ws:
            return

        try:
            async for raw_msg in self.ws:
                data = json.loads(raw_msg)

                # 1. Handle Barge-in Interruption
                if data.get("serverContent", {}).get("interrupted"):
                    if on_interrupted:
                        on_interrupted()

                # 2. Handle Audio Playback Stream
                parts = data.get("serverContent", {}).get("modelTurn", {}).get("parts", [])
                for part in parts:
                    inline = part.get("inlineData", {})
                    if inline.get("data"):
                        pcm_audio = base64.b64decode(inline["data"])
                        if on_audio_received:
                            on_audio_received(pcm_audio)

                # 3. Handle Tool Calls
                tool_call = data.get("toolCall")
                if tool_call and self.tool_executor:
                    for fc in tool_call.get("functionCalls", []):
                        call_id = fc.get("id", "")
                        fn_name = fc.get("name", "")
                        fn_args = fc.get("args", {})
                        res = self.tool_executor(fn_name, fn_args)
                        await self.send_tool_response(call_id, res)

        except websockets.exceptions.ConnectionClosed as e:
            err_str = str(e)
            if "1000" not in err_str:
                raise GeminiLiveFallbackError(f"Live session ended: {err_str}")
        except Exception as e:
            raise GeminiLiveFallbackError(f"Live session error: {e}")

    async def close(self):
        """Gracefully closes WebSocket connection."""
        self.is_connected = False
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
