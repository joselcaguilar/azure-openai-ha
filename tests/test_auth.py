"""Verify native Microsoft browser OAuth and renewable inference authorization."""

import asyncio
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from respx import MockRouter

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryError,
    OAuth2TokenRequestConnectionError,
)

from custom_components.azure_openai_conversation import async_create_entry_client
from custom_components.azure_openai_conversation.auth import EntraOAuth2Implementation
from custom_components.azure_openai_conversation.const import (
    CONF_API_BASE,
    DOMAIN,
    INFERENCE_SCOPE,
    MANAGEMENT_SCOPE,
)

from .const import ENDPOINT, REDIRECT_URI, TENANT_ID


def test_pkce_and_static_consent(
    oauth_implementation: EntraOAuth2Implementation,
) -> None:
    """Keep independent verifiers and consent to both registered APIs with one scope."""
    first = oauth_implementation.with_tenant(TENANT_ID)
    second = oauth_implementation.with_tenant(TENANT_ID)
    first_data = first.extra_authorize_data
    assert first.code_verifier != second.code_verifier
    assert first.authorize_url == (
        f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/authorize"
    )
    assert first_data["code_challenge_method"] == "S256"
    assert first_data["scope"] == f"offline_access {INFERENCE_SCOPE}"
    assert MANAGEMENT_SCOPE not in first_data["scope"]
    assert first_data["prompt"] == "consent"
    assert first.service_domain == DOMAIN


async def test_authorization_code_redeems_inference_token(
    oauth_implementation: EntraOAuth2Implementation,
) -> None:
    """Redeem the PKCE code once, for inference only."""
    implementation = oauth_implementation.with_tenant(TENANT_ID)
    response = {
        "access_token": "inference-token",
        "expires_in": "3600",
        "refresh_token": "first-refresh",
    }
    with patch.object(
        implementation, "_token_request", return_value=response
    ) as request:
        token = await implementation.async_resolve_external_data(
            {"code": "authorization-code", "state": {"redirect_uri": REDIRECT_URI}}
        )

    assert token == response
    request.assert_awaited_once()
    data = request.await_args.args[0]
    assert data["grant_type"] == "authorization_code"
    assert data["code_verifier"] == implementation.code_verifier
    assert data["scope"] == f"offline_access {INFERENCE_SCOPE}"


async def test_refresh_rotates_only_the_inference_token(
    oauth_implementation: EntraOAuth2Implementation, oauth_data: dict
) -> None:
    """Persist the latest refresh token without requesting a management token."""
    with patch.object(
        oauth_implementation,
        "_token_request",
        return_value={
            "access_token": "new-inference",
            "expires_in": 600,
            "refresh_token": "rotated-refresh",
        },
    ) as request:
        token = await oauth_implementation.async_refresh_token(oauth_data["token"])
    request.assert_awaited_once_with(
        {
            "grant_type": "refresh_token",
            "refresh_token": "refresh-token",
            "scope": INFERENCE_SCOPE,
        }
    )
    assert token["access_token"] == "new-inference"
    assert token["refresh_token"] == "rotated-refresh"
    assert token["expires_in"] == 600


async def test_management_token_is_requested_on_demand_and_not_stored(
    oauth_implementation: EntraOAuth2Implementation, oauth_data: dict
) -> None:
    """Discovery gets a short-lived ARM token without changing the stored token."""
    stored = dict(oauth_data["token"])
    with patch.object(
        oauth_implementation,
        "_token_request",
        return_value={
            "access_token": "management-token",
            "expires_in": 3600,
            "refresh_token": "management-refresh",
        },
    ) as request:
        management_token = await oauth_implementation.async_get_management_token(
            oauth_data["token"]
        )
    assert management_token == "management-token"
    request.assert_awaited_once_with(
        {
            "grant_type": "refresh_token",
            "refresh_token": "refresh-token",
            "scope": MANAGEMENT_SCOPE,
        }
    )
    assert oauth_data["token"] == stored


async def test_missing_rotated_refresh_token_preserves_current(
    oauth_implementation: EntraOAuth2Implementation, oauth_data: dict
) -> None:
    """A provider that omits rotation must not erase the existing refresh token."""
    with patch.object(
        oauth_implementation,
        "_token_request",
        return_value={"access_token": "new-inference", "expires_in": 600},
    ):
        token = await oauth_implementation.async_refresh_token(oauth_data["token"])
    assert token["refresh_token"] == "refresh-token"


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"access_token": "token", "expires_in": "invalid"},
        {"access_token": "token", "expires_in": 0},
        {"access_token": 42, "expires_in": 3600},
        {"access_token": "", "expires_in": 3600},
        {"access_token": "token", "expires_in": 3600, "refresh_token": ""},
    ],
)
async def test_invalid_initial_tokens_fail_explicitly(
    oauth_implementation: EntraOAuth2Implementation, response: dict
) -> None:
    """Do not fabricate a successful OAuth session from an incomplete response."""
    with (
        patch.object(oauth_implementation, "_token_request", return_value=response),
        pytest.raises(OAuth2TokenRequestConnectionError),
    ):
        await oauth_implementation.async_resolve_external_data(
            {"code": "code", "state": {"redirect_uri": REDIRECT_URI}}
        )


async def test_empty_refresh_does_not_make_a_request(
    oauth_implementation: EntraOAuth2Implementation,
) -> None:
    """Reject a missing refresh token locally rather than sending invalid credentials."""
    with (
        patch.object(oauth_implementation, "_token_request") as request,
        pytest.raises(OAuth2TokenRequestConnectionError),
    ):
        await oauth_implementation.async_refresh_token({"refresh_token": None})
    request.assert_not_awaited()


async def test_oauth_client_refresh_is_shared(
    hass: HomeAssistant,
    oauth_data: dict,
    oauth_implementation: EntraOAuth2Implementation,
    respx_mock: MockRouter,
) -> None:
    """Concurrent SDK requests share Home Assistant's refresh lock and stored token."""
    entry = MockConfigEntry(domain=DOMAIN, data=oauth_data)
    entry.add_to_hass(hass)
    route = respx_mock.get(f"{ENDPOINT}openai/v1/models").respond(
        json={"object": "list", "data": []}
    )
    client = await async_create_entry_client(hass, entry)
    await hass.async_add_executor_job(client.platform_headers)
    await client.models.list()
    assert route.calls[-1].request.headers["Authorization"] == "Bearer inference-token"

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "token": {**entry.data["token"], "expires_at": 0}}
    )
    with patch.object(
        EntraOAuth2Implementation,
        "_token_request",
        return_value={
            "access_token": "new-inference",
            "expires_in": 3600,
            "refresh_token": "latest-refresh",
        },
    ) as refresh:
        await asyncio.gather(client.models.list(), client.models.list())

    refresh.assert_awaited_once()
    assert entry.data["token"]["refresh_token"] == "latest-refresh"
    assert all(
        call.request.headers["Authorization"] == "Bearer new-inference"
        for call in route.calls[1:]
    )


async def test_unsafe_stored_endpoint_rejected(
    hass: HomeAssistant, oauth_data: dict
) -> None:
    """Entra mode must not trust a manually edited API-gateway endpoint."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={**oauth_data, CONF_API_BASE: "https://attacker.example"}
    )
    entry.add_to_hass(hass)
    with pytest.raises(ConfigEntryError):
        await async_create_entry_client(hass, entry)


@pytest.mark.usefixtures("native_exposed_entities")
@pytest.mark.parametrize(
    ("status", "reauth"), [(400, True), (429, False), (503, False)]
)
async def test_refresh_failure_uses_native_reauth_or_retry_without_key_fallback(
    hass: HomeAssistant,
    oauth_data: dict,
    oauth_implementation: EntraOAuth2Implementation,
    aioclient_mock,
    respx_mock: MockRouter,
    status: int,
    reauth: bool,
) -> None:
    """Revocation triggers account linking; transient failures retry without using a key."""
    data = {
        **oauth_data,
        "api_key": "must-not-be-used",
        "token": {**oauth_data["token"], "expires_at": 0},
    }
    entry = MockConfigEntry(domain=DOMAIN, data=data, version=2, minor_version=2)
    entry.add_to_hass(hass)
    aioclient_mock.post(
        f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
        status=status,
        json={"error": "invalid_grant" if reauth else "temporarily_unavailable"},
    )
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is (
        ConfigEntryState.SETUP_ERROR if reauth else ConfigEntryState.SETUP_RETRY
    )
    flows = hass.config_entries.flow.async_progress()
    assert bool(flows) is reauth
    if reauth:
        assert len(flows) == 1
        assert flows[0]["context"]["source"] == "reauth"
        assert flows[0]["context"]["entry_id"] == entry.entry_id
    assert not respx_mock.calls
    assert entry.data == data
