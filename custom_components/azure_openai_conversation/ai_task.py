"""AI Task integration for Azure OpenAI."""

from __future__ import annotations

import base64
from json import JSONDecodeError
import logging
import re
from typing import TYPE_CHECKING, override

import openai

from homeassistant.components import ai_task, conversation
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.json import json_loads

from .const import CONF_IMAGE_MODEL, RECOMMENDED_IMAGE_MODEL
from .entity import AzureOpenAIBaseLLMEntity

if TYPE_CHECKING:
    from . import OpenAIConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OpenAIConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AI Task entities."""
    for subentry in config_entry.subentries.values():
        if subentry.subentry_type != "ai_task_data":
            continue

        async_add_entities(
            [AzureOpenAITaskEntity(config_entry, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


class AzureOpenAITaskEntity(
    ai_task.AITaskEntity,
    AzureOpenAIBaseLLMEntity,
):
    """Azure OpenAI AI Task entity."""

    _attr_supported_features = (
        ai_task.AITaskEntityFeature.GENERATE_DATA
        | ai_task.AITaskEntityFeature.GENERATE_IMAGE
        | ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
    )

    @override
    async def _async_generate_data(
        self,
        task: ai_task.GenDataTask,
        chat_log: conversation.ChatLog,
    ) -> ai_task.GenDataTaskResult:
        """Handle a generate data task."""
        await self._async_handle_chat_log(
            chat_log, task.name, task.structure, max_iterations=1000
        )

        if not isinstance(chat_log.content[-1], conversation.AssistantContent):
            raise HomeAssistantError(
                "Last content in chat log is not an AssistantContent"
            )

        text = chat_log.content[-1].content or ""

        if not task.structure:
            return ai_task.GenDataTaskResult(
                conversation_id=chat_log.conversation_id,
                data=text,
            )
        try:
            data = json_loads(text)
        except JSONDecodeError as err:
            _LOGGER.error(
                "Failed to parse JSON response: %s. Response: %s",
                err,
                text,
            )
            raise HomeAssistantError(
                "Error with Azure OpenAI structured response"
            ) from err

        return ai_task.GenDataTaskResult(
            conversation_id=chat_log.conversation_id,
            data=data,
        )

    @override
    async def _async_generate_image(
        self,
        task: ai_task.GenImageTask,
        chat_log: conversation.ChatLog,
    ) -> ai_task.GenImageTaskResult:
        """Handle a generate image task.

        Azure doesn't support the streamed image generation tool of the
        Responses API, so the Images API is used with the image deployment.
        """
        model = self.subentry.data.get(CONF_IMAGE_MODEL, RECOMMENDED_IMAGE_MODEL)
        client = self.entry.runtime_data
        attachments = task.attachments or []

        if any(not a.mime_type.startswith("image/") for a in attachments):
            raise HomeAssistantError(
                "Only image attachments are supported when generating images"
            )

        try:
            if attachments:
                images = await self.hass.async_add_executor_job(
                    lambda: [
                        (a.path.name, a.path.read_bytes(), a.mime_type)
                        for a in attachments
                    ]
                )
                response = await client.images.edit(
                    model=model, image=images, prompt=task.instructions
                )
            else:
                response = await client.images.generate(
                    model=model, prompt=task.instructions
                )
        except openai.OpenAIError as err:
            _LOGGER.error("Error generating image with Azure OpenAI: %s", err)
            raise HomeAssistantError(
                "Error generating image with Azure OpenAI"
            ) from err

        if not response.data or not response.data[0].b64_json:
            raise HomeAssistantError("No image returned")

        width = height = None
        if response.size and (size := re.fullmatch(r"(\d+)x(\d+)", response.size)):
            width, height = int(size[1]), int(size[2])

        return ai_task.GenImageTaskResult(
            image_data=base64.b64decode(response.data[0].b64_json),
            conversation_id=chat_log.conversation_id,
            mime_type=f"image/{response.output_format or 'png'}",
            width=width,
            height=height,
            model=model,
            revised_prompt=response.data[0].revised_prompt,
        )
