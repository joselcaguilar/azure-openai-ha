"""Diagnostics support for Azure OpenAI Conversation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from openai import __title__, __version__

from homeassistant.const import CONF_PROMPT
from homeassistant.core import HomeAssistant

from .const import (
    AUTH_API_KEY,
    CONF_AUTH_TYPE,
    CONF_DEPLOYMENTS,
    CONF_WEB_SEARCH_CITY,
    CONF_WEB_SEARCH_COUNTRY,
    CONF_WEB_SEARCH_REGION,
    CONF_WEB_SEARCH_TIMEZONE,
)

if TYPE_CHECKING:
    from . import OpenAIConfigEntry

TO_OMIT = {
    CONF_PROMPT,
    CONF_WEB_SEARCH_CITY,
    CONF_WEB_SEARCH_COUNTRY,
    CONF_WEB_SEARCH_REGION,
    CONF_WEB_SEARCH_TIMEZONE,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OpenAIConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Only allowlisted entry data is read, so the endpoint, API key, tokens and
    Azure resource IDs are never included.
    """
    return {
        "client": f"{__title__}=={__version__}",
        "entry_version": f"{entry.version}.{entry.minor_version}",
        "state": entry.state.value,
        "auth_type": entry.data.get(CONF_AUTH_TYPE, AUTH_API_KEY),
        "deployments": [
            {
                key: deployment[key]
                for key in ("name", "model_name", "services", "unsupported_reason")
            }
            for deployment in entry.data.get(CONF_DEPLOYMENTS, [])
        ],
        "subentries": [
            {
                "title": subentry.title,
                "subentry_type": subentry.subentry_type,
                "data": {
                    key: value
                    for key, value in subentry.data.items()
                    if key not in TO_OMIT
                },
            }
            for subentry in entry.subentries.values()
        ],
    }
