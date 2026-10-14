"""Constants for the Azure OpenAI Conversation Integration."""

import logging
from typing import Any

from homeassistant.const import CONF_LLM_HASS_API, CONF_PROMPT
from homeassistant.helpers import llm

DOMAIN = "azure_openai_conversation"
LOGGER: logging.Logger = logging.getLogger(__package__)

DEFAULT_CONVERSATION_NAME = "Azure OpenAI Conversation"
DEFAULT_AI_TASK_NAME = "Azure OpenAI AI Task"
DEFAULT_IMAGE_TASK_NAME = "Azure OpenAI Image Task"
DEFAULT_STT_NAME = "Azure OpenAI STT"
DEFAULT_TTS_NAME = "Azure OpenAI TTS"
DEFAULT_NAME = "Azure OpenAI Conversation"

CONF_API_BASE = "api_base"
CONF_AUTH_TYPE = "auth_type"
CONF_AUTO_DISCOVERED = "auto_discovered"
CONF_CHAT_MODEL = "chat_model"
CONF_CODE_INTERPRETER = "code_interpreter"
CONF_IMAGE_MODEL = "image_model"
CONF_IMAGE_QUALITY = "image_quality"
CONF_DEPLOYMENTS = "deployments"
CONF_MODEL_NAME = "model_name"
CONF_RESOURCE_ID = "resource_id"
CONF_TENANT_ID = "tenant_id"
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
AUTH_API_KEY = "api_key"
AUTH_ENTRA_ID = "entra_id"
INFERENCE_SCOPE = "https://cognitiveservices.azure.com/.default"
MANAGEMENT_SCOPE = "https://management.azure.com//.default"
RECOMMENDED_CODE_INTERPRETER = False
RECOMMENDED_CHAT_MODEL = "gpt-4o-mini"
RECOMMENDED_IMAGE_MODEL = "gpt-image-2.5-flare"
RECOMMENDED_IMAGE_QUALITY = "high"
RECOMMENDED_MAX_TOKENS = 3000
RECOMMENDED_PRO_MODE = False
RECOMMENDED_REASONING_EFFORT = "medium"
RECOMMENDED_REASONING_SUMMARY = "auto"
RECOMMENDED_SEND_SAMPLING_PARAMETERS = False
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
STT_MODELS: list[str] = [
    "gpt-transcribe",
    "gpt-4o-transcribe",
    "gpt-4o-mini-transcribe",
    "whisper",
]
TTS_MODELS: list[str] = ["gpt-4o-mini-tts", "tts", "tts-hd", "tts-1", "tts-1-hd"]

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


def get_reasoning_options(model: str) -> list[str]:
    """Return adjustable reasoning efforts supported by the underlying model."""
    if not model.startswith(("o", "gpt-5", "gpt-6")) or model.startswith("gpt-5-pro"):
        return []

    models_reasoning_map: dict[str | tuple[str, ...], list[str]] = {
        "gpt-6-luna": ["none", "low", "medium", "high", "xhigh", "max"],
        "gpt-6": ["low", "medium", "high", "xhigh", "max"],
        "gpt-5.6": ["none", "low", "medium", "high", "xhigh", "max"],
        ("gpt-5.2-pro", "gpt-5.4-pro", "gpt-5.5-pro"): ["medium", "high", "xhigh"],
        ("gpt-5.2", "gpt-5.3", "gpt-5.4", "gpt-5.5"): [
            "none",
            "low",
            "medium",
            "high",
            "xhigh",
        ],
        "gpt-5.1": ["none", "low", "medium", "high"],
        "gpt-5": ["minimal", "low", "medium", "high"],
        "": ["low", "medium", "high"],
    }
    for prefix, options in models_reasoning_map.items():
        if model.startswith(prefix):
            return options
    return []  # pragma: no cover


def get_recommended_reasoning_effort(model: str) -> str:
    """Use the preferred effort only where the model supports it."""
    if model.startswith("gpt-5-pro"):
        return "high"
    options = get_reasoning_options(model)
    if options and RECOMMENDED_REASONING_EFFORT not in options:  # pragma: no cover
        return options[0]
    return RECOMMENDED_REASONING_EFFORT


def get_image_quality_options(model: str) -> list[str]:
    """Return image quality levels supported by the underlying image model."""
    if model.startswith("gpt-image-2.5"):
        return ["low", "medium", "high", "xhigh", "max", "auto"]
    if model.startswith("gpt-image"):
        return ["low", "medium", "high"]
    # DALL-E 3 has been retired and DALL-E 2 accepts only its standard quality
    return []
