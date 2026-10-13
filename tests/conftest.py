"""Shared Home Assistant fixtures for Azure OpenAI integration tests."""

from collections.abc import Generator
import time
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.components.homeassistant.const import DATA_EXPOSED_ENTITIES
from homeassistant.components.homeassistant.exposed_entities import ExposedEntities
from homeassistant.helpers import config_entry_oauth2_flow
import pytest

from custom_components.azure_openai_conversation.auth import EntraOAuth2Implementation
from custom_components.azure_openai_conversation.const import (
    AUTH_ENTRA_ID,
    CONF_API_BASE,
    CONF_AUTH_TYPE,
    CONF_RESOURCE_ID,
    CONF_TENANT_ID,
    DOMAIN,
)
from custom_components.azure_openai_conversation.deployments import DeploymentData

from .const import ENDPOINT, RESOURCE_ID, TENANT_ID


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations: None) -> None:
    """Enable the repository's custom integration."""


@pytest.fixture
async def native_exposed_entities(hass: HomeAssistant) -> ExposedEntities:
    """Initialize native Assist exposure state normally supplied by core startup."""
    exposed = ExposedEntities(hass)
    await exposed.async_initialize()
    hass.data[DATA_EXPOSED_ENTITIES] = exposed
    return exposed


@pytest.fixture
def oauth_data() -> dict:
    """Provide valid Microsoft sign-in entry data without using real credentials."""
    return {
        CONF_AUTH_TYPE: AUTH_ENTRA_ID,
        CONF_TENANT_ID: TENANT_ID,
        CONF_RESOURCE_ID: RESOURCE_ID,
        CONF_API_BASE: ENDPOINT,
        "auth_implementation": DOMAIN,
        "token": {
            "access_token": "inference-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "expires_at": time.time() + 3600,
        },
    }


@pytest.fixture
def oauth_implementation(hass: HomeAssistant) -> EntraOAuth2Implementation:
    """Register independent, user-provided application credentials."""
    implementation = EntraOAuth2Implementation(
        hass, DOMAIN, "test-client-id", "test-client-secret"
    )
    config_entry_oauth2_flow.async_register_implementation(hass, DOMAIN, implementation)
    return implementation


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Keep config-flow tests independent of platform initialization."""
    with patch(
        "custom_components.azure_openai_conversation.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock


@pytest.fixture
def deployment_inventory() -> list[DeploymentData]:
    """Include multiple model families and one explicitly unsupported deployment."""
    return [
        DeploymentData(
            id=f"{RESOURCE_ID}/deployments/{name}",
            name=name,
            model_name=model,
            services=services,
            unsupported_reason=reason,
        )
        for name, model, services, reason in (
            ("ha-chat", "gpt-6.1-sol", ["conversation", "ai_task_data"], ""),
            ("daily-chat", "gpt-4.1-mini", ["conversation", "ai_task_data"], ""),
            ("art", "gpt-image-1", ["ai_task_image"], ""),
            ("listen", "gpt-4o-mini-transcribe", ["stt"], ""),
            ("speak", "tts-1", ["tts"], ""),
            ("search", "text-embedding-3-large", [], "no supported API"),
        )
    ]
