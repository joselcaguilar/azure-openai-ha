"""Verify runtime setup, reload behavior, and preservation of legacy configuration."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from respx import MockRouter

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError

from custom_components.azure_openai_conversation import (
    async_create_entry_client,
    async_migrate_entry,
    create_client,
    create_deployment_client,
)
from custom_components.azure_openai_conversation.const import (
    AUTH_API_KEY,
    CONF_API_BASE,
    CONF_AUTH_TYPE,
    CONF_CHAT_MODEL,
    DOMAIN,
)

from .const import ENDPOINT


async def test_legacy_client_keeps_api_key(
    hass: HomeAssistant, respx_mock: MockRouter
) -> None:
    """Entries lacking the new authentication field must keep their existing API key."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_API_BASE: ENDPOINT, "api_key": "legacy-key"}
    )
    entry.add_to_hass(hass)
    route = respx_mock.get(f"{ENDPOINT}openai/v1/models").respond(
        json={"object": "list", "data": []}
    )
    client = await async_create_entry_client(hass, entry)
    await hass.async_add_executor_job(client.platform_headers)
    await client.models.list()
    assert route.calls[0].request.headers["Authorization"] == "Bearer legacy-key"


async def test_deployment_client_targets_deployment_route(
    hass: HomeAssistant, respx_mock: MockRouter
) -> None:
    """Deployment routes escape the name, keep the API key and leave v1 unchanged."""
    client = create_client(hass, ENDPOINT, "api-key")
    route = respx_mock.post(
        f"{ENDPOINT}openai/deployments/team%2Fstt/audio/transcriptions"
    ).respond(json={"text": "Hola"})
    await hass.async_add_executor_job(client.platform_headers)
    transcription = await create_deployment_client(
        client, "team/stt"
    ).audio.transcriptions.create(model="team/stt", file=("a.wav", b"RIFF"))
    assert transcription.text == "Hola"
    request = route.calls[0].request
    assert request.url.raw_path == (
        b"/openai/deployments/team%2Fstt/audio/transcriptions"
        b"?api-version=2025-04-01-preview"
    )
    assert request.headers["Authorization"] == "Bearer api-key"
    assert str(client.base_url) == f"{ENDPOINT}openai/v1/"
    assert client.default_query == {"api-version": "preview"}


async def test_unknown_authentication_is_not_an_api_key_fallback(
    hass: HomeAssistant,
) -> None:
    """An unsupported authentication method is a visible error, not a key fallback."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_AUTH_TYPE: "unknown",
            CONF_API_BASE: ENDPOINT,
            "api_key": "do-not-use",
        },
    )
    entry.add_to_hass(hass)
    with pytest.raises(ConfigEntryError, match="Unsupported"):
        await async_create_entry_client(hass, entry)


async def test_minor_migration_does_not_change_services(hass: HomeAssistant) -> None:
    """Mark API-key authentication explicitly while keeping legacy subentry IDs/options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_BASE: ENDPOINT, "api_key": "legacy-key"},
        version=2,
        minor_version=1,
        subentries_data=[
            {
                "subentry_type": "conversation",
                "title": "Keep my name",
                "unique_id": None,
                "data": {CONF_CHAT_MODEL: "custom-deployment", "prompt": "My prompt"},
            }
        ],
    )
    entry.add_to_hass(hass)
    original = dict(entry.subentries)
    assert await async_migrate_entry(hass, entry)
    assert entry.minor_version == 2
    assert entry.data[CONF_AUTH_TYPE] == AUTH_API_KEY
    assert entry.subentries == original


async def test_v1_migration_keeps_explicit_recommended_deployment(
    hass: HomeAssistant,
) -> None:
    """A stored deployment must survive migration even if recommended settings is enabled."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_BASE: ENDPOINT, "api_key": "legacy-key"},
        version=1,
        options={CONF_CHAT_MODEL: "ha-chat", "recommended": True, "prompt": "Keep me"},
    )
    entry.add_to_hass(hass)
    assert await async_migrate_entry(hass, entry)
    assert entry.version == 2
    assert entry.minor_version == 2
    assert len(entry.subentries) == 2
    assert all(
        subentry.data[CONF_CHAT_MODEL] == "ha-chat"
        for subentry in entry.subentries.values()
    )
