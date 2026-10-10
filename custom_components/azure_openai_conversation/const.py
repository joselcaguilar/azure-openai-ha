"""Constants for the Azure OpenAI Conversation Integration."""

import logging
from typing import Any

from homeassistant.const import CONF_LLM_HASS_API, CONF_PROMPT
from homeassistant.helpers import llm

DOMAIN = "azure_openai_conversation"
LOGGER: logging.Logger = logging.getLogger(__package__)

DEFAULT_CONVERSATION_NAME = "Azure OpenAI Conversation"
DEFAULT_AI_TASK_NAME = "Azure OpenAI AI Task"
DEFAULT_STT_NAME = "Azure OpenAI STT"
DEFAULT_TTS_NAME = "Azure OpenAI TTS"
DEFAULT_NAME = "Azure OpenAI Conversation"

CONF_API_BASE = "api_base"
CONF_CHAT_MODEL = "chat_model"
CONF_CODE_INTERPRETER = "code_interpreter"
CONF_IMAGE_MODEL = "image_model"
CONF_MAX_TOKENS = "max_tokens"
CONF_PRO_MODE = "pro_mode"
CONF_REASONING_EFFORT = "reasoning_effort"
CONF_REASONING_SUMMARY = "reasoning_summary"
CONF_RECOMMENDED = "recommended"
CONF_SEND_SAMPLING_PARAMETERS = "send_sampling_parameters"
CONF_STORE_RESPONSES = "store_responses"
CONF_TEMPERATURE = "temperature"
CONF_TOP_P = "top_p"
CONF_TTS_SPEED = "tts_speed"
CONF_VERBOSITY = "verbosity"
CONF_WEB_SEARCH = "web_search"
CONF_WEB_SEARCH_USER_LOCATION = "user_location"
CONF_WEB_SEARCH_CONTEXT_SIZE = "search_context_size"
CONF_WEB_SEARCH_CITY = "city"
CONF_WEB_SEARCH_REGION = "region"
CONF_WEB_SEARCH_COUNTRY = "country"
CONF_WEB_SEARCH_TIMEZONE = "timezone"
CONF_WEB_SEARCH_INLINE_CITATIONS = "inline_citations"
RECOMMENDED_CODE_INTERPRETER = False
RECOMMENDED_CHAT_MODEL = "gpt-4o-mini"
RECOMMENDED_IMAGE_MODEL = "gpt-image-2.5-flare"
RECOMMENDED_MAX_TOKENS = 3000
RECOMMENDED_PRO_MODE = False
RECOMMENDED_REASONING_EFFORT = "low"
RECOMMENDED_REASONING_SUMMARY = "auto"
RECOMMENDED_SEND_SAMPLING_PARAMETERS = True
RECOMMENDED_STORE_RESPONSES = False
RECOMMENDED_STT_MODEL = "gpt-4o-mini-transcribe"
RECOMMENDED_TEMPERATURE = 1.0
RECOMMENDED_TOP_P = 1.0
RECOMMENDED_TTS_MODEL = "gpt-4o-mini-tts"
RECOMMENDED_TTS_SPEED = 1.0
RECOMMENDED_VERBOSITY = "medium"
RECOMMENDED_WEB_SEARCH = False
RECOMMENDED_WEB_SEARCH_CONTEXT_SIZE = "medium"
RECOMMENDED_WEB_SEARCH_USER_LOCATION = False
RECOMMENDED_WEB_SEARCH_INLINE_CITATIONS = False
DEFAULT_STT_PROMPT = (
    "The following conversation is a smart home user talking to Home Assistant."
)

# Model names are only suggestions: Azure expects the deployment name.
IMAGE_MODELS: list[str] = [
    "gpt-image-2.5-sunburst",
    "gpt-image-2.5-flare",
    "gpt-image-2",
    "gpt-image-1.5",
    "gpt-image-1",
    "gpt-image-1-mini",
]
STT_MODELS: list[str] = ["gpt-4o-transcribe", "gpt-4o-mini-transcribe", "whisper"]
TTS_MODELS: list[str] = ["gpt-4o-mini-tts", "tts-1", "tts-1-hd"]

UNSUPPORTED_MODELS: list[str] = [
    "o1-mini",
    "o1-mini-2024-09-12",
    "o1-preview",
    "o1-preview-2024-09-12",
    "gpt-4o-realtime-preview",
    "gpt-4o-realtime-preview-2024-12-17",
    "gpt-4o-realtime-preview-2024-10-01",
    "gpt-4o-mini-realtime-preview",
    "gpt-4o-mini-realtime-preview-2024-12-17",
]

UNSUPPORTED_WEB_SEARCH_MODELS: list[str] = [
    "gpt-3.5",
    "gpt-4-turbo",
    "gpt-4.1-nano",
    "o1",
    "o3-mini",
]

UNSUPPORTED_CODE_INTERPRETER_MODELS: list[str] = [
    "gpt-5-pro",
    "gpt-5.2-pro",
    "gpt-5-codex",
    "gpt-5.1-codex",
    "gpt-5.2-codex",
]

RECOMMENDED_CONVERSATION_OPTIONS = {
    CONF_RECOMMENDED: True,
    CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
    CONF_PROMPT: llm.DEFAULT_INSTRUCTIONS_PROMPT,
}
RECOMMENDED_AI_TASK_OPTIONS = {
    CONF_RECOMMENDED: True,
}
RECOMMENDED_STT_OPTIONS: dict[str, Any] = {}
RECOMMENDED_TTS_OPTIONS = {
    CONF_PROMPT: "",
    CONF_CHAT_MODEL: RECOMMENDED_TTS_MODEL,
}
