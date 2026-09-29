"""Conversation support for OpenAI."""

from collections.abc import AsyncGenerator, Callable
from datetime import date, datetime, time
import json
from typing import Any, Literal, cast

import openai
from openai._streaming import AsyncStream
from openai.types.responses import (
    EasyInputMessageParam,
    FunctionToolParam,
    ResponseCompletedEvent,
    ResponseErrorEvent,
    ResponseFailedEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionCallArgumentsDoneEvent,
    ResponseFunctionToolCall,
    ResponseFunctionToolCallParam,
    ResponseIncompleteEvent,
    ResponseInputParam,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseOutputMessageParam,
    ResponseReasoningItem,
    ResponseReasoningItemParam,
    ResponseStreamEvent,
    ResponseTextDeltaEvent,
    ToolParam,
    WebSearchToolParam,
)
from openai.types.responses.response_input_param import FunctionCallOutput
from openai.types.responses.web_search_tool_param import UserLocation
from voluptuous_openapi import convert

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LLM_HASS_API, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, intent, llm
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OpenAIConfigEntry, async_responses_create_with_param_fallback
from .const import (
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_PROMPT,
    CONF_REASONING_EFFORT,
    CONF_SEND_SAMPLING_PARAMETERS,
    CONF_STRIP_WEB_CITATIONS,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    CONF_WEB_SEARCH,
    CONF_WEB_SEARCH_CITY,
    CONF_WEB_SEARCH_CONTEXT_SIZE,
    CONF_WEB_SEARCH_COUNTRY,
    CONF_WEB_SEARCH_REGION,
    CONF_WEB_SEARCH_TIMEZONE,
    CONF_WEB_SEARCH_USER_LOCATION,
    DOMAIN,
    LOGGER,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_REASONING_EFFORT,
    RECOMMENDED_SEND_SAMPLING_PARAMETERS,
    RECOMMENDED_STRIP_WEB_CITATIONS,
    RECOMMENDED_TEMPERATURE,
    RECOMMENDED_TOP_P,
    RECOMMENDED_WEB_SEARCH_CONTEXT_SIZE,
    REASONING_EFFORT_DISABLED,
)

# Max number of back and forth with the LLM to generate a response
MAX_TOOL_ITERATIONS = 10


def _extract_answer_from_json_text(text: str) -> str | None:
    """Return the answer field when text is a structured JSON payload."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    answer = parsed.get("answer")
    if isinstance(answer, str):
        return answer.strip()

    return None


def _extract_output_text(
    item: dict[str, Any], *, strip_url_citations: bool
) -> str | None:
    """Extract output text and optionally strip url_citation annotation ranges."""
    content = item.get("content")
    if not isinstance(content, list):
        return None

    output_parts: list[str] = []
    for content_item in content:
        if not isinstance(content_item, dict):
            continue
        if content_item.get("type") != "output_text":
            continue

        text = content_item.get("text")
        if not isinstance(text, str):
            continue

        ranges: list[tuple[int, int]] = []
        annotations = content_item.get("annotations")
        if isinstance(annotations, list):
            for annotation in annotations:
                if not isinstance(annotation, dict):
                    continue
                if annotation.get("type") != "url_citation":
                    continue

                start = annotation.get("start_index")
                end = annotation.get("end_index")
                if (
                    isinstance(start, int)
                    and isinstance(end, int)
                    and 0 <= start < end <= len(text)
                ):
                    ranges.append((start, end))

        if strip_url_citations and ranges:
            ranges.sort()
            merged_ranges: list[tuple[int, int]] = [ranges[0]]
            for start, end in ranges[1:]:
                prev_start, prev_end = merged_ranges[-1]
                if start <= prev_end:
                    merged_ranges[-1] = (prev_start, max(prev_end, end))
                else:
                    merged_ranges.append((start, end))

            cleaned_parts: list[str] = []
            index = 0
            for start, end in merged_ranges:
                cleaned_parts.append(text[index:start])
                index = end
            cleaned_parts.append(text[index:])
            text = "".join(cleaned_parts)

        text = _extract_answer_from_json_text(text) or text
        output_parts.append(text)

    if not output_parts:
        return None

    return "".join(output_parts).strip()


def _json_default(value: Any) -> str:
    """Serialize values that appear in Home Assistant tool responses."""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OpenAIConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up conversation entities."""
    agent = AzureOpenAIConversationEntity(config_entry)
    async_add_entities([agent])


def _format_tool(
    tool: llm.Tool, custom_serializer: Callable[[Any], Any] | None
) -> FunctionToolParam:
    """Format tool specification."""

    def _convert_tool_schema() -> Any:
        """Convert tool schema, retrying without custom serializer.

        Some HA tool schemas convert to unsupported placeholders when a
        serializer is supplied, but convert correctly without one.
        """
        converted = convert(tool.parameters, custom_serializer=custom_serializer)
        if isinstance(converted, dict):
            return converted

        if custom_serializer is None:
            return converted

        fallback_converted = convert(tool.parameters)
        if isinstance(fallback_converted, dict):
            return fallback_converted

        return converted

    def _to_azure_tool_schema(schema: Any) -> dict[str, Any]:
        """Normalize schema to Azure/OpenAI function-tool requirements.

        Azure rejects top-level oneOf/anyOf/allOf/enum/not and requires
        an object at the top level.
        """
        if not isinstance(schema, dict):
            return {"type": "object", "properties": {}}

        normalized = dict(schema)

        # HA tool schemas can be emitted as anyOf(object, null) for optional
        # argument groups. Azure requires a top-level object.
        for combiner in ("anyOf", "oneOf", "allOf"):
            variants = normalized.get(combiner)
            if isinstance(variants, list):
                object_variant = next(
                    (
                        variant
                        for variant in variants
                        if isinstance(variant, dict)
                        and (
                            variant.get("type") == "object"
                            or "properties" in variant
                        )
                    ),
                    None,
                )
                if object_variant is not None:
                    normalized = {**normalized, **object_variant}
                normalized.pop(combiner, None)

        normalized.pop("enum", None)
        normalized.pop("not", None)

        if normalized.get("type") != "object":
            normalized["type"] = "object"

        normalized.setdefault("properties", {})
        return normalized

    return FunctionToolParam(
        type="function",
        name=tool.name,
        parameters=_to_azure_tool_schema(_convert_tool_schema()),
        description=tool.description,
        strict=False,
    )


def _convert_content_to_param(
    content: conversation.Content,
) -> ResponseInputParam:
    """Convert any native chat message for this agent to the native format."""
    messages: ResponseInputParam = []
    if isinstance(content, conversation.ToolResultContent):
        return [
            FunctionCallOutput(
                type="function_call_output",
                call_id=content.tool_call_id,
                output=json.dumps(content.tool_result, default=_json_default),
            )
        ]

    if content.content:
        role: Literal["user", "assistant", "system", "developer"] = content.role
        if role == "system":
            role = "developer"
        messages.append(
            EasyInputMessageParam(type="message", role=role, content=content.content)
        )

    if isinstance(content, conversation.AssistantContent) and content.tool_calls:
        messages.extend(
            ResponseFunctionToolCallParam(
                type="function_call",
                name=tool_call.tool_name,
                arguments=json.dumps(tool_call.tool_args),
                call_id=tool_call.id,
            )
            for tool_call in content.tool_calls
        )
    return messages


async def _transform_stream(
    chat_log: conversation.ChatLog,
    result: AsyncStream[ResponseStreamEvent],
    messages: ResponseInputParam,
    strip_url_citations: bool = False,
    on_clean_output_text: Callable[[str], None] | None = None,
) -> AsyncGenerator[conversation.AssistantContentDeltaDict]:
    """Transform an OpenAI delta stream into HA format."""
    async for event in result:
        LOGGER.debug("Received event: %s", event)

        if isinstance(event, ResponseOutputItemAddedEvent):
            if isinstance(event.item, ResponseOutputMessage):
                yield {"role": event.item.role}
            elif isinstance(event.item, ResponseFunctionToolCall):
                # OpenAI has tool calls as individual events
                # while HA puts tool calls inside the assistant message.
                # We turn them into individual assistant content for HA
                # to ensure that tools are called as soon as possible.
                yield {"role": "assistant"}
                current_tool_call = event.item
        elif isinstance(event, ResponseOutputItemDoneEvent):
            item = event.item.model_dump()
            item.pop("status", None)
            if isinstance(event.item, ResponseReasoningItem):
                messages.append(cast(ResponseReasoningItemParam, item))
            elif isinstance(event.item, ResponseOutputMessage):
                if on_clean_output_text is not None:
                    if clean_output_text := _extract_output_text(
                        item,
                        strip_url_citations=strip_url_citations,
                    ):
                        on_clean_output_text(clean_output_text)
                messages.append(cast(ResponseOutputMessageParam, item))
            elif isinstance(event.item, ResponseFunctionToolCall):
                messages.append(cast(ResponseFunctionToolCallParam, item))
        elif isinstance(event, ResponseTextDeltaEvent):
            yield {"content": event.delta}
        elif isinstance(event, ResponseFunctionCallArgumentsDeltaEvent):
            current_tool_call.arguments += event.delta
        elif isinstance(event, ResponseFunctionCallArgumentsDoneEvent):
            current_tool_call.status = "completed"
            yield {
                "tool_calls": [
                    llm.ToolInput(
                        id=current_tool_call.call_id,
                        tool_name=current_tool_call.name,
                        tool_args=json.loads(current_tool_call.arguments),
                    )
                ]
            }
        elif isinstance(event, ResponseCompletedEvent):
            if event.response.usage is not None:
                chat_log.async_trace(
                    {
                        "stats": {
                            "input_tokens": event.response.usage.input_tokens,
                            "output_tokens": event.response.usage.output_tokens,
                        }
                    }
                )
        elif isinstance(event, ResponseIncompleteEvent):
            if event.response.usage is not None:
                chat_log.async_trace(
                    {
                        "stats": {
                            "input_tokens": event.response.usage.input_tokens,
                            "output_tokens": event.response.usage.output_tokens,
                        }
                    }
                )

            if (
                event.response.incomplete_details
                and event.response.incomplete_details.reason
            ):
                reason: str = event.response.incomplete_details.reason
            else:
                reason = "unknown reason"

            if reason == "max_output_tokens":
                reason = "max output tokens reached"
            elif reason == "content_filter":
                reason = "content filter triggered"

            raise HomeAssistantError(f"Azure OpenAI response incomplete: {reason}")
        elif isinstance(event, ResponseFailedEvent):
            if event.response.usage is not None:
                chat_log.async_trace(
                    {
                        "stats": {
                            "input_tokens": event.response.usage.input_tokens,
                            "output_tokens": event.response.usage.output_tokens,
                        }
                    }
                )
            reason = "unknown reason"
            if event.response.error is not None:
                reason = event.response.error.message
            raise HomeAssistantError(f"Azure OpenAI response failed: {reason}")
        elif isinstance(event, ResponseErrorEvent):
            raise HomeAssistantError(f"Azure OpenAI response error: {event.message}")


class AzureOpenAIConversationEntity(
    conversation.ConversationEntity, conversation.AbstractConversationAgent
):
    """Azure OpenAI conversation agent."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supports_streaming = True

    def __init__(self, entry: OpenAIConfigEntry) -> None:
        """Initialize the agent."""
        self.entry = entry
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Azure OpenAI",
            model="Azure ChatGPT",
            entry_type=dr.DeviceEntryType.SERVICE,
        )
        if self.entry.options.get(CONF_LLM_HASS_API):
            self._attr_supported_features = (
                conversation.ConversationEntityFeature.CONTROL
            )

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return a list of supported languages."""
        return MATCH_ALL

    async def async_added_to_hass(self) -> None:
        """When entity is added to Home Assistant."""
        await super().async_added_to_hass()

        conversation.async_set_agent(self.hass, self.entry, self)
        self.entry.async_on_unload(
            self.entry.add_update_listener(self._async_entry_update_listener)
        )

    async def async_will_remove_from_hass(self) -> None:
        """When entity will be removed from Home Assistant."""
        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        """Process the user input and call the API."""
        options = self.entry.options

        try:
            await chat_log.async_update_llm_data(
                DOMAIN,
                user_input,
                options.get(CONF_LLM_HASS_API),
                options.get(CONF_PROMPT),
            )
        except conversation.ConverseError as err:
            return err.as_conversation_result()

        clean_output_text = await self._async_handle_chat_log(chat_log)

        intent_response = intent.IntentResponse(language=user_input.language)
        assert type(chat_log.content[-1]) is conversation.AssistantContent
        speech = clean_output_text or chat_log.content[-1].content or ""

        intent_response.async_set_speech(speech)
        return conversation.ConversationResult(
            response=intent_response,
            conversation_id=chat_log.conversation_id,
            continue_conversation=chat_log.continue_conversation,
        )

    async def _async_handle_chat_log(
        self,
        chat_log: conversation.ChatLog,
    ) -> str | None:
        """Generate an answer for the chat log."""
        options = self.entry.options
        clean_output_text: str | None = None
        strip_web_citations = options.get(
            CONF_STRIP_WEB_CITATIONS,
            RECOMMENDED_STRIP_WEB_CITATIONS,
        )

        def _set_clean_output_text(text: str) -> None:
            nonlocal clean_output_text
            clean_output_text = text

        tools: list[ToolParam] | None = None
        if chat_log.llm_api:
            tools = [
                _format_tool(tool, chat_log.llm_api.custom_serializer)
                for tool in chat_log.llm_api.tools
            ]

        if options.get(CONF_WEB_SEARCH):
            web_search = WebSearchToolParam(
                type="web_search",
                search_context_size=options.get(
                    CONF_WEB_SEARCH_CONTEXT_SIZE, RECOMMENDED_WEB_SEARCH_CONTEXT_SIZE
                ),
            )
            if options.get(CONF_WEB_SEARCH_USER_LOCATION):
                web_search["user_location"] = UserLocation(
                    type="approximate",
                    city=options.get(CONF_WEB_SEARCH_CITY, ""),
                    region=options.get(CONF_WEB_SEARCH_REGION, ""),
                    country=options.get(CONF_WEB_SEARCH_COUNTRY, ""),
                    timezone=options.get(CONF_WEB_SEARCH_TIMEZONE, ""),
                )
            if tools is None:
                tools = []
            tools.append(web_search)

        model = options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL)
        messages = [
            m
            for content in chat_log.content
            for m in _convert_content_to_param(content)
        ]

        client = self.entry.runtime_data
        reasoning_effort = options.get(
            CONF_REASONING_EFFORT, RECOMMENDED_REASONING_EFFORT
        )
        if reasoning_effort in ("", REASONING_EFFORT_DISABLED):
            reasoning_effort = None
        send_sampling_parameters = options.get(
            CONF_SEND_SAMPLING_PARAMETERS,
            RECOMMENDED_SEND_SAMPLING_PARAMETERS,
        )

        # To prevent infinite loops, we limit the number of iterations
        for _iteration in range(MAX_TOOL_ITERATIONS):
            model_args = {
                "model": model,
                "input": messages,
                "max_output_tokens": options.get(
                    CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS
                ),
                "user": chat_log.conversation_id,
                "stream": True,
            }

            if send_sampling_parameters:
                model_args["top_p"] = options.get(CONF_TOP_P, RECOMMENDED_TOP_P)
                model_args["temperature"] = options.get(
                    CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE
                )
            if tools:
                model_args["tools"] = tools

            if reasoning_effort:
                model_args["reasoning"] = {"effort": reasoning_effort}

            if options.get(CONF_WEB_SEARCH):
                model_args["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": "assistant_web_answer",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "answer": {"type": "string"},
                            },
                            "required": ["answer"],
                            "additionalProperties": False,
                        },
                        "strict": True,
                    }
                }

            if not model.startswith("o"):
                model_args["store"] = False

            try:
                result = await async_responses_create_with_param_fallback(
                    client,
                    model_args,
                    entry_id=self.entry.entry_id,
                    model=model,
                )
            except openai.RateLimitError as err:
                LOGGER.error("Rate limited by Azure OpenAI: %s", err)
                raise HomeAssistantError("Rate limited or insufficient funds") from err
            except openai.OpenAIError as err:
                LOGGER.error("Error talking to Azure OpenAI: %s", err)
                raise HomeAssistantError("Error talking to Azure OpenAI") from err

            async for content in chat_log.async_add_delta_content_stream(
                self.entity_id,
                _transform_stream(
                    chat_log,
                    result,
                    messages,
                    strip_url_citations=strip_web_citations,
                    on_clean_output_text=_set_clean_output_text,
                ),
            ):
                if not isinstance(content, conversation.AssistantContent):
                    messages.extend(_convert_content_to_param(content))

            if not chat_log.unresponded_tool_results:
                break

        return clean_output_text

    async def _async_entry_update_listener(
        self, hass: HomeAssistant, entry: ConfigEntry
    ) -> None:
        """Handle options update."""
        # Reload as we update device info + entity name + supported features
        await hass.config_entries.async_reload(entry.entry_id)
