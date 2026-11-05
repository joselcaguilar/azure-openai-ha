"""AI Task integration for Azure OpenAI."""

from __future__ import annotations

import base64
from json import JSONDecodeError
import logging
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any, override

import openai
from openai.types.decision_create_params import Question
from openai.types.decision_input_message_param import DecisionInputMessageParam
from openai.types.decision_input_part_union_param import DecisionInputPartUnionParam

from homeassistant.components import ai_task, conversation
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.json import json_dumps
from homeassistant.util.json import json_loads

from .const import (
    CONF_AUTO_DISCOVERED,
    CONF_CHAT_MODEL,
    CONF_DEPLOYMENTS,
    CONF_IMAGE_MODEL,
    CONF_IMAGE_QUALITY,
    CONF_MODEL_NAME,
    RECOMMENDED_DECISION_MODEL,
    RECOMMENDED_IMAGE_MODEL,
    RECOMMENDED_IMAGE_QUALITY,
    get_image_quality_options,
)
from .entity import AzureOpenAIBaseLLMEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigSubentry

    from . import OpenAIConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

_DECISION_IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OpenAIConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AI Task entities."""
    for subentry in config_entry.subentries.values():
        if subentry.subentry_type in ("ai_task_data", "ai_task_image"):
            entity: ai_task.AITaskEntity = AzureOpenAITaskEntity(config_entry, subentry)
        elif subentry.subentry_type == "ai_task_evaluate":
            entity = AzureOpenAIEvaluationEntity(config_entry, subentry)
        else:
            continue

        async_add_entities(
            [entity],
            config_subentry_id=subentry.subentry_id,
        )


class AzureOpenAITaskEntity(
    ai_task.AITaskEntity,
    AzureOpenAIBaseLLMEntity,
):
    """Azure OpenAI AI Task entity."""

    def __init__(self, entry: OpenAIConfigEntry, subentry: ConfigSubentry) -> None:
        """Advertise only the APIs configured for this task."""
        super().__init__(entry, subentry)
        self._attr_supported_features = ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
        if subentry.subentry_type == "ai_task_image":
            self._attr_supported_features |= ai_task.AITaskEntityFeature.GENERATE_IMAGE
            if subentry.data.get(CONF_MODEL_NAME, "").startswith("dall-e-3"):
                self._attr_supported_features &= (
                    ~ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
                )
        else:
            self._attr_supported_features |= ai_task.AITaskEntityFeature.GENERATE_DATA
            if subentry.data.get(CONF_IMAGE_MODEL) or (
                CONF_DEPLOYMENTS not in entry.data
                and not subentry.data.get(CONF_AUTO_DISCOVERED)
            ):
                self._attr_supported_features |= (
                    ai_task.AITaskEntityFeature.GENERATE_IMAGE
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
        model_name = next(
            (
                deployment["model_name"]
                for deployment in self.entry.data.get(CONF_DEPLOYMENTS, [])
                if deployment["name"] == model
            ),
            self.subentry.data.get(CONF_MODEL_NAME, model)
            if self.subentry.subentry_type == "ai_task_image"
            else model,
        )
        client = self.entry.runtime_data
        attachments = task.attachments or []

        if any(not a.mime_type.startswith("image/") for a in attachments):
            raise HomeAssistantError(
                "Only image attachments are supported when generating images"
            )
        if attachments and model_name.startswith("dall-e-3"):
            raise HomeAssistantError("DALL-E 3 does not support image editing")
        if len(attachments) > 1 and model_name.startswith("dall-e-2"):
            raise HomeAssistantError("DALL-E 2 supports only one image attachment")
        extra_args: dict[str, Any] = {}
        if model_name.startswith("dall-e-"):
            extra_args["response_format"] = "b64_json"
        if quality_options := get_image_quality_options(model_name):
            quality = self.subentry.data.get(
                CONF_IMAGE_QUALITY, RECOMMENDED_IMAGE_QUALITY
            )
            # A re-pointed deployment can leave a level its new model rejects
            extra_args["quality"] = (
                quality if quality in quality_options else RECOMMENDED_IMAGE_QUALITY
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
                    model=model,
                    image=images[0] if model_name.startswith("dall-e-2") else images,
                    prompt=task.instructions,
                    **extra_args,
                )
            else:
                response = await client.images.generate(
                    model=model, prompt=task.instructions, **extra_args
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


def _read_image_base64(path: Path) -> str:
    """Read and encode an image off the event loop."""
    return base64.b64encode(path.read_bytes()).decode("ascii")


class AzureOpenAIEvaluationEntity(ai_task.AITaskEntity, AzureOpenAIBaseLLMEntity):
    """Azure OpenAI AI task evaluation entity, using the Decisions API."""

    _attr_supported_features = (
        ai_task.AITaskEntityFeature.EVALUATE
        | ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
    )

    @override
    async def _async_evaluate(
        self, task: ai_task.EvaluationTask
    ) -> ai_task.EvaluationTaskResult:
        """Evaluate questions using the Decisions API."""
        questions: list[Question] = []
        for question_id, question in task.questions.items():
            if question["type"] == "noul":
                questions.append(
                    {
                        "type": "predicate",
                        "name": question_id,
                        "instructions": question["instructions"],
                    }
                )
            elif question["type"] == "choice":
                questions.append(
                    {
                        "type": "choice",
                        "name": question_id,
                        "instructions": question["instructions"],
                        "choices": [
                            {"value": option, "description": description}
                            for option, description in question["criteria"].items()
                        ],
                    }
                )
            else:
                questions.append(
                    {
                        "type": "score",
                        "name": question_id,
                        "instructions": question["instructions"],
                        "levels": [
                            {"label": str(index), "description": description}
                            for index, description in enumerate(question["criteria"])
                        ],
                    }
                )

        state = task.state
        state_text = state if isinstance(state, str) else json_dumps(state)
        decision_input: str | list[DecisionInputMessageParam] = state_text
        if task.attachments:
            content: list[DecisionInputPartUnionParam] = []
            if state is not None:
                content.append({"type": "input_text", "text": state_text})
            for attachment in task.attachments:
                mime_type = attachment.mime_type.partition(";")[0].strip().lower()
                if mime_type == "image/jpg":
                    mime_type = "image/jpeg"
                if mime_type not in _DECISION_IMAGE_TYPES:
                    raise HomeAssistantError(
                        "Azure OpenAI decisions only support JPEG, PNG, WebP, and GIF "
                        f"image attachments; received {attachment.mime_type}"
                    )
                try:
                    encoded = await self.hass.async_add_executor_job(
                        _read_image_base64, attachment.path
                    )
                except OSError as err:
                    raise HomeAssistantError(
                        "Unable to read evaluation attachment"
                    ) from err
                content.append(
                    {
                        "type": "input_image",
                        "image_url": f"data:{mime_type};base64,{encoded}",
                    }
                )
            decision_input = [{"role": "user", "content": content}]

        model = self.subentry.data.get(CONF_CHAT_MODEL, RECOMMENDED_DECISION_MODEL)
        try:
            response = await self.entry.runtime_data.decisions.create(
                model=model,
                input=decision_input,
                questions=questions,
            )
        except openai.NotFoundError as err:
            # Azure answers 404 for a missing deployment or an unsupported region
            raise HomeAssistantError(
                f"Azure OpenAI decisions are not available for deployment `{model}`. "
                "They need a gpt-6-luna deployment in a region that supports the "
                f"Decisions API: {err}"
            ) from err
        except openai.OpenAIError as err:
            raise HomeAssistantError(
                f"Error evaluating with Azure OpenAI: {err}"
            ) from err

        answers: dict[str, ai_task.EvaluationAnswer] = {}
        for answer in response.answers:
            if answer.name is None:
                raise HomeAssistantError("Azure OpenAI returned an unnamed answer")
            question_id = answer.name
            if question_id not in task.questions or question_id in answers:
                raise HomeAssistantError(
                    "Azure OpenAI returned an unexpected question name"
                )
            if answer.type == "refusal":
                raise HomeAssistantError(
                    f"Azure OpenAI refused evaluation question {question_id}"
                )
            if answer.type == "predicate":
                answers[question_id] = ai_task.NoulAnswer(noul=answer.probability)
            elif answer.type == "choice":
                if not isinstance(answer.choice, str) or any(
                    not isinstance(option.value, str) for option in answer.probabilities
                ):
                    raise HomeAssistantError("Azure OpenAI returned an invalid choice")
                probabilities = {
                    option.value: option.probability for option in answer.probabilities
                }
                if len(probabilities) != len(answer.probabilities):
                    raise HomeAssistantError(
                        "Azure OpenAI returned duplicate choice probabilities"
                    )
                answers[question_id] = ai_task.ChoiceAnswer(
                    choice=answer.choice, probabilities=probabilities
                )
            elif answer.type == "score":
                levels = sorted(answer.probabilities, key=lambda level: level.value)
                if [level.value for level in levels] != list(range(len(levels))):
                    raise HomeAssistantError(
                        "Azure OpenAI returned invalid score levels"
                    )
                answers[question_id] = ai_task.ScoreAnswer(
                    score=answer.score,
                    probabilities=[level.probability for level in levels],
                )
            else:
                raise HomeAssistantError(
                    "Azure OpenAI returned an unsupported answer type"
                )
        return ai_task.EvaluationTaskResult(answers=answers)
