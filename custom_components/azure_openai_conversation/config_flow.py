"""Config flow for Azure OpenAI Conversation integration."""

from __future__ import annotations

import logging
from types import MappingProxyType
from typing import Any

# from functools import partial
# import types

import openai
import voluptuous as vol
# from openai import error

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

# from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TemplateSelector,
)
from homeassistant.helpers.typing import VolDictType

from .const import (
    CONF_API_BASE,
    CONF_API_VERSION,
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_PROMPT,
    CONF_RECOMMENDED,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    DOMAIN,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_TEMPERATURE,
    RECOMMENDED_TOP_P,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_API_BASE): str,
        vol.Required(CONF_API_VERSION): str,
    }
)

RECOMMENDED_OPTIONS = {
    CONF_RECOMMENDED: True,
    CONF_LLM_HASS_API: llm.LLM_API_ASSIST,
    CONF_PROMPT: llm.DEFAULT_INSTRUCTIONS_PROMPT,
}


"""DEFAULT_OPTIONS = types.MappingProxyType(
    {
        CONF_PROMPT: DEFAULT_PROMPT,
        CONF_CHAT_MODEL: DEFAULT_CHAT_MODEL,
        CONF_MAX_TOKENS: DEFAULT_MAX_TOKENS,
        CONF_TOP_P: DEFAULT_TOP_P,
        CONF_TEMPERATURE: DEFAULT_TEMPERATURE,
    }
)"""


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    client = openai.AsyncAzureOpenAI(
        api_key=data[CONF_API_KEY],
        base_url=data[CONF_API_BASE],
        api_version=data[CONF_API_VERSION],
    )
    await hass.async_add_executor_job(client.with_options(timeout=10.0).models.list)
    """openai.api_type = "azure"
    openai.api_key = data[CONF_API_KEY]
    openai.api_base = data[CONF_API_BASE]
    openai.api_version = data[CONF_API_VERSION]

    await hass.async_add_executor_job(partial(openai.Model.list, request_timeout=10))"""


class AzureOpenAIConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Azure OpenAI Conversation."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors: dict[str, str] = {}

        try:
            await validate_input(self.hass, user_input)
        except openai.APIConnectionError:
            errors["base"] = "cannot_connect"
        except openai.AuthenticationError:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(
                title="Azure OpenAI Conversation",
                data=user_input,
                options=RECOMMENDED_OPTIONS,
            )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Create the options flow."""
        return AzureOpenAIOptionsFlow(config_entry)


class AzureOpenAIOptionsFlow(OptionsFlow):
    """Azure OpenAI config flow options handler."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.last_rendered_recommended = config_entry.options.get(
            CONF_RECOMMENDED, False
        )
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        options: dict[str, Any] | MappingProxyType[str, Any] = self.config_entry.options

        if user_input is not None:
            if user_input[CONF_RECOMMENDED] == self.last_rendered_recommended:
                if user_input[CONF_LLM_HASS_API] == "none":
                    user_input.pop(CONF_LLM_HASS_API)
                return self.async_create_entry(title="", data=user_input)

            # Re-render the options again, now with the recommended options shown/hidden
            self.last_rendered_recommended = user_input[CONF_RECOMMENDED]

            options = {
                CONF_RECOMMENDED: user_input[CONF_RECOMMENDED],
                CONF_PROMPT: user_input[CONF_PROMPT],
                CONF_LLM_HASS_API: user_input[CONF_LLM_HASS_API],
            }
            return self.async_create_entry(
                title="Azure OpenAI Conversation", data=user_input
            )
        schema = azure_openai_config_option_schema(self.hass, options)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
        )


def azure_openai_config_option_schema(
    hass: HomeAssistant, options: MappingProxyType[str, Any]
) -> VolDictType:
    """Return a schema for Azure OpenAI completion options."""
    hass_apis: list[SelectOptionDict] = [
        SelectOptionDict(
            label="No control",
            value="none",
        )
    ]
    hass_apis.extend(
        SelectOptionDict(
            label=api.name,
            value=api.id,
        )
        for api in llm.async_get_apis(hass)
    )
    schema: VolDictType = {
        vol.Optional(
            CONF_PROMPT,
            description={
                "suggested_value": options.get(
                    CONF_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT
                )
            },
        ): TemplateSelector(),
        vol.Optional(
            CONF_LLM_HASS_API,
            description={"suggested_value": options.get(CONF_LLM_HASS_API)},
            default="none",
        ): SelectSelector(SelectSelectorConfig(options=hass_apis)),
        vol.Required(
            CONF_RECOMMENDED, default=options.get(CONF_RECOMMENDED, False)
        ): bool,
    }

    if options.get(CONF_RECOMMENDED):
        return schema

    schema.update(
        {
            vol.Optional(
                CONF_CHAT_MODEL,
                description={"suggested_value": options.get(CONF_CHAT_MODEL)},
                default=RECOMMENDED_CHAT_MODEL,
            ): str,
            vol.Optional(
                CONF_MAX_TOKENS,
                description={"suggested_value": options.get(CONF_MAX_TOKENS)},
                default=RECOMMENDED_MAX_TOKENS,
            ): int,
            vol.Optional(
                CONF_TOP_P,
                description={"suggested_value": options.get(CONF_TOP_P)},
                default=RECOMMENDED_TOP_P,
            ): NumberSelector(NumberSelectorConfig(min=0, max=1, step=0.05)),
            vol.Optional(
                CONF_TEMPERATURE,
                description={"suggested_value": options.get(CONF_TEMPERATURE)},
                default=RECOMMENDED_TEMPERATURE,
            ): NumberSelector(NumberSelectorConfig(min=0, max=2, step=0.05)),
        }
    )
    return schema
