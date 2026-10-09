"""The Azure OpenAI Conversation integration."""

from __future__ import annotations

from types import MappingProxyType

import openai

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.httpx_client import get_async_client

from .const import (
    CONF_API_BASE,
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_REASONING_EFFORT,
    CONF_RECOMMENDED,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    CONF_WEB_SEARCH_INLINE_CITATIONS,
    DEFAULT_AI_TASK_NAME,
    DOMAIN,
    LOGGER,
    RECOMMENDED_AI_TASK_OPTIONS,
)

PLATFORMS = (Platform.AI_TASK, Platform.CONVERSATION, Platform.STT, Platform.TTS)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type OpenAIConfigEntry = ConfigEntry[openai.AsyncClient]

_LEGACY_CONF_SEND_SAMPLING_PARAMETERS = "send_sampling_parameters"
_LEGACY_CONF_STRIP_WEB_CITATIONS = "strip_web_citations"
_LEGACY_REASONING_EFFORT_DISABLED = "disabled"


def normalize_azure_endpoint(uri: str) -> str:
    """Normalize Azure OpenAI endpoint URI by ensuring it ends with /openai/v1/."""

    normalized = uri.rstrip("/")

    if not normalized.endswith("/openai/v1"):
        normalized += "/openai/v1"

    return normalized + "/"


def create_client(
    hass: HomeAssistant, api_base: str, api_key: str
) -> openai.AsyncOpenAI:
    """Create a client for the Azure OpenAI v1 API."""
    return openai.AsyncOpenAI(
        base_url=normalize_azure_endpoint(api_base),
        default_query={"api-version": "preview"},
        api_key=api_key,
        http_client=get_async_client(hass),
    )


async def async_setup_entry(hass: HomeAssistant, entry: OpenAIConfigEntry) -> bool:
    """Set up Azure OpenAI Conversation from a config entry."""
    client = create_client(hass, entry.data[CONF_API_BASE], entry.data[CONF_API_KEY])

    # Cache current platform data which gets added to each request
    # (caching done by library)
    _ = await hass.async_add_executor_job(client.platform_headers)

    try:
        await client.models.list(timeout=10.0)
    except openai.AuthenticationError as err:
        raise ConfigEntryAuthFailed(err) from err
    except openai.NotFoundError as err:
        # Some endpoints, such as API gateways, don't expose the models route
        LOGGER.warning("Unable to list models, continuing setup: %s", err)
    except openai.OpenAIError as err:
        raise ConfigEntryNotReady(err) from err

    entry.runtime_data = client

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: OpenAIConfigEntry) -> bool:
    """Unload Azure OpenAI."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(hass: HomeAssistant, entry: OpenAIConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: OpenAIConfigEntry) -> bool:
    """Migrate entry."""
    LOGGER.debug("Migrating from version %s:%s", entry.version, entry.minor_version)

    if entry.version > 2:
        # Downgrade from a future version
        return False

    if entry.version == 1:
        _migrate_options_to_subentries(hass, entry)

    LOGGER.debug(
        "Migration to version %s:%s successful", entry.version, entry.minor_version
    )

    return True


def _migrate_options_to_subentries(
    hass: HomeAssistant, entry: OpenAIConfigEntry
) -> None:
    """Move the conversation options of a version 1 entry into subentries."""
    options = dict(entry.options)
    # Normalize options introduced by unreleased version 1 builds.
    if options.get(CONF_REASONING_EFFORT) in (
        "",
        _LEGACY_REASONING_EFFORT_DISABLED,
    ):
        options[CONF_REASONING_EFFORT] = "none"
    if (
        strip_citations := options.pop(_LEGACY_CONF_STRIP_WEB_CITATIONS, None)
    ) is not None:
        options[CONF_WEB_SEARCH_INLINE_CITATIONS] = not strip_citations
    options.pop(_LEGACY_CONF_SEND_SAMPLING_PARAMETERS, None)

    conversation = ConfigSubentry(
        data=MappingProxyType(options),
        subentry_type="conversation",
        title=entry.title,
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(entry, conversation)

    entity_registry = er.async_get(hass)
    if entity_id := entity_registry.async_get_entity_id(
        "conversation", DOMAIN, entry.entry_id
    ):
        entity_registry.async_update_entity(
            entity_id,
            config_subentry_id=conversation.subentry_id,
            new_unique_id=conversation.subentry_id,
        )

    device_registry = dr.async_get(hass)
    if device := device_registry.async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    ):
        device_registry.async_update_device(
            device.id,
            new_identifiers={(DOMAIN, conversation.subentry_id)},
            new_config_subentry_id=conversation.subentry_id,
        )

    # Azure needs a deployment name, so reuse the one the agent already uses
    ai_task_options = dict(RECOMMENDED_AI_TASK_OPTIONS)
    if not options.get(CONF_RECOMMENDED) and CONF_CHAT_MODEL in options:
        ai_task_options = {
            CONF_RECOMMENDED: False,
            **{
                key: options[key]
                for key in (
                    CONF_CHAT_MODEL,
                    CONF_MAX_TOKENS,
                    CONF_TEMPERATURE,
                    CONF_TOP_P,
                    CONF_REASONING_EFFORT,
                )
                if key in options
            },
        }
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data=MappingProxyType(ai_task_options),
            subentry_type="ai_task_data",
            title=DEFAULT_AI_TASK_NAME,
            unique_id=None,
        ),
    )

    hass.config_entries.async_update_entry(
        entry, options={}, version=2, minor_version=1
    )
