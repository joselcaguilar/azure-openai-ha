"""Exercise native setup, browser OAuth, reauthentication, and service configuration."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock, PropertyMock, patch
from urllib.parse import parse_qs, urlsplit
import base64
import hashlib
import json
import string

import httpx
import openai
import probatio
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from respx import MockRouter

from homeassistant.components import application_credentials
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import OAuth2TokenRequestReauthError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.translation import async_get_translations

from custom_components.azure_openai_conversation.auth import EntraOAuth2Implementation
from custom_components.azure_openai_conversation import async_create_entry_client
from custom_components.azure_openai_conversation.const import (
    AUTH_API_KEY,
    AUTH_ENTRA_ID,
    CONF_API_BASE,
    CONF_AUTH_TYPE,
    CONF_CHAT_MODEL,
    CONF_DEPLOYMENTS,
    CONF_IMAGE_MODEL,
    CONF_MODEL_NAME,
    CONF_REASONING_EFFORT,
    CONF_RESOURCE_ID,
    CONF_SEND_SAMPLING_PARAMETERS,
    CONF_TEMPERATURE,
    CONF_TENANT_ID,
    CONF_TOP_P,
    DOMAIN,
)
from custom_components.azure_openai_conversation.deployments import (
    DeploymentData,
    DeploymentDiscovery,
    DeploymentDiscoveryError,
    deployment_subentries,
)

from .const import ENDPOINT, REDIRECT_URI, RESOURCE_ID, TENANT_ID

CONFIG_FLOW = "custom_components.azure_openai_conversation.config_flow"
INTEGRATION = Path(__file__).parents[1] / "custom_components" / DOMAIN
LANGUAGES = ["en", "de", "es", "fr", "nl", "pl", "pt", "sk", "zh-Hant"]
DISCOVERY_SERVICES = ("conversation", "ai_task_data", "ai_task_image", "stt", "tts")
MANAGEMENT_TOKEN_RESPONSE = {"access_token": "management-token", "expires_in": 3600}
MALFORMED_TOKEN = {"access_token": "do-not-log-this-token", "expires_in": "invalid"}
pytestmark = pytest.mark.usefixtures("native_exposed_entities")


def _form_fields(result: dict) -> dict[str, dict]:
    """Serialize fields through the same native serializer used by config-flow HTTP."""
    return {
        field["name"]: field
        for field in probatio.to_field_list(
            result["data_schema"], custom_serializer=cv.custom_serializer
        )
    }


def _flatten(data: dict, prefix: str = "") -> dict[str, str]:
    """Flatten nested translation keys the way Home Assistant does."""
    flat: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{prefix}{key}."))
        else:
            flat[f"{prefix}{key}"] = value
    return flat


def _strings(name: str) -> dict[str, str]:
    """Load flattened strings.json or one shipped translation file."""
    path = INTEGRATION / (
        "strings.json" if name == "strings" else f"translations/{name}.json"
    )
    return _flatten(json.loads(path.read_text(encoding="utf-8")))


def _placeholders(value: str) -> set[str]:
    """Collect placeholders exactly as Home Assistant validates localized strings."""
    return {
        field for _, field, _, _ in string.Formatter().parse(value) if field is not None
    }


def _assert_description_placeholders(result: dict) -> None:
    """Supply every placeholder the step's text uses, or the frontend cannot render it."""
    prefix = f"config.step.{result['step_id']}."
    used = {
        placeholder
        for key, value in _strings("en").items()
        if key.startswith(prefix)
        for placeholder in _placeholders(value)
    }
    assert used <= set(result["description_placeholders"] or {})


async def _authorize(
    hass: HomeAssistant,
    result: dict,
    token_responses: list[dict | Exception] | None = None,
) -> dict:
    """Complete the native browser callback without contacting Microsoft."""
    if result["step_id"] == "pick_implementation":
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"implementation": DOMAIN}
        )
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    query = parse_qs(urlsplit(result["url"]).query)
    assert f"/{TENANT_ID}/" in result["url"]
    assert query["code_challenge_method"] == ["S256"]
    with patch.object(
        EntraOAuth2Implementation,
        "_token_request",
        side_effect=token_responses
        if token_responses is not None
        else [
            {
                "access_token": "inference-token",
                "refresh_token": "first-refresh",
                "expires_in": 3600,
            },
            MANAGEMENT_TOKEN_RESPONSE,
        ],
    ) as request:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"code": "authorization-code", "state": {"redirect_uri": REDIRECT_URI}},
        )
        assert result["type"] is FlowResultType.EXTERNAL_STEP_DONE
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
    verifier = request.await_args_list[0].args[0]["code_verifier"]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    assert challenge.decode().rstrip("=") == query["code_challenge"][0]
    return result


async def test_api_key_setup(hass: HomeAssistant, mock_setup_entry: AsyncMock) -> None:
    """Keep the legacy API-key setup available behind the authentication menu."""
    with patch(f"{CONFIG_FLOW}.validate_input", return_value=None):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["type"] is FlowResultType.MENU
        assert result["menu_options"] == ["entra_id", "api_key"]
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "api_key"}
        )
        assert result["step_id"] == "api_key"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_BASE: ENDPOINT, "api_key": "test-api-key"}
        )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.data == {
        CONF_AUTH_TYPE: AUTH_API_KEY,
        CONF_API_BASE: ENDPOINT,
        "api_key": "test-api-key",
    }
    assert {subentry.subentry_type for subentry in entry.subentries.values()} == {
        "conversation",
        "ai_task_data",
    }
    mock_setup_entry.assert_awaited_once()


async def test_oauth_flow_uses_arm_not_inference_catalog(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    oauth_implementation: EntraOAuth2Implementation,
    respx_mock: MockRouter,
) -> None:
    """Run setup through real HTTP adapters and keep the two token audiences separate."""
    account_url = f"https://management.azure.com{RESOURCE_ID}"
    respx_mock.get(account_url).respond(json={"properties": {"endpoint": ENDPOINT}})
    respx_mock.get(f"{account_url}/deployments").respond(
        json={
            "value": [
                {
                    "name": "ha-chat",
                    "properties": {
                        "model": {"format": "OpenAI", "name": "gpt-6.1-sol"},
                        "capabilities": {"chatCompletion": "true"},
                        "provisioningState": "Succeeded",
                    },
                }
            ]
        }
    )
    models = respx_mock.get(f"{ENDPOINT}openai/v1/models").respond(
        json={
            "object": "list",
            "data": [
                {
                    "object": "model",
                    "id": "gpt-4o-mini",
                    "created": 0,
                    "owned_by": "Azure",
                }
            ],
        }
    )
    with patch(
        "homeassistant.helpers.config_entry_oauth2_flow.LocalOAuth2Implementation.redirect_uri",
        new_callable=PropertyMock,
        return_value=REDIRECT_URI,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "entra_id"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TENANT_ID: TENANT_ID, CONF_RESOURCE_ID: RESOURCE_ID},
        )
        result = await _authorize(hass, result)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"conversation": ["ha-chat"], "ai_task_data": ["ha-chat"]},
        )
    await hass.async_block_till_done()

    entry = result["result"]
    assert len(entry.subentries) == 2
    assert all(
        item.data[CONF_CHAT_MODEL] == "ha-chat"
        and item.data[CONF_MODEL_NAME] == "gpt-6.1-sol"
        for item in entry.subentries.values()
    )
    assert models.calls[0].request.headers["Authorization"] == "Bearer inference-token"
    assert all(
        call.request.headers["Authorization"] == "Bearer management-token"
        for call in respx_mock.calls
        if call.request.url.host == "management.azure.com"
    )


@pytest.mark.parametrize(
    ("tenant", "resource", "errors"),
    [
        ("invalid", RESOURCE_ID, {CONF_TENANT_ID: "invalid_tenant_id"}),
        (TENANT_ID, "https://not-an-arm-id", {CONF_RESOURCE_ID: "invalid_resource_id"}),
    ],
)
async def test_resource_validation_precedes_sign_in(
    hass: HomeAssistant, tenant: str, resource: str, errors: dict
) -> None:
    """Do not open a browser or request credentials for malformed resource settings."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "entra_id"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TENANT_ID: tenant, CONF_RESOURCE_ID: resource}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "entra_id"
    assert result["errors"] == errors


async def test_api_key_migrates_to_browser_oauth(
    hass: HomeAssistant,
    oauth_implementation: EntraOAuth2Implementation,
    deployment_inventory: list[DeploymentData],
) -> None:
    """Reconfiguration may switch authentication without changing existing service IDs."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_BASE: ENDPOINT, "api_key": "old-key"},
        version=2,
        subentries_data=[
            {
                "subentry_type": "conversation",
                "title": "Existing assistant",
                "unique_id": None,
                "data": {CONF_CHAT_MODEL: "ha-chat", "prompt": "Keep me"},
            }
        ],
    )
    entry.add_to_hass(hass)
    subentry = next(iter(entry.subentries.values()))
    original_id = subentry.subentry_id
    with (
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.LocalOAuth2Implementation.redirect_uri",
            new_callable=PropertyMock,
            return_value=REDIRECT_URI,
        ),
        patch(
            f"{CONFIG_FLOW}.async_discover_deployments",
            return_value=DeploymentDiscovery(ENDPOINT, deployment_inventory),
        ),
        patch(f"{CONFIG_FLOW}.validate_input", return_value=None),
        patch.object(hass.config_entries, "async_reload", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "entra_id"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TENANT_ID: TENANT_ID, CONF_RESOURCE_ID: RESOURCE_ID},
        )
        result = await _authorize(hass, result)
        assert result["step_id"] == "discovery_confirm"
        assert result["description_placeholders"]["service_count"] == "6"
        conversation = _form_fields(result)["conversation"]["selector"]["select"]
        assert [item["value"] for item in conversation["options"]] == ["daily-chat"]
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_AUTH_TYPE] == AUTH_ENTRA_ID
    assert "api_key" not in entry.data
    assert subentry.subentry_id == original_id
    assert subentry.data["prompt"] == "Keep me"
    assert subentry.data[CONF_MODEL_NAME] == "gpt-6.1-sol"
    assert len(entry.subentries) == 1


async def test_oauth_reauth_preserves_resource_and_subentries(
    hass: HomeAssistant,
    oauth_data: dict,
    oauth_implementation: EntraOAuth2Implementation,
    deployment_inventory: list[DeploymentData],
) -> None:
    """A revoked Microsoft session relinks the configured tenant/resource, not an API key."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**oauth_data, CONF_DEPLOYMENTS: deployment_inventory},
        version=2,
        subentries_data=deployment_subentries(deployment_inventory),
    )
    entry.add_to_hass(hass)
    removed = next(
        item for item in entry.subentries.values() if item.subentry_type == "tts"
    )
    assert hass.config_entries.async_remove_subentry(entry, removed.subentry_id)
    original_ids = set(entry.subentries)
    with (
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.LocalOAuth2Implementation.redirect_uri",
            new_callable=PropertyMock,
            return_value=REDIRECT_URI,
        ),
        patch(
            f"{CONFIG_FLOW}.async_discover_deployments",
            return_value=DeploymentDiscovery(ENDPOINT, deployment_inventory),
        ),
        patch(f"{CONFIG_FLOW}.validate_input", return_value=None),
        patch.object(hass.config_entries, "async_reload", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reauth", "entry_id": entry.entry_id},
            data=entry.data,
        )
        assert result["step_id"] == "reauth_oauth_confirm"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        result = await _authorize(hass, result)
        assert result["step_id"] == "discovery_confirm"
        assert result["description_placeholders"]["service_count"] == "1"
        assert {
            service: field["selector"]["select"]["options"]
            for service, field in _form_fields(result).items()
        } == {"tts": [{"value": "speak", "label": "speak (tts-1)"}]}
        _assert_description_placeholders(result)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_RESOURCE_ID] == RESOURCE_ID
    assert entry.data[CONF_TENANT_ID] == TENANT_ID
    assert set(entry.subentries) == original_ids


async def test_reconfigure_reports_when_every_model_is_already_added(
    hass: HomeAssistant,
    oauth_data: dict,
    oauth_implementation: EntraOAuth2Implementation,
    deployment_inventory: list[DeploymentData],
) -> None:
    """Explain that nothing is missing, then refresh only the stored inventory."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**oauth_data, CONF_DEPLOYMENTS: deployment_inventory},
        version=2,
        subentries_data=deployment_subentries(deployment_inventory),
    )
    entry.add_to_hass(hass)
    original = {
        key: (item.title, dict(item.data)) for key, item in entry.subentries.items()
    }
    refreshed = sorted(
        [
            *deployment_inventory,
            DeploymentData(
                id=f"{RESOURCE_ID}/deployments/bulk",
                name="bulk",
                model_name="gpt-4.1-mini",
                services=[],
                unsupported_reason="batch-only deployment",
            ),
        ],
        key=lambda item: item["name"],
    )
    with (
        patch.object(
            EntraOAuth2Implementation,
            "_token_request",
            return_value=MANAGEMENT_TOKEN_RESPONSE,
        ),
        patch(
            f"{CONFIG_FLOW}.async_discover_deployments",
            return_value=DeploymentDiscovery(ENDPOINT, refreshed),
        ),
        patch(f"{CONFIG_FLOW}.validate_input", return_value=None),
        patch.object(hass.config_entries, "async_reload", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "entra_id"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TENANT_ID: TENANT_ID, CONF_RESOURCE_ID: RESOURCE_ID},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "discovery_all_added"
        assert result["last_step"] is True
        assert _form_fields(result) == {}
        assert result["description_placeholders"] == {
            "service_count": "0",
            "unsupported": "- bulk (gpt-4.1-mini)\n- search (text-embedding-3-large)",
        }
        _assert_description_placeholders(result)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_DEPLOYMENTS] == refreshed
    assert {
        key: (item.title, dict(item.data)) for key, item in entry.subentries.items()
    } == original


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        (
            httpx.HTTPStatusError(
                "Forbidden",
                request=httpx.Request("GET", "https://management.azure.com"),
                response=httpx.Response(403),
            ),
            "deployment_access_denied",
        ),
        (DeploymentDiscoveryError("bad metadata"), "invalid_discovery_response"),
        (httpx.ConnectError("cannot connect"), "cannot_connect"),
    ],
)
async def test_failed_reconfigure_changes_nothing(
    hass: HomeAssistant,
    oauth_data: dict,
    oauth_implementation: EntraOAuth2Implementation,
    failure: Exception,
    error: str,
) -> None:
    """Keep stored credentials and services untouched when discovery fails."""
    entry = MockConfigEntry(domain=DOMAIN, data=oauth_data, version=2)
    entry.add_to_hass(hass)
    with (
        patch.object(
            EntraOAuth2Implementation,
            "_token_request",
            return_value=MANAGEMENT_TOKEN_RESPONSE,
        ),
        patch(f"{CONFIG_FLOW}.async_discover_deployments", side_effect=failure),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "entra_id"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TENANT_ID: TENANT_ID, CONF_RESOURCE_ID: RESOURCE_ID},
        )
    assert result["step_id"] == "discovery"
    assert result["errors"] == {"base": error}
    _assert_description_placeholders(result)
    assert entry.data == oauth_data
    assert not entry.subentries


async def test_rejected_stored_session_signs_in_again(
    hass: HomeAssistant,
    oauth_data: dict,
    oauth_implementation: EntraOAuth2Implementation,
) -> None:
    """Reconfigure opens Microsoft sign-in when the stored session is rejected."""
    entry = MockConfigEntry(domain=DOMAIN, data=oauth_data, version=2)
    entry.add_to_hass(hass)
    with (
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.LocalOAuth2Implementation.redirect_uri",
            new_callable=PropertyMock,
            return_value=REDIRECT_URI,
        ),
        patch.object(
            EntraOAuth2Implementation,
            "_token_request",
            side_effect=OAuth2TokenRequestReauthError(
                domain=DOMAIN, request_info=Mock(), status=400
            ),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "entra_id"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TENANT_ID: TENANT_ID, CONF_RESOURCE_ID: RESOURCE_ID},
        )
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    assert f"/{TENANT_ID}/" in result["url"]
    assert entry.data == oauth_data


async def test_inference_permission_is_required_before_save(
    hass: HomeAssistant,
    oauth_data: dict,
    oauth_implementation: EntraOAuth2Implementation,
    deployment_inventory: list[DeploymentData],
) -> None:
    """Reader access alone must not produce a success-shaped integration setup."""
    entry = MockConfigEntry(domain=DOMAIN, data=oauth_data, version=2)
    entry.add_to_hass(hass)
    denied = openai.PermissionDeniedError(
        "Inference forbidden",
        response=httpx.Response(403, request=httpx.Request("GET", ENDPOINT)),
        body=None,
    )
    with (
        patch.object(
            EntraOAuth2Implementation,
            "_token_request",
            return_value=MANAGEMENT_TOKEN_RESPONSE,
        ),
        patch(
            f"{CONFIG_FLOW}.async_discover_deployments",
            return_value=DeploymentDiscovery(ENDPOINT, deployment_inventory),
        ),
        patch(f"{CONFIG_FLOW}.validate_input", side_effect=denied),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "entra_id"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TENANT_ID: TENANT_ID, CONF_RESOURCE_ID: RESOURCE_ID},
        )
    assert result["errors"] == {"base": "inference_access_denied"}
    assert entry.data == oauth_data
    assert not entry.subentries


async def test_manual_subentry_suggests_deployed_image(
    hass: HomeAssistant,
    oauth_data: dict,
    deployment_inventory: list[DeploymentData],
) -> None:
    """The dedicated image flow offers deployed aliases and stores only image metadata."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**oauth_data, CONF_DEPLOYMENTS: deployment_inventory},
        state=ConfigEntryState.LOADED,
        version=2,
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "ai_task_image"), context={"source": "user"}
    )
    assert result["step_id"] == "init"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Images", CONF_IMAGE_MODEL: "art"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    subentry = next(iter(entry.subentries.values()))
    assert subentry.subentry_type == "ai_task_image"
    assert subentry.data == {
        CONF_IMAGE_MODEL: "art",
        CONF_MODEL_NAME: "gpt-image-1",
    }


@pytest.mark.parametrize("service", ["conversation", "ai_task_data"])
async def test_new_chat_service_defaults_to_deployed_alias(
    hass: HomeAssistant,
    oauth_data: dict,
    deployment_inventory: list[DeploymentData],
    service: str,
) -> None:
    """Additional chat services must suggest a deployed alias, not a catalog default."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**oauth_data, CONF_DEPLOYMENTS: deployment_inventory},
        state=ConfigEntryState.LOADED,
        version=2,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, service), context={"source": "user"}
    )
    assert result["step_id"] == "init"
    fields = _form_fields(result)
    assert fields[CONF_SEND_SAMPLING_PARAMETERS]["default"] is False
    for field, maximum in ((CONF_TOP_P, 1), (CONF_TEMPERATURE, 2)):
        assert fields[field]["visible"] == {
            "field": CONF_SEND_SAMPLING_PARAMETERS,
            "value": True,
        }
        assert fields[field]["selector"] == {
            "number": {"min": 0.0, "max": maximum, "step": 0.05, "mode": "slider"}
        }
        assert "visible" not in fields[field].get("description", {})
        assert "default" not in fields[field]
    user_input = result["data_schema"](
        {"name": "Additional assistant", "recommended": True}
    )
    assert user_input[CONF_CHAT_MODEL] == "ha-chat"
    selector = next(
        selector
        for field, selector in result["data_schema"].schema.items()
        if field.schema == CONF_CHAT_MODEL
    )
    assert selector.config["options"] == [
        {"value": "ha-chat", "label": "ha-chat (gpt-6.1-sol)"},
        {"value": "daily-chat", "label": "daily-chat (gpt-4.1-mini)"},
    ]
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    subentry = next(iter(entry.subentries.values()))
    assert subentry.data[CONF_CHAT_MODEL] == "ha-chat"
    assert subentry.data[CONF_MODEL_NAME] == "gpt-6.1-sol"
    assert subentry.data[CONF_SEND_SAMPLING_PARAMETERS] is False


@pytest.mark.parametrize("service", ["conversation", "ai_task_data"])
async def test_recommended_sampling_preserves_explicit_choices_and_hidden_values(
    hass: HomeAssistant,
    oauth_data: dict,
    deployment_inventory: list[DeploymentData],
    service: str,
) -> None:
    """Disabling and re-enabling sampling retains saved numbers and model effort."""
    subentries = deployment_subentries(deployment_inventory)
    for subentry_data in subentries:
        if (
            subentry_data["subentry_type"] == service
            and subentry_data["data"].get(CONF_CHAT_MODEL) == "ha-chat"
        ):
            subentry_data["data"].update(
                {
                    CONF_SEND_SAMPLING_PARAMETERS: True,
                    CONF_TOP_P: 0.35,
                    CONF_TEMPERATURE: 0.75,
                    CONF_REASONING_EFFORT: "high",
                }
            )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**oauth_data, CONF_DEPLOYMENTS: deployment_inventory},
        state=ConfigEntryState.LOADED,
        version=2,
        minor_version=2,
        subentries_data=subentries,
    )
    entry.add_to_hass(hass)
    subentry = next(
        item
        for item in entry.subentries.values()
        if item.subentry_type == service and item.data[CONF_CHAT_MODEL] == "ha-chat"
    )
    original_id, original_unique_id = subentry.subentry_id, subentry.unique_id
    context = {"source": "reconfigure", "subentry_id": original_id}
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, service), context=context
    )
    fields = _form_fields(result)
    assert fields[CONF_SEND_SAMPLING_PARAMETERS]["default"] is True
    assert fields[CONF_REASONING_EFFORT]["description"]["suggested_value"] == "high"
    user_input = {CONF_CHAT_MODEL: "ha-chat", "recommended": True}
    if service == "conversation":
        user_input["prompt"] = "My prompt"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input
    )
    assert result["reason"] == "reconfigure_successful"
    assert subentry.data[CONF_CHAT_MODEL] == "ha-chat"
    assert subentry.data[CONF_MODEL_NAME] == "gpt-6.1-sol"
    if service == "conversation":
        assert subentry.data["prompt"] == "My prompt"
    assert subentry.data[CONF_SEND_SAMPLING_PARAMETERS] is True
    assert subentry.data[CONF_REASONING_EFFORT] == "high"
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, service), context=context
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_CHAT_MODEL: "ha-chat",
            "recommended": True,
            CONF_SEND_SAMPLING_PARAMETERS: False,
            CONF_TOP_P: 0.9,
            CONF_TEMPERATURE: 1.5,
        },
    )
    assert result["reason"] == "reconfigure_successful"
    assert subentry.data[CONF_SEND_SAMPLING_PARAMETERS] is False
    assert subentry.data[CONF_TOP_P] == 0.35
    assert subentry.data[CONF_TEMPERATURE] == 0.75
    assert subentry.data[CONF_REASONING_EFFORT] == "high"
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, service), context=context
    )
    fields = _form_fields(result)
    assert fields[CONF_SEND_SAMPLING_PARAMETERS]["default"] is False
    assert fields[CONF_TOP_P]["description"]["suggested_value"] == 0.35
    assert fields[CONF_TEMPERATURE]["description"]["suggested_value"] == 0.75
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_CHAT_MODEL: "ha-chat",
            "recommended": True,
            CONF_SEND_SAMPLING_PARAMETERS: True,
        },
    )
    assert result["reason"] == "reconfigure_successful"
    assert subentry.data[CONF_SEND_SAMPLING_PARAMETERS] is True
    assert subentry.data[CONF_TOP_P] == 0.35
    assert subentry.data[CONF_TEMPERATURE] == 0.75
    assert subentry.data[CONF_REASONING_EFFORT] == "high"
    assert subentry.subentry_id == original_id
    assert subentry.unique_id == original_unique_id


@pytest.mark.parametrize("service", ["conversation", "ai_task_data"])
@pytest.mark.parametrize(
    ("model_name", "choices", "default"),
    [
        ("gpt-4.1-mini", [], None),
        ("gpt-5", ["minimal", "low", "medium", "high"], "low"),
        ("gpt-5.1", ["none", "low", "medium", "high"], "low"),
        ("gpt-5.2-pro", ["medium", "high", "xhigh"], "medium"),
        ("gpt-5.4", ["none", "low", "medium", "high", "xhigh"], "low"),
        ("gpt-5.6", ["none", "low", "medium", "high", "xhigh", "max"], "low"),
        ("gpt-6.1-sol", ["low", "medium", "high", "xhigh", "max"], "low"),
        ("gpt-6-luna", ["none", "low", "medium", "high", "xhigh", "max"], "low"),
        ("gpt-5-pro", [], None),
    ],
)
async def test_initial_settings_offer_valid_model_effort_with_recommended_enabled(
    hass: HomeAssistant,
    oauth_data: dict,
    deployment_inventory: list[DeploymentData],
    service: str,
    model_name: str,
    choices: list[str],
    default: str | None,
) -> None:
    """Use the underlying model, including model-specific valid recommended defaults."""
    deployment_inventory[0]["model_name"] = model_name
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**oauth_data, CONF_DEPLOYMENTS: deployment_inventory},
        state=ConfigEntryState.LOADED,
        version=2,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, service), context={"source": "user"}
    )
    fields = _form_fields(result)
    if choices:
        assert fields[CONF_REASONING_EFFORT]["selector"]["select"]["options"] == choices
        assert (
            fields[CONF_REASONING_EFFORT]["description"]["suggested_value"] == default
        )
    else:
        assert CONF_REASONING_EFFORT not in fields
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "Configured model", CONF_CHAT_MODEL: "ha-chat", "recommended": True},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    subentry = next(iter(entry.subentries.values()))
    assert subentry.data.get(CONF_REASONING_EFFORT) == default


@pytest.mark.parametrize("service", ["conversation", "ai_task_data"])
async def test_changed_model_rejects_incompatible_effort_and_refreshes_choices(
    hass: HomeAssistant,
    oauth_data: dict,
    deployment_inventory: list[DeploymentData],
    service: str,
) -> None:
    """An effort accepted by the old selector must still be valid for the new model."""
    deployment_inventory[0]["model_name"] = "gpt-5"
    deployment_inventory[1]["model_name"] = "gpt-5.2-pro"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**oauth_data, CONF_DEPLOYMENTS: deployment_inventory},
        state=ConfigEntryState.LOADED,
        version=2,
        minor_version=2,
        subentries_data=deployment_subentries(deployment_inventory),
    )
    entry.add_to_hass(hass)
    subentry = next(
        item
        for item in entry.subentries.values()
        if item.subentry_type == service and item.data[CONF_CHAT_MODEL] == "ha-chat"
    )
    original_data = dict(subentry.data)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, service),
        context={"source": "reconfigure", "subentry_id": subentry.subentry_id},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_CHAT_MODEL: "daily-chat",
            "recommended": True,
            CONF_REASONING_EFFORT: "minimal",
        },
    )
    assert result["step_id"] == "init"
    assert result["errors"] == {CONF_REASONING_EFFORT: "reasoning_effort_not_supported"}
    fields = _form_fields(result)
    assert fields[CONF_REASONING_EFFORT]["selector"]["select"]["options"] == [
        "medium",
        "high",
        "xhigh",
    ]
    assert fields[CONF_REASONING_EFFORT]["description"]["suggested_value"] == "medium"
    assert subentry.data == original_data
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_CHAT_MODEL: "daily-chat",
            "recommended": True,
            CONF_REASONING_EFFORT: "medium",
        },
    )
    assert result["reason"] == "reconfigure_successful"
    assert subentry.data[CONF_CHAT_MODEL] == "daily-chat"
    assert subentry.data[CONF_MODEL_NAME] == "gpt-5.2-pro"
    assert subentry.data[CONF_REASONING_EFFORT] == "medium"


@pytest.mark.parametrize("service", ["conversation", "ai_task_data"])
@pytest.mark.parametrize("tool", ["web_search", "code_interpreter"])
async def test_initial_minimal_effort_still_rejects_incompatible_advanced_tools(
    hass: HomeAssistant,
    oauth_data: dict,
    deployment_inventory: list[DeploymentData],
    service: str,
    tool: str,
) -> None:
    """Moving the selector must not bypass validation of minimal-effort tool use."""
    deployment_inventory[0]["model_name"] = "gpt-5"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**oauth_data, CONF_DEPLOYMENTS: deployment_inventory},
        state=ConfigEntryState.LOADED,
        version=2,
        minor_version=2,
        subentries_data=deployment_subentries(deployment_inventory),
    )
    entry.add_to_hass(hass)
    subentry = next(
        item
        for item in entry.subentries.values()
        if item.subentry_type == service and item.data[CONF_CHAT_MODEL] == "ha-chat"
    )
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, service),
        context={"source": "reconfigure", "subentry_id": subentry.subentry_id},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_CHAT_MODEL: "ha-chat",
            "recommended": False,
            CONF_REASONING_EFFORT: "minimal",
        },
    )
    assert result["step_id"] == "additional"
    assert {
        CONF_SEND_SAMPLING_PARAMETERS,
        CONF_TEMPERATURE,
        CONF_TOP_P,
        CONF_REASONING_EFFORT,
    }.isdisjoint(_form_fields(result))
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {})
    assert result["step_id"] == "model"
    assert CONF_REASONING_EFFORT not in _form_fields(result)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {tool: True}
    )
    assert result["step_id"] == "model"
    assert result["errors"] == {tool: f"{tool}_minimal_reasoning"}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {tool: False}
    )
    assert result["reason"] == "reconfigure_successful"
    assert subentry.data[CONF_REASONING_EFFORT] == "minimal"
    assert subentry.data[tool] is False


@pytest.mark.parametrize(
    ("audience", "failure", "key", "expected"),
    [
        (0, MALFORMED_TOKEN, "reason", "oauth_failed"),
        (1, MALFORMED_TOKEN, "errors", {"base": "cannot_connect"}),
        # A fresh sign-in cannot fix a denied management token, so do not loop.
        (
            1,
            OAuth2TokenRequestReauthError(
                domain=DOMAIN, request_info=Mock(), status=400
            ),
            "errors",
            {"base": "deployment_access_denied"},
        ),
    ],
)
async def test_failed_browser_token_exchange_saves_and_logs_nothing(
    hass: HomeAssistant,
    oauth_implementation: EntraOAuth2Implementation,
    audience: int,
    failure: dict | Exception,
    key: str,
    expected: str | dict,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Failed token exchanges must surface an error without saving or logging tokens."""
    responses = [
        {
            "access_token": "inference-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
        },
        MANAGEMENT_TOKEN_RESPONSE,
    ]
    responses[audience] = failure
    with patch(
        "homeassistant.helpers.config_entry_oauth2_flow.LocalOAuth2Implementation.redirect_uri",
        new_callable=PropertyMock,
        return_value=REDIRECT_URI,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "entra_id"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TENANT_ID: TENANT_ID, CONF_RESOURCE_ID: RESOURCE_ID},
        )
        result = await _authorize(hass, result, responses)
    assert result[key] == expected
    assert not hass.config_entries.async_entries(DOMAIN)
    assert "do-not-log-this-token" not in caplog.text
    assert "inference-token" not in caplog.text


@pytest.mark.parametrize(
    "selection",
    [
        {
            "conversation": ["ha-chat", "daily-chat"],
            "ai_task_data": ["ha-chat", "daily-chat"],
            "ai_task_image": ["art"],
            "stt": ["listen"],
            "tts": ["speak"],
        },
        {"conversation": ["ha-chat"], "stt": ["listen"]},
        {},
    ],
)
async def test_native_application_credentials_create_only_selected_services(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    deployment_inventory: list[DeploymentData],
    respx_mock: MockRouter,
    selection: dict[str, list[str]],
) -> None:
    """Link native credentials and let each service independently opt into models."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    credential = await hass.data[
        application_credentials.DATA_COMPONENT
    ].async_create_item(
        {
            "domain": DOMAIN,
            "client_id": "native-client",
            "client_secret": "native-client-secret",
            "name": "Home Assistant Azure",
        }
    )
    with (
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.LocalOAuth2Implementation.redirect_uri",
            new_callable=PropertyMock,
            return_value=REDIRECT_URI,
        ),
        patch(
            f"{CONFIG_FLOW}.async_discover_deployments",
            return_value=DeploymentDiscovery(ENDPOINT, deployment_inventory),
        ),
        patch(f"{CONFIG_FLOW}.validate_input", return_value=None),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "entra_id"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TENANT_ID: TENANT_ID, CONF_RESOURCE_ID: RESOURCE_ID},
        )
        assert result["step_id"] == "pick_implementation"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"implementation": credential["id"]}
        )
        assert parse_qs(urlsplit(result["url"]).query)["client_id"] == ["native-client"]
        result = await _authorize(hass, result)
        assert result["step_id"] == "discovery_confirm"
        assert result["description_placeholders"]["service_count"] == "7"
        assert result["description_placeholders"]["unsupported"] == (
            "- search (text-embedding-3-large)"
        )
        _assert_description_placeholders(result)
        assert "inference-token" not in str(result)
        assert "management-token" not in str(result)
        fields = _form_fields(result)
        assert set(fields) == {
            "conversation",
            "ai_task_data",
            "ai_task_image",
            "stt",
            "tts",
        }
        for service, field in fields.items():
            assert field["default"] == []
            selector = field["selector"]["select"]
            assert selector["multiple"] is True
            assert {(item["value"], item["label"]) for item in selector["options"]} == {
                (
                    deployment["name"],
                    f"{deployment['name']} ({deployment['model_name']})",
                )
                for deployment in deployment_inventory
                if service in deployment["services"]
            }
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], selection
        )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.data[CONF_AUTH_TYPE] == AUTH_ENTRA_ID
    assert "api_key" not in entry.data
    assert entry.data[CONF_DEPLOYMENTS] == deployment_inventory
    assert entry.data["auth_implementation"] == credential["id"]
    expected = {
        (service, deployment)
        for service, deployments in selection.items()
        for deployment in deployments
    }
    assert len(entry.subentries) == len(expected)
    assert len({item.unique_id for item in entry.subentries.values()}) == len(expected)
    assert {
        (
            item.subentry_type,
            item.data.get(CONF_CHAT_MODEL, item.data.get(CONF_IMAGE_MODEL)),
        )
        for item in entry.subentries.values()
    } == expected
    client = await async_create_entry_client(hass, entry)
    await hass.async_add_executor_job(client.platform_headers)
    route = respx_mock.get(f"{ENDPOINT}openai/v1/models").respond(
        json={"object": "list", "data": []}
    )
    await client.models.list()
    assert route.calls[0].request.headers["Authorization"] == "Bearer inference-token"


@pytest.mark.parametrize("service", ["conversation", "ai_task_data"])
async def test_recommended_settings_keep_known_model_metadata_without_inventory(
    hass: HomeAssistant, service: str
) -> None:
    """Returning to manual authentication must not discard an unchanged alias's model."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_AUTH_TYPE: AUTH_API_KEY,
            CONF_API_BASE: ENDPOINT,
            "api_key": "test-key",
        },
        state=ConfigEntryState.LOADED,
        version=2,
        minor_version=2,
        subentries_data=[
            {
                "subentry_type": service,
                "title": "Keep this service",
                "unique_id": "original-deployment-service",
                "data": {
                    CONF_CHAT_MODEL: "ha-chat",
                    CONF_MODEL_NAME: "gpt-6.1-sol",
                    "recommended": False,
                },
            }
        ],
    )
    entry.add_to_hass(hass)
    subentry = next(iter(entry.subentries.values()))
    original_id = subentry.subentry_id
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, service),
        context={"source": "reconfigure", "subentry_id": subentry.subentry_id},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_CHAT_MODEL: "ha-chat", "recommended": True}
    )
    assert result["reason"] == "reconfigure_successful"
    assert subentry.data[CONF_MODEL_NAME] == "gpt-6.1-sol"
    assert subentry.subentry_id == original_id
    assert subentry.unique_id == "original-deployment-service"


async def test_web_location_lookup_reuses_the_oauth_runtime_client(
    hass: HomeAssistant,
    oauth_data: dict,
    oauth_implementation: EntraOAuth2Implementation,
    deployment_inventory: list[DeploymentData],
    respx_mock: MockRouter,
) -> None:
    """Optional location lookup must use the selected deployment without requiring a key."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**oauth_data, CONF_DEPLOYMENTS: deployment_inventory},
        state=ConfigEntryState.LOADED,
        version=2,
        minor_version=2,
        subentries_data=[
            {
                "subentry_type": "conversation",
                "title": "My assistant",
                "unique_id": None,
                "data": {CONF_CHAT_MODEL: "ha-chat", "recommended": False},
            }
        ],
    )
    entry.add_to_hass(hass)
    entry.runtime_data = await async_create_entry_client(hass, entry)
    await hass.async_add_executor_job(entry.runtime_data.platform_headers)
    hass.states.async_set("zone.home", "0", {"latitude": 50.0, "longitude": 1.0})
    route = respx_mock.post(f"{ENDPOINT}openai/v1/responses").respond(
        json={
            "id": "location-response",
            "object": "response",
            "created_at": 1,
            "model": "ha-chat",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "id": "location-message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"city": "Test City", "region": "Test Region"}',
                            "annotations": [],
                        }
                    ],
                }
            ],
        }
    )
    subentry = next(iter(entry.subentries.values()))
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "conversation"),
        context={"source": "reconfigure", "subentry_id": subentry.subentry_id},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_CHAT_MODEL: "ha-chat", "recommended": False}
    )
    assert result["step_id"] == "additional"
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {})
    assert result["step_id"] == "model"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"web_search": True, "user_location": True}
    )
    assert result["reason"] == "reconfigure_successful"
    assert subentry.data["city"] == "Test City"
    assert subentry.data["region"] == "Test Region"
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer inference-token"
    assert json.loads(request.content)["model"] == "ha-chat"


@pytest.mark.parametrize("service", ["conversation", "ai_task_data"])
@pytest.mark.parametrize("change_alias", [False, True])
async def test_manual_reconfigure_uses_metadata_only_for_unchanged_alias(
    hass: HomeAssistant, service: str, change_alias: bool
) -> None:
    """Retained metadata preserves custom settings but cannot describe another alias."""
    custom = {
        "reasoning_effort": "high",
        "reasoning_summary": "detailed",
        "verbosity": "low",
        "pro_mode": True,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_AUTH_TYPE: AUTH_API_KEY,
            CONF_API_BASE: ENDPOINT,
            "api_key": "test-key",
        },
        state=ConfigEntryState.LOADED,
        version=2,
        minor_version=2,
        subentries_data=[
            {
                "subentry_type": service,
                "title": "Keep my custom service",
                "unique_id": "known-deployment-service",
                "data": {
                    CONF_CHAT_MODEL: "ha-chat",
                    CONF_MODEL_NAME: "gpt-6.1-sol",
                    "recommended": False,
                    **custom,
                },
            }
        ],
    )
    entry.add_to_hass(hass)
    subentry = next(iter(entry.subentries.values()))
    original_id = subentry.subentry_id
    alias = "replacement-chat" if change_alias else "ha-chat"
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, service),
        context={"source": "reconfigure", "subentry_id": original_id},
    )
    assert CONF_REASONING_EFFORT in _form_fields(result)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_CHAT_MODEL: alias, "recommended": False}
    )
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {})
    assert result["step_id"] == "model"
    fields = {field.schema for field in result["data_schema"].schema}
    if change_alias:
        assert fields.isdisjoint(custom)
    else:
        assert custom.keys() - {CONF_REASONING_EFFORT} <= fields
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {}
        if change_alias
        else {
            key: value for key, value in custom.items() if key != CONF_REASONING_EFFORT
        },
    )
    assert result["reason"] == "reconfigure_successful"
    assert subentry.subentry_id == original_id
    assert subentry.data[CONF_CHAT_MODEL] == alias
    if change_alias:
        assert CONF_MODEL_NAME not in subentry.data
        assert custom.keys().isdisjoint(subentry.data)
        assert subentry.unique_id is None
    else:
        assert subentry.data[CONF_MODEL_NAME] == "gpt-6.1-sol"
        assert all(subentry.data[key] == value for key, value in custom.items())
        assert subentry.unique_id == "known-deployment-service"


@pytest.mark.parametrize(
    ("service", "alias", "model_name"),
    [("stt", "custom-listen", "whisper"), ("tts", "custom-speak", "tts-1")],
)
async def test_speech_instruction_edit_does_not_change_the_deployment(
    hass: HomeAssistant, service: str, alias: str, model_name: str
) -> None:
    """Optional deployment fields must retain the selected alias when editing speech."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_AUTH_TYPE: AUTH_API_KEY,
            CONF_API_BASE: ENDPOINT,
            "api_key": "test-key",
        },
        state=ConfigEntryState.LOADED,
        version=2,
        minor_version=2,
        subentries_data=[
            {
                "subentry_type": service,
                "title": "Keep my speech service",
                "unique_id": "known-deployment-service",
                "data": {CONF_CHAT_MODEL: alias, CONF_MODEL_NAME: model_name},
            }
        ],
    )
    entry.add_to_hass(hass)
    subentry = next(iter(entry.subentries.values()))
    original_id = subentry.subentry_id
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, service),
        context={"source": "reconfigure", "subentry_id": original_id},
    )
    assert (
        result["data_schema"]({"prompt": "New instructions"})[CONF_CHAT_MODEL] == alias
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"prompt": "New instructions"}
    )
    assert result["reason"] == "reconfigure_successful"
    assert subentry.data[CONF_CHAT_MODEL] == alias
    assert subentry.data[CONF_MODEL_NAME] == model_name
    assert subentry.data["prompt"] == "New instructions"
    assert subentry.subentry_id == original_id
    assert subentry.unique_id == "known-deployment-service"


@pytest.mark.parametrize("language", LANGUAGES)
async def test_oauth_labels_are_localized_without_replacing_api_key_labels(
    hass: HomeAssistant, language: str
) -> None:
    """Every locale has its own Microsoft linking text and retains manual setup text."""
    translations = await async_get_translations(hass, language, "config", {DOMAIN})
    localized = _strings(language)
    prefix = f"component.{DOMAIN}.config"
    for key in (
        "step.pick_implementation.data.implementation",
        "step.pick_implementation.title",
        "abort.missing_configuration",
        "step.discovery_all_added.title",
        "step.discovery_all_added.description",
        *(f"step.discovery_confirm.data.{service}" for service in DISCOVERY_SERVICES),
    ):
        assert translations[f"{prefix}.{key}"] == localized[f"config.{key}"]
    assert f"{prefix}.step.api_key.data.api_key" in translations
    assert f"{prefix}.step.user.data.api_key" not in translations


@pytest.mark.parametrize("language", LANGUAGES)
async def test_initial_settings_labels_and_effort_errors_exist_in_every_locale(
    hass: HomeAssistant, language: str
) -> None:
    """Moved sampling labels and effort text are translated in every locale."""
    translations = await async_get_translations(
        hass, language, "config_subentries", {DOMAIN}
    )
    localized = _strings(language)
    for service in ("conversation", "ai_task_data"):
        prefix = f"component.{DOMAIN}.config_subentries.{service}"
        for field in (
            CONF_SEND_SAMPLING_PARAMETERS,
            CONF_TOP_P,
            CONF_TEMPERATURE,
            CONF_REASONING_EFFORT,
        ):
            assert f"{prefix}.step.init.data.{field}" in translations
            assert f"{prefix}.step.additional.data.{field}" not in translations
        assert (
            translations[f"{prefix}.step.init.data.{CONF_REASONING_EFFORT}"]
            == localized[
                f"config_subentries.{service}.step.init.data.{CONF_REASONING_EFFORT}"
            ]
        )
        assert f"{prefix}.error.reasoning_effort_not_supported" in translations


def test_english_translation_mirrors_strings() -> None:
    """Custom integrations need resolved English text for every strings.json key."""
    source = _strings("strings")
    english = _strings("en")
    assert english.keys() == source.keys()
    for key, value in english.items():
        assert value.strip(), key
        assert "[%key:" not in value, key
        if "[%key:" not in source[key]:
            assert value == source[key], key


@pytest.mark.parametrize("language", LANGUAGES[1:])
def test_locale_matches_english_keys_and_placeholders(language: str) -> None:
    """Mismatched placeholders are dropped by Home Assistant or break the frontend."""
    english = _strings("en")
    localized = _strings(language)
    assert localized.keys() == english.keys()
    for key, value in localized.items():
        assert value.strip(), key
        assert "[%key:" not in value, key
        assert _placeholders(value) == _placeholders(english[key]), key
        # The frontend's ICU formatter treats an apostrophe before a brace as quoting.
        assert "'{" not in value, key
        assert "'}" not in value, key


@pytest.mark.parametrize("language", LANGUAGES)
async def test_translations_load_without_english_fallback(
    hass: HomeAssistant, language: str
) -> None:
    """Home Assistant serves every shipped string in the requested language."""
    localized = _strings(language)
    for category in {key.split(".", 1)[0] for key in localized}:
        assert await async_get_translations(hass, language, category, {DOMAIN}) == {
            f"component.{DOMAIN}.{key}": value
            for key, value in localized.items()
            if key.startswith(f"{category}.")
        }
