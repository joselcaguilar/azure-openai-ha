"""Config flow for Azure OpenAI Conversation integration."""

from __future__ import annotations

from collections.abc import Mapping
import json
import logging
from typing import Any, override

import openai
import probatio
from probatio import to_openapi

from homeassistant.components.zone import ENTITY_ID_HOME
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
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
from homeassistant.helpers import llm
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
from .const import (
    CONF_API_BASE,
    CONF_CHAT_MODEL,
    CONF_CODE_INTERPRETER,
    CONF_IMAGE_MODEL,
    CONF_MAX_TOKENS,
    CONF_PRO_MODE,
    CONF_REASONING_EFFORT,
    CONF_REASONING_SUMMARY,
    CONF_RECOMMENDED,
    CONF_STORE_RESPONSES,
    CONF_TEMPERATURE,
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
    RECOMMENDED_REASONING_EFFORT,
    RECOMMENDED_REASONING_SUMMARY,
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


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    client = create_client(hass, data[CONF_API_BASE], data[CONF_API_KEY])
    await client.models.list(timeout=10.0)


class AzureOpenAIConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Azure OpenAI Conversation."""

    VERSION = 2
    MINOR_VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        return await self._async_step_api_key(user_input, "user")

    async def _async_step_api_key(
        self, user_input: dict[str, Any] | None, step_id: str
    ) -> ConfigFlowResult:
        """Handle an API key form."""
        errors: dict[str, str] = {}
        entry: ConfigEntry | None = None
        if self.source == SOURCE_REAUTH:
            entry = self._get_reauth_entry()
        elif self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()

        if user_input is not None:
            if entry is None:
                self._async_abort_entries_match(user_input)
            try:
                await validate_input(
                    self.hass, {**(entry.data if entry else {}), **user_input}
                )
            except (openai.APIConnectionError, openai.NotFoundError):
                errors["base"] = "cannot_connect"
            except openai.AuthenticationError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                if entry is not None:
                    if entry.update_listeners:
                        return self.async_update_and_abort(
                            entry, data_updates=user_input
                        )
                    return self.async_update_reload_and_abort(
                        entry, data_updates=user_input
                    )
                return self.async_create_entry(
                    title=DEFAULT_NAME,
                    data=user_input,
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

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        return await self._async_step_api_key(user_input, "reauth_confirm")

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the endpoint and API key."""
        return await self._async_step_api_key(user_input, "reconfigure")

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

        if user_input is not None:
            if user_input.get(CONF_LLM_HASS_API) is None:
                user_input.pop(CONF_LLM_HASS_API, None)

            if user_input[CONF_RECOMMENDED]:
                if self._is_new:
                    return self.async_create_entry(
                        title=user_input.pop(CONF_NAME),
                        data=user_input,
                    )
                return self.async_update_and_abort(
                    self._get_entry(),
                    self._get_reconfigure_subentry(),
                    data=user_input,
                )

            options.update(user_input)
            if CONF_LLM_HASS_API in options and CONF_LLM_HASS_API not in user_input:
                options.pop(CONF_LLM_HASS_API)
            return await self.async_step_additional()

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(step_schema), options
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
                CONF_CHAT_MODEL,
                default=RECOMMENDED_CHAT_MODEL,
            ): str,
            probatio.Optional(
                CONF_MAX_TOKENS,
                default=RECOMMENDED_MAX_TOKENS,
            ): int,
            probatio.Optional(
                CONF_TOP_P,
                default=RECOMMENDED_TOP_P,
            ): NumberSelector(NumberSelectorConfig(min=0, max=1, step=0.05)),
            probatio.Optional(
                CONF_TEMPERATURE,
                default=RECOMMENDED_TEMPERATURE,
            ): NumberSelector(NumberSelectorConfig(min=0, max=2, step=0.05)),
            probatio.Optional(
                CONF_STORE_RESPONSES,
                default=RECOMMENDED_STORE_RESPONSES,
            ): bool,
        }

        if user_input is not None:
            options.update(user_input)
            if user_input.get(CONF_CHAT_MODEL) in UNSUPPORTED_MODELS:
                errors[CONF_CHAT_MODEL] = "model_not_supported"

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

        model = options[CONF_CHAT_MODEL]

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

        if reasoning_options := self._get_reasoning_options(model):
            step_schema.update(
                {
                    probatio.Optional(
                        CONF_REASONING_EFFORT,
                        default=RECOMMENDED_REASONING_EFFORT,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=reasoning_options,
                            translation_key=CONF_REASONING_EFFORT,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            )
        elif CONF_REASONING_EFFORT in options:
            options.pop(CONF_REASONING_EFFORT)

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
            step_schema[
                probatio.Optional(CONF_IMAGE_MODEL, default=RECOMMENDED_IMAGE_MODEL)
            ] = SelectSelector(
                SelectSelectorConfig(
                    options=IMAGE_MODELS,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            )

        if user_input is not None:
            if user_input.get(CONF_WEB_SEARCH):
                if user_input.get(CONF_REASONING_EFFORT) == "minimal":
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
                and user_input.get(CONF_REASONING_EFFORT) == "minimal"
            ):
                errors[CONF_CODE_INTERPRETER] = "code_interpreter_minimal_reasoning"

            options.update(user_input)
            if not errors:
                if self._is_new:
                    return self.async_create_entry(
                        title=options.pop(CONF_NAME),
                        data=options,
                    )
                return self.async_update_and_abort(
                    self._get_entry(),
                    self._get_reconfigure_subentry(),
                    data=options,
                )

        return self.async_show_form(
            step_id="model",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(step_schema), options
            ),
            errors=errors,
        )

    def _get_reasoning_options(self, model: str) -> list[str]:
        """Get reasoning effort options based on model."""
        if not model.startswith(("o", "gpt-5", "gpt-6")) or model.startswith(
            "gpt-5-pro"
        ):
            return []

        models_reasoning_map: dict[str | tuple[str, ...], list[str]] = {
            "gpt-6-luna": ["none", "low", "medium", "high", "xhigh", "max"],
            "gpt-6": ["low", "medium", "high", "xhigh", "max"],
            "gpt-5.6": ["none", "low", "medium", "high", "xhigh", "max"],
            ("gpt-5.2-pro", "gpt-5.4-pro", "gpt-5.5-pro"): ["medium", "high", "xhigh"],
            ("gpt-5.2", "gpt-5.3", "gpt-5.4", "gpt-5.5"): [
                "none",
                "low",
                "medium",
                "high",
                "xhigh",
            ],
            "gpt-5.1": ["none", "low", "medium", "high"],
            "gpt-5": ["minimal", "low", "medium", "high"],
            "": ["low", "medium", "high"],  # The default case
        }

        for prefix, options in models_reasoning_map.items():
            if model.startswith(prefix):
                return options
        return []  # pragma: no cover

    async def _get_location_data(self) -> dict[str, str]:
        """Get approximate location data of the user."""
        location_data: dict[str, str] = {}
        zone_home = self.hass.states.get(ENTITY_ID_HOME)
        if zone_home is not None:
            entry_data = self._get_entry().data
            client = create_client(
                self.hass, entry_data[CONF_API_BASE], entry_data[CONF_API_KEY]
            )
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
                    CONF_CHAT_MODEL, default=RECOMMENDED_STT_MODEL
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=STT_MODELS,
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
            }
        )

        if user_input is not None:
            options.update(user_input)
            if self._is_new:
                return self.async_create_entry(
                    title=options.pop(CONF_NAME),
                    data=options,
                )
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                data=options,
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(step_schema), options
            ),
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
                    CONF_CHAT_MODEL, default=RECOMMENDED_TTS_MODEL
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=TTS_MODELS,
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

        if user_input is not None:
            options.update(user_input)
            if self._is_new:
                return self.async_create_entry(
                    title=options.pop(CONF_NAME),
                    data=options,
                )
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                data=options,
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(step_schema), options
            ),
        )
