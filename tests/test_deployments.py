"""Verify actual Azure deployment inventory, pagination, and additive reconciliation."""

from typing import Any

import httpx
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from respx import MockRouter

from homeassistant.core import HomeAssistant

from custom_components.azure_openai_conversation.const import (
    CONF_CHAT_MODEL,
    CONF_DEPLOYMENTS,
    DOMAIN,
)
from custom_components.azure_openai_conversation.deployments import (
    MANAGEMENT_ORIGIN,
    DeploymentData,
    DeploymentDiscoveryError,
    async_discover_deployments,
    deployment_subentries,
    missing_deployment_services,
    supported_services,
    sync_deployment_subentries,
    validate_inference_endpoint,
    validate_resource_id,
)

from .const import ENDPOINT, RESOURCE_ID

ACCOUNT_URL = f"{MANAGEMENT_ORIGIN}{RESOURCE_ID}"


@pytest.mark.parametrize(
    ("model", "capabilities", "expected"),
    [
        ("gpt-6.1-sol", {"chatCompletion": "true"}, ("conversation", "ai_task_data")),
        ("gpt-4.1-mini", {}, ("conversation", "ai_task_data")),
        ("gpt-chat-latest", {}, ("conversation", "ai_task_data")),
        ("gpt-6.1-sol", {"responses": False}, ()),
        ("gpt-6.1-sol", {"chatCompletion": "false"}, ()),
        ("gpt-35-turbo", {"chatCompletion": "true"}, ()),
        ("gpt-4-turbo", {"chatCompletion": "true"}, ()),
        ("o1-mini-2024-09-12", {"responses": True}, ()),
        ("gpt-4o-realtime-preview", {"chatCompletion": "true"}, ()),
        ("gpt-realtime-2.1", {"speech": "true", "transcription": "true"}, ()),
        ("gpt-live-transcribe", {"transcription": "true"}, ()),
        ("gpt-realtime-whisper", {"transcription": "true"}, ()),
        ("gpt-4o-audio-preview", {"chatCompletion": "true"}, ()),
        ("gpt-4o-mini-search-preview", {"chatCompletion": "true"}, ()),
        ("gpt-image-1", {}, ("ai_task_image",)),
        ("dall-e-3", {}, ("ai_task_image",)),
        ("dall-e-2", {}, ("ai_task_image",)),
        ("whisper", {}, ("stt",)),
        ("gpt-transcribe", {}, ("stt",)),
        ("gpt-4o-transcribe", {}, ("stt",)),
        ("gpt-4o-mini-transcribe", {}, ("stt",)),
        ("gpt-4o-transcribe-diarize", {}, ()),
        ("gpt-4o-mini-tts", {}, ("tts",)),
        ("tts", {}, ("tts",)),
        ("tts-hd", {}, ("tts",)),
        ("tts-1", {}, ("tts",)),
        ("tts-1-hd", {}, ("tts",)),
        ("text-embedding-3-large", {"embeddings": "true"}, ()),
        ("sora-2", {}, ()),
        ("davinci-002", {"completion": "true"}, ()),
    ],
)
def test_supported_services(
    model: str, capabilities: dict[str, Any], expected: tuple[str, ...]
) -> None:
    """Do not confuse chat-completions-only models with Responses-compatible models."""
    assert supported_services(model, capabilities) == expected


@pytest.mark.parametrize(
    "resource",
    [
        "https://management.azure.com" + RESOURCE_ID,
        RESOURCE_ID + "/projects/example",
        RESOURCE_ID + "/deployments/example",
        RESOURCE_ID.replace("00000000-0000-0000-0000-000000000000", "invalid"),
        RESOURCE_ID.replace("/resourceGroups/test/", "/resourceGroups/test?/"),
        RESOURCE_ID.replace("/resourceGroups/test/", "/resourceGroups/test./"),
    ],
)
def test_invalid_resource_id(resource: str) -> None:
    """Reject URLs and child-resource paths before sending an authenticated request."""
    with pytest.raises(ValueError):
        validate_resource_id(resource)


def test_resource_id_normalization() -> None:
    """Normalize valid account IDs without changing resource identity."""
    assert validate_resource_id(f" {RESOURCE_ID}/ ") == RESOURCE_ID


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://test-account.openai.azure.com",
        "https://test-account.openai.azure.com.attacker.example",
        "https://attacker.example",
        "https://user:password@test-account.openai.azure.com",
        "https://test-account.openai.azure.com:8443",
        "https://test-account.openai.azure.com:bad-port",
        "https://test-account.openai.azure.com?destination=attacker",
        "https://test-account.openai.azure.com#fragment",
    ],
)
def test_untrusted_inference_endpoint(endpoint: str) -> None:
    """Never expose an Entra bearer token to a gateway or untrusted endpoint."""
    with pytest.raises(DeploymentDiscoveryError):
        validate_inference_endpoint(endpoint)


async def test_discover_actual_deployments(
    hass: HomeAssistant,
    respx_mock: MockRouter,
    deployment_inventory: list[DeploymentData],
) -> None:
    """Discover every deployment page and enrich only those actually deployed."""
    for item in deployment_inventory:
        if item["name"] == "speak":
            item["model_name"] = "tts"
    respx_mock.get(ACCOUNT_URL).respond(json={"properties": {"endpoint": ENDPOINT}})
    records = [
        {
            "name": item["name"],
            "properties": {
                "model": {
                    "format": "OpenAI",
                    "name": item["model_name"],
                    "version": "1",
                },
                "provisioningState": "Succeeded",
            },
        }
        for item in deployment_inventory
    ]
    records.append(
        {
            "name": "gpt-6-named-anthropic",
            "properties": {
                "model": {
                    "publisher": "Anthropic",
                    "format": "OpenAI",
                    "name": "claude-sonnet",
                },
                "provisioningState": "Succeeded",
            },
        }
    )
    deployments_route = respx_mock.get(f"{ACCOUNT_URL}/deployments").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "value": records[:2],
                    "nextLink": "?api-version=2024-10-01&$skiptoken=more",
                },
            ),
            httpx.Response(200, json={"value": records[2:]}),
        ]
    )
    catalog = [
        {
            "format": "OpenAI",
            "name": item["model_name"],
            "version": "1",
            "capabilities": (
                {"chatCompletion": "true"} if "conversation" in item["services"] else {}
            ),
        }
        for item in deployment_inventory
    ]
    catalog.append(
        {
            "format": "OpenAI",
            "name": "gpt-4o-mini",
            "version": "1",
            "capabilities": {"chatCompletion": "true"},
        }
    )
    respx_mock.get(f"{ACCOUNT_URL}/models").respond(json={"value": catalog})

    result = await async_discover_deployments(hass, RESOURCE_ID, "management-token")

    assert result.endpoint == ENDPOINT
    assert deployments_route.call_count == 2
    by_name = {item["name"]: item for item in result.deployments}
    assert by_name.keys() == {item["name"] for item in deployment_inventory}
    assert by_name["ha-chat"]["model_name"] == "gpt-6.1-sol"
    assert by_name["ha-chat"]["services"] == ["conversation", "ai_task_data"]
    assert by_name["art"]["services"] == ["ai_task_image"]
    assert by_name["listen"]["services"] == ["stt"]
    assert by_name["speak"]["services"] == ["tts"]
    assert by_name["search"]["unsupported_reason"]
    assert len(deployment_subentries(result.deployments)) == 7
    assert all(
        call.request.headers["Authorization"] == "Bearer management-token"
        for call in respx_mock.calls
    )


@pytest.mark.parametrize(
    "next_link",
    [
        "https://attacker.example/deployments",
        f"https://user@management.azure.com{RESOURCE_ID}/deployments",
        f"{ACCOUNT_URL}/models",
        f"{ACCOUNT_URL}/deployments?api-version=2024-10-01",
        f"https://management.azure.com:bad-port{RESOURCE_ID}/deployments",
    ],
)
async def test_reject_bad_pagination(
    hass: HomeAssistant, respx_mock: MockRouter, next_link: str
) -> None:
    """Reject cross-resource links, credentials, invalid ports, and pagination cycles."""
    respx_mock.get(ACCOUNT_URL).respond(json={"properties": {"endpoint": ENDPOINT}})
    respx_mock.get(f"{ACCOUNT_URL}/deployments").respond(
        json={"value": [], "nextLink": next_link}
    )
    with pytest.raises(DeploymentDiscoveryError):
        await async_discover_deployments(hass, RESOURCE_ID, "management-token")
    assert len(respx_mock.calls) == 2


async def test_arm_redirect_is_not_followed(
    hass: HomeAssistant, respx_mock: MockRouter
) -> None:
    """Do not follow redirects carrying management-plane authorization."""
    respx_mock.get(ACCOUNT_URL).respond(
        status_code=302, headers={"Location": "https://attacker.example"}
    )
    with pytest.raises(httpx.HTTPStatusError):
        await async_discover_deployments(hass, RESOURCE_ID, "management-token")
    assert len(respx_mock.calls) == 1


@pytest.mark.parametrize(
    "record",
    [
        {"name": "broken", "properties": None},
        {"name": "broken", "properties": {"model": {"publisher": 42}}},
        {
            "name": "broken",
            "properties": {"model": {"format": "OpenAI", "name": None}},
        },
        {
            "name": "bad/path",
            "properties": {"model": {"format": "OpenAI", "name": "gpt-6.1-sol"}},
        },
        {
            "name": "broken",
            "sku": None,
            "properties": {"model": {"format": "OpenAI", "name": "gpt-6.1-sol"}},
        },
    ],
)
async def test_malformed_inventory_is_not_success(
    hass: HomeAssistant, respx_mock: MockRouter, record: dict
) -> None:
    """A malformed Azure response is an explicit error, not an empty successful setup."""
    respx_mock.get(ACCOUNT_URL).respond(json={"properties": {"endpoint": ENDPOINT}})
    respx_mock.get(f"{ACCOUNT_URL}/deployments").respond(json={"value": [record]})
    respx_mock.get(f"{ACCOUNT_URL}/models").respond(json={"value": []})
    with pytest.raises(DeploymentDiscoveryError):
        await async_discover_deployments(hass, RESOURCE_ID, "management-token")


@pytest.mark.parametrize(
    ("state", "sku", "reason"),
    [
        ("Failed", "GlobalStandard", "deployment state"),
        ("Succeeded", "GlobalBatch", "batch-only"),
    ],
)
async def test_unusable_deployments_reported(
    hass: HomeAssistant, respx_mock: MockRouter, state: str, sku: str, reason: str
) -> None:
    """Do not create interactive services for failed or batch-only deployments."""
    respx_mock.get(ACCOUNT_URL).respond(json={"properties": {"endpoint": ENDPOINT}})
    respx_mock.get(f"{ACCOUNT_URL}/deployments").respond(
        json={
            "value": [
                {
                    "name": "ha-chat",
                    "sku": {"name": sku},
                    "properties": {
                        "model": {"format": "OpenAI", "name": "gpt-6.1-sol"},
                        "capabilities": {"chatCompletion": "true"},
                        "provisioningState": state,
                    },
                }
            ]
        }
    )
    result = await async_discover_deployments(hass, RESOURCE_ID, "management-token")
    assert not result.deployments[0]["services"]
    assert reason in result.deployments[0]["unsupported_reason"]


def test_legacy_default_is_made_explicit(hass: HomeAssistant) -> None:
    """Keep a legacy default deployment explicit when it is matched by discovery."""
    inventory = [
        DeploymentData(
            id=f"{RESOURCE_ID}/deployments/gpt-4o-mini",
            name="gpt-4o-mini",
            model_name="gpt-4o-mini",
            services=["conversation", "ai_task_data"],
            unsupported_reason="",
        )
    ]
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DEPLOYMENTS: inventory},
        subentries_data=[
            {
                "subentry_type": "conversation",
                "title": "Existing assistant",
                "unique_id": None,
                "data": {"recommended": True},
            }
        ],
    )
    entry.add_to_hass(hass)
    existing = next(iter(entry.subentries.values()))
    assert sync_deployment_subentries(hass, entry)
    assert len(entry.subentries) == 1
    assert existing.data[CONF_CHAT_MODEL] == "gpt-4o-mini"
    assert not sync_deployment_subentries(hass, entry)


def test_missing_services_exclude_added_and_legacy_defaults(
    hass: HomeAssistant, deployment_inventory: list[DeploymentData]
) -> None:
    """Offer only compatible services that the entry does not already provide."""
    assert missing_deployment_services(None, deployment_inventory) == (
        deployment_inventory
    )
    legacy = DeploymentData(
        id=f"{RESOURCE_ID}/deployments/gpt-4o-mini",
        name="gpt-4o-mini",
        model_name="gpt-4o-mini",
        services=["conversation", "ai_task_data"],
        unsupported_reason="",
    )
    inventory = [*deployment_inventory, legacy]
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DEPLOYMENTS: inventory},
        subentries_data=[
            *(
                item
                for item in deployment_subentries(deployment_inventory)
                if item["subentry_type"] != "tts"
            ),
            {
                "subentry_type": "conversation",
                "title": "Existing assistant",
                "unique_id": None,
                "data": {"recommended": True},
            },
        ],
    )
    entry.add_to_hass(hass)
    missing = missing_deployment_services(entry, inventory)
    assert [item["name"] for item in missing] == [item["name"] for item in inventory]
    assert {item["name"]: item["services"] for item in missing if item["services"]} == {
        "gpt-4o-mini": ["ai_task_data"],
        "speak": ["tts"],
    }
    assert legacy["services"] == ["conversation", "ai_task_data"]
