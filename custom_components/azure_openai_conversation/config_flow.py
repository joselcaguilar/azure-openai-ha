"""Config flow for Azure OpenAI Conversation integration."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
import logging
import time
from typing import Any, cast, override
from uuid import UUID

import httpx
import openai
import probatio
from probatio import to_openapi

from homeassistant.components.zone import ENTITY_ID_HOME
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigEntryState,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import (
    CONF_API_KEY,
    CONF_LLM_HASS_API,
    CONF_NAME,
    CONF_PROMPT,
    EntityStateAttribute,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import (
    OAuth2TokenRequestConnectionError,
    OAuth2TokenRequestError,
    OAuth2TokenRequestReauthError,
)
from homeassistant.helpers import config_entry_oauth2_flow, llm
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TemplateSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.typing import VolDictType

from . import create_client
from .auth import EntraOAuth2Implementation, async_get_oauth_implementation
from .const import (
    AUTH_API_KEY,
    AUTH_ENTRA_ID,
    CONF_API_BASE,
    CONF_AUTH_TYPE,
    CONF_AUTO_DISCOVERED,
    CONF_CHAT_MODEL,
    CONF_CODE_INTERPRETER,
    CONF_IMAGE_MODEL,
    CONF_DEPLOYMENTS,
    CONF_MAX_TOKENS,
    CONF_MODEL_NAME,
    CONF_PRO_MODE,
    CONF_REASONING_EFFORT,
    CONF_REASONING_SUMMARY,
    CONF_RECOMMENDED,
    CONF_SEND_SAMPLING_PARAMETERS,
    CONF_STORE_RESPONSES,
    CONF_RESOURCE_ID,
    CONF_TEMPERATURE,
    CONF_TENANT_ID,
    CONF_TOP_P,
    CONF_TTS_SPEED,
    CONF_VERBOSITY,
    CONF_WEB_SEARCH,
    CONF_WEB_SEARCH_CITY,
    CONF_WEB_SEARCH_CONTEXT_SIZE,
    CONF_WEB_SEARCH_COUNTRY,
    CONF_WEB_SEARCH_INLINE_CITATIONS,
    CONF_WEB_SEARCH_REGION,
    CONF_WEB_SEARCH_TIMEZONE,
    CONF_WEB_SEARCH_USER_LOCATION,
    DEFAULT_AI_TASK_NAME,
    DEFAULT_CONVERSATION_NAME,
    DEFAULT_NAME,
    DEFAULT_IMAGE_TASK_NAME,
    DEFAULT_STT_NAME,
    DEFAULT_STT_PROMPT,
    DEFAULT_TTS_NAME,
    DOMAIN,
    IMAGE_MODELS,
    RECOMMENDED_AI_TASK_OPTIONS,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_CODE_INTERPRETER,
    RECOMMENDED_CONVERSATION_OPTIONS,
    RECOMMENDED_IMAGE_MODEL,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_PRO_MODE,
    RECOMMENDED_REASONING_SUMMARY,
    RECOMMENDED_SEND_SAMPLING_PARAMETERS,
    RECOMMENDED_STORE_RESPONSES,
    RECOMMENDED_STT_MODEL,
    RECOMMENDED_STT_OPTIONS,
    RECOMMENDED_TEMPERATURE,
    RECOMMENDED_TOP_P,
    RECOMMENDED_TTS_MODEL,
    RECOMMENDED_TTS_OPTIONS,
    RECOMMENDED_TTS_SPEED,
    RECOMMENDED_VERBOSITY,
    RECOMMENDED_WEB_SEARCH,
    RECOMMENDED_WEB_SEARCH_CONTEXT_SIZE,
    RECOMMENDED_WEB_SEARCH_INLINE_CITATIONS,
    RECOMMENDED_WEB_SEARCH_USER_LOCATION,
    STT_MODELS,
    TTS_MODELS,
    UNSUPPORTED_CODE_INTERPRETER_MODELS,
    UNSUPPORTED_MODELS,
    UNSUPPORTED_WEB_SEARCH_MODELS,
    get_reasoning_options,
    get_recommended_reasoning_effort,
)
from .deployments import (
    DeploymentData,
    DeploymentDiscovery,
    DeploymentDiscoveryError,
    async_discover_deployments,
    deployment_subentries,
    missing_deployment_services,
    sync_deployment_subentries,
    validate_resource_id,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_API_KEY): str,
        probatio.Required(CONF_API_BASE): str,
    }
)
STEP_REAUTH_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_API_KEY): str,
    }
)


class _SamplingNumberSelector(NumberSelector):
    """Show a sampling control only while its native form checkbox is enabled."""

    @override
    def serialize(self) -> dict[str, Any]:
        """Include the frontend's field visibility condition."""
        return {
            **super().serialize(),
            "visible": {"field": CONF_SEND_SAMPLING_PARAMETERS, "value": True},
        }


def _deployment_choices(
    deployments: Iterable[DeploymentData] | None,
    service: str,
    fallback: Iterable[str] = (),
) -> list[SelectOptionDict | str]:
    """Use discovered deployment names, retaining manual values for API-key entries."""
    if deployments is None:
        return list(fallback)
    return [
        SelectOptionDict(
            value=deployment["name"],
            label=f"{deployment['name']} ({deployment['model_name']})",
        )
        for deployment in deployments
        if service in deployment["services"]
    ]


def _default_deployment(entry: ConfigEntry, service: str, fallback: str) -> str:
    """Suggest a real deployment rather than an undeployed recommended model."""
    if CONF_DEPLOYMENTS not in entry.data:
        return fallback
    return next(
        (
            deployment["name"]
            for deployment in entry.data[CONF_DEPLOYMENTS]
            if service in deployment["services"]
        ),
        "",
    )


def _known_model_name(
    flow: ConfigSubentryFlow, model_key: str, selected: str
) -> str | None:
    """Resolve current discovery metadata or an unchanged subentry's known model."""
    for deployment in flow._get_entry().data.get(CONF_DEPLOYMENTS, []):
        if deployment["name"] == selected:
            return deployment["model_name"]
    if flow.source != "user":
        subentry = flow._get_reconfigure_subentry()
        if subentry.data.get(model_key) == selected:
            return subentry.data.get(CONF_MODEL_NAME)
    return None


def _save_subentry(
    flow: ConfigSubentryFlow, options: dict[str, Any]
) -> SubentryFlowResult:
    """Persist options and resolve model metadata without changing entity identities."""
    entry = flow._get_entry()
    model_key = (
        CONF_IMAGE_MODEL if flow._subentry_type == "ai_task_image" else CONF_CHAT_MODEL
    )
    selected = options[model_key]
    options = dict(options)
    subentry = None if flow.source == "user" else flow._get_reconfigure_subentry()
    model_changed = subentry is None or subentry.data.get(model_key) != selected
    if model_name := _known_model_name(flow, model_key, selected):
        options[CONF_MODEL_NAME] = model_name
    else:
        options.pop(CONF_MODEL_NAME, None)
    if flow.source == "user":
        return flow.async_create_entry(
            title=options.pop(CONF_NAME),
            data=options,
        )
    if subentry is None:
        raise ValueError("A reconfigure flow requires a config subentry")
    if model_changed:
        options.pop(CONF_AUTO_DISCOVERED, None)
        return flow.async_update_and_abort(
            entry, subentry, data=options, unique_id=None
        )
    return flow.async_update_and_abort(entry, subentry, data=options)


def _model_supported(flow: ConfigSubentryFlow, model: str, service: str) -> bool:
    """Validate discovered capabilities while allowing unchanged legacy deployments."""
    if not model.strip():
        return False
    entry = flow._get_entry()
    if CONF_DEPLOYMENTS not in entry.data:
        return model not in UNSUPPORTED_MODELS
    if any(
        deployment["name"] == model and service in deployment["services"]
        for deployment in entry.data[CONF_DEPLOYMENTS]
    ):
        return True
    model_key = CONF_IMAGE_MODEL if service == "ai_task_image" else CONF_CHAT_MODEL
    return flow.source == SOURCE_RECONFIGURE and (
        flow._get_reconfigure_subentry().data.get(model_key) == model
    )


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    client = create_client(hass, data[CONF_API_BASE], data[CONF_API_KEY])
    await hass.async_add_executor_job(client.platform_headers)
    await client.models.list(timeout=10.0)


class AzureOpenAIConfigFlow(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Handle a config flow for Azure OpenAI Conversation."""

    DOMAIN = DOMAIN
    VERSION = 2
    MINOR_VERSION = 2

    def __init__(self) -> None:
        """Initialize authentication and discovery state."""
        super().__init__()
        self._settings: dict[str, Any] = {}
        self._oauth_data: dict[str, Any] = {}
        self._signed_in = False
        self._discovery: DeploymentDiscovery | None = None

    @property
    @override
    def logger(self) -> logging.Logger:
        """Return the integration's config flow logger."""
        return _LOGGER

    def _existing_entry(self) -> ConfigEntry | None:
        """Return the entry being reauthenticated or reconfigured."""
        if self.source == SOURCE_REAUTH:
            return self._get_reauth_entry()
        if self.source == SOURCE_RECONFIGURE:
            return self._get_reconfigure_entry()
        return None

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is not None and CONF_API_KEY in user_input:
            return await self.async_step_api_key(user_input)
        return self.async_show_menu(
            step_id="user", menu_options=["entra_id", "api_key"]
        )

    async def async_step_api_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Keep manual API-key setup available for existing users and gateways."""
        return await self._async_step_api_key(user_input, "api_key")

    async def _async_step_api_key(
        self, user_input: dict[str, Any] | None, step_id: str
    ) -> ConfigFlowResult:
        """Handle an API key form."""
        errors: dict[str, str] = {}
        entry = self._existing_entry()

        if user_input is not None:
            if entry is None:
                self._async_abort_entries_match(user_input)
            try:
                await validate_input(
                    self.hass, {**(entry.data if entry else {}), **user_input}
                )
            except openai.APIConnectionError, openai.NotFoundError:
                errors["base"] = "cannot_connect"
            except openai.AuthenticationError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                data = {
                    CONF_AUTH_TYPE: AUTH_API_KEY,
                    CONF_API_BASE: user_input.get(
                        CONF_API_BASE, entry.data[CONF_API_BASE] if entry else None
                    ),
                    CONF_API_KEY: user_input[CONF_API_KEY],
                }
                if entry is not None:
                    if entry.update_listeners:
                        return self.async_update_and_abort(entry, data=data)
                    return self.async_update_reload_and_abort(entry, data=data)
                return self.async_create_entry(
                    title=DEFAULT_NAME,
                    data=data,
                    subentries=[
                        {
                            "subentry_type": "conversation",
                            "data": RECOMMENDED_CONVERSATION_OPTIONS,
                            "title": DEFAULT_CONVERSATION_NAME,
                            "unique_id": None,
                        },
                        {
                            "subentry_type": "ai_task_data",
                            "data": RECOMMENDED_AI_TASK_OPTIONS,
                            "title": DEFAULT_AI_TASK_NAME,
                            "unique_id": None,
                        },
                    ],
                )

        if step_id == "reauth_confirm":
            schema = STEP_REAUTH_DATA_SCHEMA
        else:
            schema = STEP_USER_DATA_SCHEMA
        suggested_values = user_input
        if suggested_values is None and entry is not None:
            suggested_values = {CONF_API_BASE: entry.data[CONF_API_BASE]}

        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, suggested_values),
            errors=errors,
            description_placeholders={
                "example_url": "https://xyz.services.ai.azure.com"
            },
        )

    async def async_step_entra_id(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the resource and tenant before linking the Microsoft account."""
        entry = self._existing_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                resource_id = validate_resource_id(user_input[CONF_RESOURCE_ID])
            except ValueError:
                errors[CONF_RESOURCE_ID] = "invalid_resource_id"
            try:
                tenant_id = str(UUID(user_input[CONF_TENANT_ID].strip()))
            except ValueError:
                errors[CONF_TENANT_ID] = "invalid_tenant_id"
            if not errors:
                self._settings = {
                    CONF_AUTH_TYPE: AUTH_ENTRA_ID,
                    CONF_RESOURCE_ID: resource_id,
                    CONF_TENANT_ID: tenant_id,
                }
                if (
                    entry is not None
                    and entry.data.get(CONF_AUTH_TYPE) == AUTH_ENTRA_ID
                    and entry.data[CONF_TENANT_ID] == tenant_id
                ):
                    try:
                        self.flow_impl = await async_get_oauth_implementation(
                            self.hass, entry
                        )
                    except config_entry_oauth2_flow.UnknownImplementationError:
                        return await self.async_step_pick_implementation()
                    else:
                        self._oauth_data = {
                            "auth_implementation": entry.data["auth_implementation"],
                            "token": dict(entry.data["token"]),
                        }
                        return await self.async_step_discovery()
                return await self.async_step_pick_implementation()

        suggested = user_input or (
            {
                key: entry.data[key]
                for key in (CONF_RESOURCE_ID, CONF_TENANT_ID)
                if key in entry.data
            }
            if entry
            else None
        )
        return self.async_show_form(
            step_id="entra_id",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(
                    {
                        probatio.Required(CONF_TENANT_ID): str,
                        probatio.Required(CONF_RESOURCE_ID): str,
                    }
                ),
                suggested,
            ),
            errors=errors,
        )

    @override
    async def async_step_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Use a separate tenant-bound PKCE verifier for each browser flow."""
        if user_input is None:
            if not isinstance(self.flow_impl, EntraOAuth2Implementation):
                return self.async_abort(reason="oauth_implementation_unavailable")
            self.flow_impl = self.flow_impl.with_tenant(self._settings[CONF_TENANT_ID])
        return await super().async_step_auth(user_input)

    @override
    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Discover deployments before committing the authorized integration."""
        self._oauth_data = data
        self._signed_in = True
        return await self.async_step_discovery()

    async def async_step_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """List all actual OpenAI deployments, with an explicit retry on failure."""
        errors: dict[str, str] = {}
        self._discovery = None
        try:
            token = self._oauth_data["token"]
            if token["expires_at"] <= time.time() + 30:
                token = await self.flow_impl.async_refresh_token(token)
                self._oauth_data["token"] = token
            management_token = await cast(
                EntraOAuth2Implementation, self.flow_impl
            ).async_get_management_token(token)
            self._discovery = await async_discover_deployments(
                self.hass, self._settings[CONF_RESOURCE_ID], management_token
            )
            if deployment_subentries(self._discovery.deployments):
                await validate_input(
                    self.hass,
                    {
                        CONF_API_BASE: self._discovery.endpoint,
                        CONF_API_KEY: token["access_token"],
                    },
                )
        except OAuth2TokenRequestReauthError:
            if not self._signed_in:
                return await self.async_step_pick_implementation(
                    {"implementation": self._oauth_data["auth_implementation"]}
                )
            # Signing in again cannot fix missing consent or a Conditional Access block.
            _LOGGER.warning("Microsoft denied the token for deployment discovery")
            errors["base"] = "deployment_access_denied"
        except OAuth2TokenRequestError, OAuth2TokenRequestConnectionError:
            _LOGGER.warning(
                "Microsoft token request failed during deployment discovery"
            )
            errors["base"] = "cannot_connect"
        except httpx.HTTPStatusError as err:
            _LOGGER.warning(
                "Azure deployment discovery failed with HTTP %s",
                err.response.status_code,
            )
            errors["base"] = {
                401: "invalid_auth",
                403: "deployment_access_denied",
                404: "resource_not_found",
            }.get(err.response.status_code, "cannot_connect")
        except httpx.RequestError:
            _LOGGER.warning("Unable to connect to Azure deployment discovery")
            errors["base"] = "cannot_connect"
        except openai.AuthenticationError:
            _LOGGER.warning("Microsoft inference token was rejected by Azure")
            errors["base"] = "invalid_auth"
        except openai.PermissionDeniedError:
            _LOGGER.warning("The signed-in user has no Azure OpenAI inference access")
            errors["base"] = "inference_access_denied"
        except openai.OpenAIError:
            _LOGGER.warning("Unable to validate the Azure OpenAI inference endpoint")
            errors["base"] = "cannot_connect"
        except DeploymentDiscoveryError as err:
            _LOGGER.error("Invalid Azure deployment discovery response: %s", err)
            errors["base"] = "invalid_discovery_response"
        else:
            if not self._discovery.deployments:
                errors["base"] = "no_openai_deployments"
            elif not deployment_subentries(self._discovery.deployments):
                errors["base"] = "no_supported_deployments"
            else:
                return await self.async_step_discovery_confirm()

        return self.async_show_form(
            step_id="discovery",
            data_schema=probatio.Schema({}),
            errors=errors,
            description_placeholders=self._discovery_summary(),
        )

    def _discovery_summary(self) -> dict[str, str]:
        """Count services left to add and name unsupported models without tokens."""
        deployments = self._discovery.deployments if self._discovery else []
        missing = missing_deployment_services(self._existing_entry(), deployments)
        # Reasons stay in debug logs; translated descriptions explain the categories.
        return {
            "unsupported": "\n".join(
                f"- {item['name']} ({item['model_name']})"
                for item in deployments
                if item["unsupported_reason"]
            )
            or "—",
            "service_count": str(len(deployment_subentries(missing))),
        }

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select deployments separately for each service, preserving existing services."""
        if self._discovery is None:
            return await self.async_step_discovery()
        if user_input is None:
            entry = self._existing_entry()
            missing = missing_deployment_services(entry, self._discovery.deployments)
            if entry is not None and not deployment_subentries(missing):
                return await self.async_step_discovery_all_added()
            schema: VolDictType = {}
            for service in (
                "conversation",
                "ai_task_data",
                "ai_task_image",
                "stt",
                "tts",
            ):
                if choices := _deployment_choices(missing, service):
                    schema[probatio.Optional(service, default=list)] = SelectSelector(
                        SelectSelectorConfig(
                            options=choices,
                            multiple=True,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
            return self.async_show_form(
                step_id="discovery_confirm",
                data_schema=probatio.Schema(schema),
                description_placeholders=self._discovery_summary(),
                last_step=True,
            )
        selected = deployment_subentries(self._discovery.deployments, user_input)
        data = {
            **self._settings,
            **self._oauth_data,
            CONF_API_BASE: self._discovery.endpoint,
            CONF_DEPLOYMENTS: self._discovery.deployments,
        }
        entry = self._existing_entry()
        resource_id = self._settings[CONF_RESOURCE_ID].lower()
        if any(
            existing.entry_id != (entry.entry_id if entry else None)
            and existing.data.get(CONF_RESOURCE_ID, "").lower() == resource_id
            for existing in self._async_current_entries()
        ):
            return self.async_abort(reason="already_configured")
        if entry is not None:
            data_changed = {
                key: value for key, value in entry.data.items() if key != "token"
            } != {key: value for key, value in data.items() if key != "token"}
            self.hass.config_entries.async_update_entry(entry, data=data)
            changed = sync_deployment_subentries(self.hass, entry, selected)
            # The update listener reloads only for changes other than the token.
            if not entry.update_listeners or not (changed or data_changed):
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
            return self.async_update_and_abort(entry)
        return self.async_create_entry(
            title=DEFAULT_NAME,
            data=data,
            subentries=selected,
        )

    async def async_step_discovery_all_added(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explain that every compatible deployment already has its services."""
        if user_input is None:
            return self.async_show_form(
                step_id="discovery_all_added",
                data_schema=probatio.Schema({}),
                description_placeholders=self._discovery_summary(),
                last_step=True,
            )
        return await self.async_step_discovery_confirm({})

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        if entry_data.get(CONF_AUTH_TYPE) == AUTH_ENTRA_ID:
            self._settings = {
                key: entry_data[key]
                for key in (CONF_AUTH_TYPE, CONF_RESOURCE_ID, CONF_TENANT_ID)
            }
            return await self.async_step_reauth_oauth_confirm()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_oauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Relink Microsoft when a token, consent, or app credential becomes invalid."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_oauth_confirm", data_schema=probatio.Schema({})
            )
        entry = self._get_reauth_entry()
        return await self.async_step_pick_implementation(
            {"implementation": entry.data["auth_implementation"]}
        )

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        return await self._async_step_api_key(user_input, "reauth_confirm")

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose authentication and refresh the selected resource's deployments."""
        if user_input is not None and CONF_API_KEY in user_input:
            return await self.async_step_api_key(user_input)
        return self.async_show_menu(
            step_id="reconfigure", menu_options=["entra_id", "api_key"]
        )

    @classmethod
    @callback
    @override
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {
            "conversation": AzureOpenAISubentryFlowHandler,
            "ai_task_data": AzureOpenAISubentryFlowHandler,
            "ai_task_image": AzureOpenAISubentryImageFlowHandler,
            "stt": AzureOpenAISubentrySTTFlowHandler,
            "tts": AzureOpenAISubentryTTSFlowHandler,
        }


class AzureOpenAISubentryFlowHandler(ConfigSubentryFlow):
    """Flow for managing Azure OpenAI conversation and AI task subentries."""

    options: dict[str, Any]

    @property
    def _is_new(self) -> bool:
        """Return if this is a new subentry."""
        return self.source == "user"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a subentry."""
        if self._subentry_type == "ai_task_data":
            self.options = RECOMMENDED_AI_TASK_OPTIONS.copy()
        else:
            self.options = RECOMMENDED_CONVERSATION_OPTIONS.copy()
        return await self.async_step_init()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle reconfiguration of a subentry."""
        self.options = self._get_reconfigure_subentry().data.copy()
        return await self.async_step_init()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Manage initial options."""
        # abort if entry is not loaded
        if self._get_entry().state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        options = self.options

        hass_apis: list[SelectOptionDict] = [
            SelectOptionDict(
                label=api.name,
                value=api.id,
            )
            for api in llm.async_get_apis(self.hass)
        ]
        if suggested_llm_apis := options.get(CONF_LLM_HASS_API):
            if isinstance(suggested_llm_apis, str):
                suggested_llm_apis = [suggested_llm_apis]
            valid_apis = {api.id for api in llm.async_get_apis(self.hass)}
            options[CONF_LLM_HASS_API] = [
                api for api in suggested_llm_apis if api in valid_apis
            ]

        step_schema: VolDictType = {}

        if self._is_new:
            if self._subentry_type == "ai_task_data":
                default_name = DEFAULT_AI_TASK_NAME
            else:
                default_name = DEFAULT_CONVERSATION_NAME
            step_schema[probatio.Required(CONF_NAME, default=default_name)] = str

        if self._subentry_type == "conversation":
            step_schema.update(
                {
                    probatio.Optional(
                        CONF_PROMPT,
                        description={
                            "suggested_value": options.get(
                                CONF_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT
                            )
                        },
                    ): TemplateSelector(),
                    probatio.Optional(CONF_LLM_HASS_API): SelectSelector(
                        SelectSelectorConfig(options=hass_apis, multiple=True)
                    ),
                }
            )

        step_schema[
            probatio.Required(
                CONF_RECOMMENDED, default=options.get(CONF_RECOMMENDED, False)
            )
        ] = bool
        chat_model = (user_input or {}).get(
            CONF_CHAT_MODEL,
            options.get(
                CONF_CHAT_MODEL,
                _default_deployment(
                    self._get_entry(), self._subentry_type, RECOMMENDED_CHAT_MODEL
                ),
            ),
        )
        step_schema[probatio.Required(CONF_CHAT_MODEL, default=chat_model)] = (
            SelectSelector(
                SelectSelectorConfig(
                    options=_deployment_choices(
                        self._get_entry().data.get(CONF_DEPLOYMENTS),
                        self._subentry_type,
                        [RECOMMENDED_CHAT_MODEL],
                    ),
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            )
        )
        step_schema.update(
            {
                probatio.Required(
                    CONF_SEND_SAMPLING_PARAMETERS,
                    default=options.get(
                        CONF_SEND_SAMPLING_PARAMETERS,
                        RECOMMENDED_SEND_SAMPLING_PARAMETERS,
                    ),
                ): bool,
                probatio.Optional(
                    CONF_TOP_P,
                    description={
                        "suggested_value": options.get(CONF_TOP_P, RECOMMENDED_TOP_P)
                    },
                ): _SamplingNumberSelector(
                    NumberSelectorConfig(min=0, max=1, step=0.05)
                ),
                probatio.Optional(
                    CONF_TEMPERATURE,
                    description={
                        "suggested_value": options.get(
                            CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE
                        )
                    },
                ): _SamplingNumberSelector(
                    NumberSelectorConfig(min=0, max=2, step=0.05)
                ),
            }
        )
        model_name = _known_model_name(self, CONF_CHAT_MODEL, chat_model) or chat_model
        reasoning_options = get_reasoning_options(model_name)
        recommended_effort = get_recommended_reasoning_effort(model_name)
        reasoning_effort = options.get(CONF_REASONING_EFFORT, recommended_effort)
        if reasoning_options:
            if reasoning_effort not in reasoning_options:
                reasoning_effort = recommended_effort
            step_schema[
                probatio.Optional(
                    CONF_REASONING_EFFORT,
                    description={"suggested_value": reasoning_effort},
                )
            ] = SelectSelector(
                SelectSelectorConfig(
                    options=reasoning_options,
                    translation_key=CONF_REASONING_EFFORT,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )

        if user_input is not None:
            if not _model_supported(
                self, user_input[CONF_CHAT_MODEL], self._subentry_type
            ):
                return self.async_show_form(
                    step_id="init",
                    data_schema=self.add_suggested_values_to_schema(
                        probatio.Schema(step_schema), user_input
                    ),
                    errors={CONF_CHAT_MODEL: "model_not_supported"},
                )
            if reasoning_options:
                selected_effort = user_input.get(
                    CONF_REASONING_EFFORT, reasoning_effort
                )
                if selected_effort not in reasoning_options:
                    return self.async_show_form(
                        step_id="init",
                        data_schema=self.add_suggested_values_to_schema(
                            probatio.Schema(step_schema),
                            {**user_input, CONF_REASONING_EFFORT: reasoning_effort},
                        ),
                        errors={
                            CONF_REASONING_EFFORT: "reasoning_effort_not_supported"
                        },
                    )
                user_input[CONF_REASONING_EFFORT] = selected_effort
            else:
                user_input.pop(CONF_REASONING_EFFORT, None)
            if not user_input[CONF_SEND_SAMPLING_PARAMETERS]:
                user_input.pop(CONF_TOP_P, None)
                user_input.pop(CONF_TEMPERATURE, None)
            if user_input.get(CONF_LLM_HASS_API) is None:
                user_input.pop(CONF_LLM_HASS_API, None)

            if user_input[CONF_RECOMMENDED]:
                return _save_subentry(
                    self,
                    {
                        **{
                            key: options[key]
                            for key in (
                                CONF_AUTO_DISCOVERED,
                                CONF_IMAGE_MODEL,
                                CONF_TOP_P,
                                CONF_TEMPERATURE,
                            )
                            if key in options
                        },
                        **user_input,
                    },
                )

            options.update(user_input)
            if CONF_LLM_HASS_API in options and CONF_LLM_HASS_API not in user_input:
                options.pop(CONF_LLM_HASS_API)
            return await self.async_step_additional()

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(step_schema),
                {**options, CONF_REASONING_EFFORT: reasoning_effort},
            ),
        )

    async def async_step_additional(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Manage additional options."""
        options = self.options
        errors: dict[str, str] = {}

        step_schema: VolDictType = {
            probatio.Optional(
                CONF_MAX_TOKENS,
                default=RECOMMENDED_MAX_TOKENS,
            ): int,
            probatio.Optional(
                CONF_STORE_RESPONSES,
                default=RECOMMENDED_STORE_RESPONSES,
            ): bool,
        }

        if user_input is not None:
            options.update(user_input)
            if not errors:
                return await self.async_step_model()

        return self.async_show_form(
            step_id="additional",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(step_schema), options
            ),
            errors=errors,
        )

    async def async_step_model(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Manage model-specific options."""
        options = self.options
        errors: dict[str, str] = {}

        step_schema: VolDictType = {}

        model = (
            _known_model_name(self, CONF_CHAT_MODEL, options[CONF_CHAT_MODEL])
            or options[CONF_CHAT_MODEL]
        )

        if not model.startswith(tuple(UNSUPPORTED_CODE_INTERPRETER_MODELS)):
            step_schema.update(
                {
                    probatio.Optional(
                        CONF_CODE_INTERPRETER,
                        default=RECOMMENDED_CODE_INTERPRETER,
                    ): bool,
                }
            )
        elif CONF_CODE_INTERPRETER in options:
            options.pop(CONF_CODE_INTERPRETER)

        if not get_reasoning_options(model):
            options.pop(CONF_REASONING_EFFORT, None)

        if model.startswith(("gpt-5.6", "gpt-6")):
            step_schema.update(
                {
                    probatio.Optional(
                        CONF_PRO_MODE,
                        default=RECOMMENDED_PRO_MODE,
                    ): bool,
                }
            )
        elif CONF_PRO_MODE in options:
            options.pop(CONF_PRO_MODE)

        if model.startswith(("gpt-5", "gpt-6")):
            step_schema.update(
                {
                    probatio.Optional(
                        CONF_VERBOSITY,
                        default=RECOMMENDED_VERBOSITY,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=["low", "medium", "high"],
                            translation_key=CONF_VERBOSITY,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            )
        elif CONF_VERBOSITY in options:
            options.pop(CONF_VERBOSITY)

        if model.startswith(("o", "gpt-5", "gpt-6")):
            # Azure doesn't accept a concise summary for GPT-5 or o-series models
            reasoning_summary_options = ["off", "auto", "detailed"]
            stored_summary = options.get(
                CONF_REASONING_SUMMARY, RECOMMENDED_REASONING_SUMMARY
            )
            if stored_summary not in reasoning_summary_options:
                stored_summary = RECOMMENDED_REASONING_SUMMARY
                options[CONF_REASONING_SUMMARY] = stored_summary
            step_schema.update(
                {
                    probatio.Optional(
                        CONF_REASONING_SUMMARY,
                        default=stored_summary,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=reasoning_summary_options,
                            translation_key=CONF_REASONING_SUMMARY,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            )
        elif CONF_REASONING_SUMMARY in options:
            options.pop(CONF_REASONING_SUMMARY)

        if not model.startswith(tuple(UNSUPPORTED_WEB_SEARCH_MODELS)):
            step_schema.update(
                {
                    probatio.Optional(
                        CONF_WEB_SEARCH,
                        default=RECOMMENDED_WEB_SEARCH,
                    ): bool,
                    probatio.Optional(
                        CONF_WEB_SEARCH_CONTEXT_SIZE,
                        default=RECOMMENDED_WEB_SEARCH_CONTEXT_SIZE,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=["low", "medium", "high"],
                            translation_key=CONF_WEB_SEARCH_CONTEXT_SIZE,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    probatio.Optional(
                        CONF_WEB_SEARCH_USER_LOCATION,
                        default=RECOMMENDED_WEB_SEARCH_USER_LOCATION,
                    ): bool,
                    probatio.Optional(
                        CONF_WEB_SEARCH_INLINE_CITATIONS,
                        default=RECOMMENDED_WEB_SEARCH_INLINE_CITATIONS,
                    ): bool,
                }
            )
        elif CONF_WEB_SEARCH in options:
            options = {
                k: v
                for k, v in options.items()
                if k
                not in (
                    CONF_WEB_SEARCH,
                    CONF_WEB_SEARCH_CONTEXT_SIZE,
                    CONF_WEB_SEARCH_USER_LOCATION,
                    CONF_WEB_SEARCH_CITY,
                    CONF_WEB_SEARCH_REGION,
                    CONF_WEB_SEARCH_COUNTRY,
                    CONF_WEB_SEARCH_TIMEZONE,
                    CONF_WEB_SEARCH_INLINE_CITATIONS,
                )
            }

        if self._subentry_type == "ai_task_data":
            image_options = _deployment_choices(
                self._get_entry().data.get(CONF_DEPLOYMENTS),
                "ai_task_image",
                IMAGE_MODELS,
            )
            step_schema[probatio.Optional(CONF_IMAGE_MODEL)] = SelectSelector(
                SelectSelectorConfig(
                    options=image_options,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            )

        if user_input is not None:
            if self._subentry_type == "ai_task_data":
                if image_model := user_input.get(CONF_IMAGE_MODEL):
                    if not _model_supported(self, image_model, "ai_task_image"):
                        errors[CONF_IMAGE_MODEL] = "model_not_supported"
                else:
                    options.pop(CONF_IMAGE_MODEL, None)
            if user_input.get(CONF_WEB_SEARCH):
                if options.get(CONF_REASONING_EFFORT) == "minimal":
                    errors[CONF_WEB_SEARCH] = "web_search_minimal_reasoning"
                if user_input.get(CONF_WEB_SEARCH_USER_LOCATION) and not errors:
                    user_input.update(await self._get_location_data())
                else:
                    options.pop(CONF_WEB_SEARCH_CITY, None)
                    options.pop(CONF_WEB_SEARCH_REGION, None)
                    options.pop(CONF_WEB_SEARCH_COUNTRY, None)
                    options.pop(CONF_WEB_SEARCH_TIMEZONE, None)
            if (
                user_input.get(CONF_CODE_INTERPRETER)
                and options.get(CONF_REASONING_EFFORT) == "minimal"
            ):
                errors[CONF_CODE_INTERPRETER] = "code_interpreter_minimal_reasoning"

            options.update(user_input)
            if not errors:
                return _save_subentry(self, options)

        return self.async_show_form(
            step_id="model",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(step_schema), options
            ),
            errors=errors,
        )

    async def _get_location_data(self) -> dict[str, str]:
        """Get approximate location data of the user."""
        location_data: dict[str, str] = {}
        zone_home = self.hass.states.get(ENTITY_ID_HOME)
        if zone_home is not None:
            client = self._get_entry().runtime_data
            location_schema = probatio.Schema(
                {
                    probatio.Optional(
                        CONF_WEB_SEARCH_CITY,
                        description=(
                            "Free text input for the city, e.g. `San Francisco`"
                        ),
                    ): str,
                    probatio.Optional(
                        CONF_WEB_SEARCH_REGION,
                        description="Free text input for the region, e.g. `California`",
                    ): str,
                }
            )
            try:
                response = await client.responses.create(
                    # Azure needs a deployment, so use the one being configured
                    model=self.options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL),
                    input=[
                        {
                            "role": "system",
                            "content": "Where are the following coordinates located: "
                            f"({zone_home.attributes[EntityStateAttribute.LATITUDE]},"
                            f" {zone_home.attributes[EntityStateAttribute.LONGITUDE]})?",
                        }
                    ],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "approximate_location",
                            "description": "Approximate location data of the user "
                            "for refined web search results",
                            "schema": to_openapi(
                                location_schema, openapi_version="3.1.0"
                            ),
                            "strict": False,
                        }
                    },
                    store=self.options.get(
                        CONF_STORE_RESPONSES, RECOMMENDED_STORE_RESPONSES
                    ),
                )
                location_data = location_schema(json.loads(response.output_text) or {})
            except (openai.OpenAIError, ValueError, probatio.Invalid) as err:
                _LOGGER.warning("Unable to look up the home city and region: %s", err)

        if self.hass.config.country:
            location_data[CONF_WEB_SEARCH_COUNTRY] = self.hass.config.country
        location_data[CONF_WEB_SEARCH_TIMEZONE] = self.hass.config.time_zone

        _LOGGER.debug("Location data: %s", location_data)

        return location_data


class AzureOpenAISubentryImageFlowHandler(ConfigSubentryFlow):
    """Flow for dedicated image-generation AI tasks."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add an image task."""
        return await self.async_step_init(user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Reconfigure an image task."""
        return await self.async_step_init(user_input)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Select an actual image deployment independently of chat models."""
        entry = self._get_entry()
        if entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")
        options = (
            {} if self.source == "user" else dict(self._get_reconfigure_subentry().data)
        )
        schema: VolDictType = {}
        if self.source == "user":
            schema[probatio.Required(CONF_NAME, default=DEFAULT_IMAGE_TASK_NAME)] = str
        schema[
            probatio.Required(
                CONF_IMAGE_MODEL,
                default=options.get(
                    CONF_IMAGE_MODEL,
                    _default_deployment(
                        entry, "ai_task_image", RECOMMENDED_IMAGE_MODEL
                    ),
                ),
            )
        ] = SelectSelector(
            SelectSelectorConfig(
                options=_deployment_choices(
                    entry.data.get(CONF_DEPLOYMENTS), "ai_task_image", IMAGE_MODELS
                ),
                mode=SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            if _model_supported(self, user_input[CONF_IMAGE_MODEL], "ai_task_image"):
                return _save_subentry(self, {**options, **user_input})
            errors[CONF_IMAGE_MODEL] = "model_not_supported"
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(schema), options
            ),
            errors=errors,
        )


class AzureOpenAISubentrySTTFlowHandler(ConfigSubentryFlow):
    """Flow for managing Azure OpenAI STT subentries."""

    options: dict[str, Any]

    @property
    def _is_new(self) -> bool:
        """Return if this is a new subentry."""
        return self.source == "user"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a subentry."""
        self.options = RECOMMENDED_STT_OPTIONS.copy()
        self.options[CONF_CHAT_MODEL] = _default_deployment(
            self._get_entry(), "stt", RECOMMENDED_STT_MODEL
        )
        return await self.async_step_init()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle reconfiguration of a subentry."""
        self.options = self._get_reconfigure_subentry().data.copy()
        return await self.async_step_init()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Manage initial options."""
        # abort if entry is not loaded
        if self._get_entry().state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        options = self.options

        step_schema: VolDictType = {}

        if self._is_new:
            step_schema[probatio.Required(CONF_NAME, default=DEFAULT_STT_NAME)] = str

        step_schema.update(
            {
                probatio.Optional(
                    CONF_PROMPT,
                    description={
                        "suggested_value": options.get(CONF_PROMPT, DEFAULT_STT_PROMPT)
                    },
                ): TextSelector(
                    TextSelectorConfig(multiline=True, type=TextSelectorType.TEXT)
                ),
                probatio.Optional(
                    CONF_CHAT_MODEL,
                    default=options.get(
                        CONF_CHAT_MODEL,
                        _default_deployment(
                            self._get_entry(), "stt", RECOMMENDED_STT_MODEL
                        ),
                    ),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=_deployment_choices(
                            self._get_entry().data.get(CONF_DEPLOYMENTS),
                            "stt",
                            STT_MODELS,
                        ),
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
            }
        )

        errors: dict[str, str] = {}
        if user_input is not None:
            options.update(user_input)
            if _model_supported(self, options[CONF_CHAT_MODEL], "stt"):
                return _save_subentry(self, options)
            errors[CONF_CHAT_MODEL] = "model_not_supported"

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(step_schema), options
            ),
            errors=errors,
        )


class AzureOpenAISubentryTTSFlowHandler(ConfigSubentryFlow):
    """Flow for managing Azure OpenAI TTS subentries."""

    options: dict[str, Any]

    @property
    def _is_new(self) -> bool:
        """Return if this is a new subentry."""
        return self.source == "user"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a subentry."""
        self.options = RECOMMENDED_TTS_OPTIONS.copy()
        self.options[CONF_CHAT_MODEL] = _default_deployment(
            self._get_entry(), "tts", RECOMMENDED_TTS_MODEL
        )
        return await self.async_step_init()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle reconfiguration of a subentry."""
        self.options = self._get_reconfigure_subentry().data.copy()
        return await self.async_step_init()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Manage initial options."""
        # abort if entry is not loaded
        if self._get_entry().state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        options = self.options

        step_schema: VolDictType = {}

        if self._is_new:
            step_schema[probatio.Required(CONF_NAME, default=DEFAULT_TTS_NAME)] = str

        step_schema.update(
            {
                probatio.Optional(
                    CONF_CHAT_MODEL,
                    default=options.get(
                        CONF_CHAT_MODEL,
                        _default_deployment(
                            self._get_entry(), "tts", RECOMMENDED_TTS_MODEL
                        ),
                    ),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=_deployment_choices(
                            self._get_entry().data.get(CONF_DEPLOYMENTS),
                            "tts",
                            TTS_MODELS,
                        ),
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
                probatio.Optional(CONF_PROMPT): TextSelector(
                    TextSelectorConfig(multiline=True, type=TextSelectorType.TEXT)
                ),
                probatio.Optional(
                    CONF_TTS_SPEED, default=RECOMMENDED_TTS_SPEED
                ): NumberSelector(NumberSelectorConfig(min=0.25, max=4.0, step=0.01)),
            }
        )

        errors: dict[str, str] = {}
        if user_input is not None:
            options.update(user_input)
            if _model_supported(self, options[CONF_CHAT_MODEL], "tts"):
                return _save_subentry(self, options)
            errors[CONF_CHAT_MODEL] = "model_not_supported"

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(step_schema), options
            ),
            errors=errors,
        )
