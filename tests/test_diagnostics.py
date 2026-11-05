"""Verify diagnostics never expose Azure credentials or personal settings."""

import json

from pytest_homeassistant.common import MockConfigEntry

from homeassistant.const import CONF_API_KEY, CONF_PROMPT
from homeassistant.core import HomeAssistant

from custom_components.azure_openai_conversation.const import (
    CONF_CHAT_MODEL,
    CONF_DEPLOYMENTS,
    CONF_WEB_SEARCH,
    CONF_WEB_SEARCH_CITY,
    CONF_WEB_SEARCH_COUNTRY,
    CONF_WEB_SEARCH_REGION,
    CONF_WEB_SEARCH_TIMEZONE,
    DOMAIN,
)
from custom_components.azure_openai_conversation.deployments import DeploymentData
from custom_components.azure_openai_conversation.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .const import ENDPOINT, RESOURCE_ID, TENANT_ID


async def test_diagnostics_omit_secrets_and_personal_settings(
    hass: HomeAssistant,
    oauth_data: dict,
    deployment_inventory: list[DeploymentData],
) -> None:
    """Keys, tokens, Azure IDs, instructions and the home location stay private."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            **oauth_data,
            CONF_API_KEY: "secret-key",
            CONF_DEPLOYMENTS: deployment_inventory,
        },
        version=2,
        minor_version=3,
        subentries_data=[
            {
                "subentry_type": "conversation",
                "title": "Assistant",
                "unique_id": None,
                "data": {
                    CONF_CHAT_MODEL: "ha-chat",
                    CONF_PROMPT: "Private instructions",
                    CONF_WEB_SEARCH: True,
                    CONF_WEB_SEARCH_CITY: "Seville",
                    CONF_WEB_SEARCH_REGION: "Andalusia",
                    CONF_WEB_SEARCH_COUNTRY: "ES",
                    CONF_WEB_SEARCH_TIMEZONE: "Europe/Madrid",
                },
            }
        ],
    )
    entry.add_to_hass(hass)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    rendered = json.dumps(diagnostics)
    for private in (
        "inference-token",
        "refresh-token",
        "secret-key",
        ENDPOINT,
        RESOURCE_ID,
        TENANT_ID,
        "Private instructions",
        "Seville",
        "Andalusia",
        "Europe/Madrid",
    ):
        assert private not in rendered
    assert diagnostics["client"].startswith("openai==")
    assert diagnostics["entry_version"] == "2.3"
    assert diagnostics["auth_type"] == "entra_id"
    assert diagnostics["deployments"][0] == {
        "name": "ha-chat",
        "model_name": "gpt-6.1-sol",
        "services": ["conversation", "ai_task_data"],
        "unsupported_reason": "",
    }
    assert diagnostics["subentries"] == [
        {
            "title": "Assistant",
            "subentry_type": "conversation",
            "data": {CONF_CHAT_MODEL: "ha-chat", CONF_WEB_SEARCH: True},
        }
    ]
