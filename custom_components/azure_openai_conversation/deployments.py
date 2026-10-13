"""Discover actual OpenAI deployments and reconcile capability-matched services."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Any, TypedDict
from urllib.parse import urljoin, urlsplit
from uuid import UUID

from homeassistant.config_entries import ConfigEntry, ConfigSubentry, ConfigSubentryData
from homeassistant.const import CONF_PROMPT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client

from .const import (
    CONF_AUTO_DISCOVERED,
    CONF_CHAT_MODEL,
    CONF_DEPLOYMENTS,
    CONF_IMAGE_MODEL,
    CONF_MODEL_NAME,
    DEFAULT_AI_TASK_NAME,
    DEFAULT_CONVERSATION_NAME,
    DEFAULT_IMAGE_TASK_NAME,
    DEFAULT_STT_NAME,
    DEFAULT_STT_PROMPT,
    DEFAULT_TTS_NAME,
    LOGGER,
    RECOMMENDED_AI_TASK_OPTIONS,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_CONVERSATION_OPTIONS,
    RECOMMENDED_IMAGE_MODEL,
    RECOMMENDED_STT_MODEL,
    RECOMMENDED_TTS_MODEL,
    RECOMMENDED_TTS_OPTIONS,
    UNSUPPORTED_MODELS,
)

MANAGEMENT_ORIGIN = "https://management.azure.com"
MANAGEMENT_API_VERSION = "2024-10-01"
_RESOURCE_PATH = re.compile(
    r"/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/"
    r"Microsoft\.CognitiveServices/accounts/([a-zA-Z0-9][a-zA-Z0-9_.-]{1,63})",
    re.IGNORECASE,
)
_RESOURCE_GROUP = re.compile(r"[\w.()-]+", re.ASCII)
_DEPLOYMENT_NAME = re.compile(r"[a-zA-Z0-9_.-]{1,64}")

_SERVICE_NAMES = {
    "conversation": DEFAULT_CONVERSATION_NAME,
    "ai_task_data": DEFAULT_AI_TASK_NAME,
    "ai_task_image": DEFAULT_IMAGE_TASK_NAME,
    "stt": DEFAULT_STT_NAME,
    "tts": DEFAULT_TTS_NAME,
}
_MODEL_KEYS = {
    "conversation": CONF_CHAT_MODEL,
    "ai_task_data": CONF_CHAT_MODEL,
    "ai_task_image": CONF_IMAGE_MODEL,
    "stt": CONF_CHAT_MODEL,
    "tts": CONF_CHAT_MODEL,
}
_LEGACY_MODELS = {
    "conversation": RECOMMENDED_CHAT_MODEL,
    "ai_task_data": RECOMMENDED_CHAT_MODEL,
    "ai_task_image": RECOMMENDED_IMAGE_MODEL,
    "stt": RECOMMENDED_STT_MODEL,
    "tts": RECOMMENDED_TTS_MODEL,
}


class DeploymentDiscoveryError(ValueError):
    """The discovery response cannot safely identify usable deployments."""


class DeploymentData(TypedDict):
    """Persist only deployment identity and the services supported by this integration."""

    id: str
    name: str
    model_name: str
    services: list[str]
    unsupported_reason: str


@dataclass(frozen=True)
class DeploymentDiscovery:
    """A validated resource endpoint and its actual OpenAI deployment inventory."""

    endpoint: str
    deployments: list[DeploymentData]


def validate_resource_id(value: str) -> str:
    """Validate a Cognitive Services account ARM ID, not a URL or child resource."""
    if not (match := _RESOURCE_PATH.fullmatch(value.strip().rstrip("/"))):
        raise ValueError("Expected a Cognitive Services account resource ID")
    subscription, resource_group, account = match.groups()
    subscription = str(UUID(subscription))
    if (
        not _RESOURCE_GROUP.fullmatch(resource_group)
        or len(resource_group) > 90
        or resource_group.endswith(".")
    ):
        raise ValueError("Invalid resource group name")
    return (
        f"/subscriptions/{subscription}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.CognitiveServices/accounts/{account}"
    )


def supported_services(
    model_name: str, capabilities: Mapping[str, Any]
) -> tuple[str, ...]:
    """Map supported APIs, using the underlying model rather than its deployment alias."""
    model = model_name.lower()
    if (
        model in UNSUPPORTED_MODELS
        or model.startswith(("o1-mini", "o1-preview", "gpt-live-transcribe"))
        or any(
            part in model
            for part in ("realtime", "-audio", "diarize", "search-preview")
        )
    ):
        return ()
    normalized = {
        re.sub(r"[^a-z]", "", key.lower()): value is True
        or (isinstance(value, str) and value.lower() == "true")
        for key, value in capabilities.items()
    }
    if model.startswith(("gpt-image-", "dall-e-")):
        return ("ai_task_image",)
    if model in ("whisper", "whisper-1") or "-transcribe" in model:
        return ("stt",)
    if model == "tts" or model.startswith("tts-") or model.endswith("-tts"):
        return ("tts",)
    if "responses" in normalized:
        return ("conversation", "ai_task_data") if normalized["responses"] else ()
    # Chat completions alone do not imply Responses API compatibility.
    if normalized.get("chatcompletion", True) and model.startswith(
        ("gpt-4o", "gpt-4.1", "gpt-5", "gpt-6", "gpt-chat-latest", "o1", "o3", "o4")
    ):
        return ("conversation", "ai_task_data")
    return ()


def validate_inference_endpoint(endpoint: str) -> str:
    """Restrict Entra bearer tokens to HTTPS endpoints on the Azure public cloud."""
    try:
        parsed = urlsplit(endpoint)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname
            and parsed.hostname.endswith(
                (
                    ".openai.azure.com",
                    ".services.ai.azure.com",
                    ".cognitiveservices.azure.com",
                )
            )
            and parsed.port in (None, 443)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError as err:
        raise DeploymentDiscoveryError("Invalid Azure inference endpoint") from err
    if not valid:
        raise DeploymentDiscoveryError(
            "Resource has no trusted Azure inference endpoint"
        )
    return f"https://{parsed.hostname}/"


def _resource_endpoint(properties: Mapping[str, Any]) -> str:
    """Select an Azure inference endpoint without exposing OAuth tokens to a gateway."""
    candidates = [properties.get("endpoint")]
    endpoints = properties.get("endpoints", {})
    if isinstance(endpoints, dict):
        candidates.extend(endpoints.values())
    for endpoint in candidates:
        if not isinstance(endpoint, str):
            continue
        try:
            return validate_inference_endpoint(endpoint)
        except DeploymentDiscoveryError:
            continue
    raise DeploymentDiscoveryError("Resource has no trusted Azure inference endpoint")


def _is_openai_model(model: Mapping[str, Any]) -> bool:
    """Filter on the publisher, falling back to the ARM model format."""
    publisher = model.get("publisher") or model.get("format")
    if not isinstance(publisher, str):
        raise DeploymentDiscoveryError("Azure returned an invalid model publisher")
    return publisher.lower() == "openai"


async def async_discover_deployments(
    hass: HomeAssistant, resource_id: str, access_token: str
) -> DeploymentDiscovery:
    """Read the selected account's deployments, never treating catalog models as deployed."""
    resource_id = validate_resource_id(resource_id)
    client = get_async_client(hass)
    headers = {"Authorization": f"Bearer {access_token}"}

    async def get_json(url: str) -> dict[str, Any]:
        response = await client.get(
            url, headers=headers, timeout=10.0, follow_redirects=False
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as err:
            raise DeploymentDiscoveryError("Azure returned invalid JSON") from err
        if not isinstance(payload, dict):
            raise DeploymentDiscoveryError("Azure returned a non-object response")
        return payload

    async def list_records(collection: str) -> list[dict[str, Any]]:
        path = f"{resource_id}/{collection}"
        url = f"{MANAGEMENT_ORIGIN}{path}?api-version={MANAGEMENT_API_VERSION}"
        visited: set[str] = set()
        records: list[dict[str, Any]] = []
        while url:
            try:
                parsed = urlsplit(url)
                port = parsed.port
            except ValueError as err:
                raise DeploymentDiscoveryError("Invalid Azure pagination link") from err
            if (
                parsed.scheme != "https"
                or parsed.hostname != "management.azure.com"
                or port not in (None, 443)
                or parsed.username is not None
                or parsed.password is not None
                or parsed.fragment
                or parsed.path.lower() != path.lower()
                or url in visited
            ):
                raise DeploymentDiscoveryError("Invalid Azure pagination link")
            visited.add(url)
            payload = await get_json(url)
            values = payload.get("value")
            if not isinstance(values, list) or any(
                not isinstance(record, dict) for record in values
            ):
                raise DeploymentDiscoveryError("Azure returned an invalid collection")
            records.extend(values)
            next_link = payload.get("nextLink")
            if next_link is not None and not isinstance(next_link, str):
                raise DeploymentDiscoveryError(
                    "Azure returned an invalid pagination link"
                )
            url = urljoin(url, next_link) if next_link else ""
        return records

    account = await get_json(
        f"{MANAGEMENT_ORIGIN}{resource_id}?api-version={MANAGEMENT_API_VERSION}"
    )
    properties = account.get("properties")
    if not isinstance(properties, dict):
        raise DeploymentDiscoveryError("Azure returned invalid account properties")
    endpoint = _resource_endpoint(properties)
    records = await list_records("deployments")
    openai_records: list[dict[str, Any]] = []
    for record in records:
        properties = record.get("properties")
        if not isinstance(properties, dict) or not isinstance(
            model := properties.get("model"), dict
        ):
            raise DeploymentDiscoveryError(
                "Azure returned invalid deployment properties"
            )
        if _is_openai_model(model):
            openai_records.append(record)

    # The catalog is used only to enrich already-deployed models with capabilities.
    catalog = (
        await list_records("models")
        if any(
            not record["properties"].get("capabilities") for record in openai_records
        )
        else []
    )
    deployments: list[DeploymentData] = []
    names: set[str] = set()
    for record in openai_records:
        properties = record["properties"]
        model = properties["model"]
        name, model_name = record.get("name"), model.get("name")
        if (
            not isinstance(name, str)
            or not _DEPLOYMENT_NAME.fullmatch(name)
            or not isinstance(model_name, str)
            or not model_name
            or name in names
        ):
            raise DeploymentDiscoveryError(
                "Azure returned an invalid deployment identity"
            )
        names.add(name)
        capabilities = properties.get("capabilities") or next(
            (
                item.get("capabilities", {})
                for item in catalog
                if item.get("name") == model_name
                and item.get("version") == model.get("version")
                and _is_openai_model(item)
            ),
            {},
        )
        if not isinstance(capabilities, dict) or any(
            not isinstance(key, str) for key in capabilities
        ):
            raise DeploymentDiscoveryError("Azure returned invalid model capabilities")
        sku = record.get("sku", {})
        if not isinstance(sku, dict):
            raise DeploymentDiscoveryError("Azure returned an invalid deployment SKU")
        services = supported_services(model_name, capabilities)
        reason = ""
        if str(properties.get("provisioningState", "")).lower() != "succeeded":
            services = ()
            reason = (
                f"deployment state: {properties.get('provisioningState', 'unknown')}"
            )
        elif "batch" in str(sku.get("name", "")).lower():
            services = ()
            reason = "batch-only deployment"
        elif not services:
            reason = "no supported conversation, AI-task, image, STT, or TTS API"
        deployments.append(
            DeploymentData(
                id=f"{resource_id}/deployments/{name}",
                name=name,
                model_name=model_name,
                services=list(services),
                unsupported_reason=reason,
            )
        )
    return DeploymentDiscovery(
        endpoint, sorted(deployments, key=lambda item: item["name"])
    )


def deployment_subentries(
    deployments: Iterable[DeploymentData],
    selected_models: Mapping[str, Iterable[str]] | None = None,
) -> list[ConfigSubentryData]:
    """Build compatible services, optionally limited to explicitly selected models."""
    subentries: list[ConfigSubentryData] = []
    for deployment in deployments:
        for service in deployment["services"]:
            if selected_models is not None and deployment[
                "name"
            ] not in selected_models.get(service, ()):
                continue
            data: dict[str, Any] = {
                _MODEL_KEYS[service]: deployment["name"],
                CONF_MODEL_NAME: deployment["model_name"],
                CONF_AUTO_DISCOVERED: True,
            }
            if service == "conversation":
                data = {**RECOMMENDED_CONVERSATION_OPTIONS, **data}
            elif service == "ai_task_data":
                data = {**RECOMMENDED_AI_TASK_OPTIONS, **data}
            elif service == "stt":
                data[CONF_PROMPT] = DEFAULT_STT_PROMPT
            elif service == "tts":
                data = {**RECOMMENDED_TTS_OPTIONS, **data}
            subentries.append(
                ConfigSubentryData(
                    subentry_type=service,
                    title=f"{_SERVICE_NAMES[service]} {deployment['name']}",
                    data=data,
                    unique_id=f"{deployment['id'].lower()}:{service}",
                )
            )
    return subentries


def _existing_subentries(
    entry: ConfigEntry, service: str, deployment_name: str
) -> list[ConfigSubentry]:
    """Return services of one type that already use a deployment."""
    model_key = _MODEL_KEYS[service]
    return [
        subentry
        for subentry in entry.subentries.values()
        if subentry.subentry_type == service
        and subentry.data.get(model_key, _LEGACY_MODELS[service]) == deployment_name
    ]


def missing_deployment_services(
    entry: ConfigEntry | None, deployments: Iterable[DeploymentData]
) -> list[DeploymentData]:
    """Limit each deployment to compatible services not yet added to the entry."""
    if entry is None:
        return list(deployments)
    return [
        DeploymentData(
            id=deployment["id"],
            name=deployment["name"],
            model_name=deployment["model_name"],
            services=[
                service
                for service in deployment["services"]
                if not _existing_subentries(entry, service, deployment["name"])
            ],
            unsupported_reason=deployment["unsupported_reason"],
        )
        for deployment in deployments
    ]


def sync_deployment_subentries(
    hass: HomeAssistant,
    entry: ConfigEntry,
    additions: Iterable[ConfigSubentryData] = (),
) -> bool:
    """Refresh existing metadata and add only explicitly requested missing services."""
    changed = False
    selected_ids = {candidate["unique_id"] for candidate in additions}
    for candidate in deployment_subentries(entry.data.get(CONF_DEPLOYMENTS, [])):
        service = candidate["subentry_type"]
        model_key = _MODEL_KEYS[service]
        deployment = candidate["data"][model_key]
        if existing := _existing_subentries(entry, service, deployment):
            for subentry in existing:
                updates = {
                    model_key: deployment,
                    CONF_MODEL_NAME: candidate["data"][CONF_MODEL_NAME],
                }
                if any(
                    subentry.data.get(key) != value for key, value in updates.items()
                ):
                    hass.config_entries.async_update_subentry(
                        entry,
                        subentry,
                        data={
                            **subentry.data,
                            **updates,
                        },
                    )
                    changed = True
            continue
        if candidate["unique_id"] not in selected_ids:
            continue
        hass.config_entries.async_add_subentry(
            entry,
            ConfigSubentry(
                data=MappingProxyType(candidate["data"]),
                subentry_type=service,
                title=candidate["title"],
                unique_id=candidate["unique_id"],
            ),
        )
        changed = True
    for deployment in entry.data.get(CONF_DEPLOYMENTS, []):
        if reason := deployment["unsupported_reason"]:
            LOGGER.debug(
                "OpenAI deployment `%s` (%s) was not added: %s",
                deployment["name"],
                deployment["model_name"],
                reason,
            )
    return changed
