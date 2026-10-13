"""Exercise discovered deployment aliases through the native platforms and SDK."""

from collections.abc import AsyncGenerator
import base64
import json
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from respx import MockRouter

from homeassistant.components import ai_task, conversation, stt, tts
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.chat_session import async_get_chat_session

from custom_components.azure_openai_conversation.ai_task import AzureOpenAITaskEntity
from custom_components.azure_openai_conversation.auth import EntraOAuth2Implementation
from custom_components.azure_openai_conversation.const import (
    CONF_CHAT_MODEL,
    CONF_DEPLOYMENTS,
    CONF_IMAGE_MODEL,
    CONF_MODEL_NAME,
    CONF_REASONING_EFFORT,
    CONF_SEND_SAMPLING_PARAMETERS,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    DOMAIN,
    RECOMMENDED_REASONING_EFFORT,
)
from custom_components.azure_openai_conversation.deployments import (
    DeploymentData,
    DeploymentDiscovery,
    deployment_subentries,
    sync_deployment_subentries,
)
from custom_components.azure_openai_conversation.tts import AzureOpenAITTSEntity

from .const import ENDPOINT, RESOURCE_ID, TENANT_ID


@pytest.fixture
async def loaded_oauth_entry(
    hass: HomeAssistant,
    native_exposed_entities,
    oauth_implementation: EntraOAuth2Implementation,
    oauth_data: dict,
    deployment_inventory: list[DeploymentData],
    respx_mock: MockRouter,
) -> AsyncGenerator[MockConfigEntry]:
    """Load real entities with a shared OAuth client and mocked inference transport."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**oauth_data, CONF_DEPLOYMENTS: deployment_inventory},
        version=2,
        minor_version=2,
        subentries_data=deployment_subentries(deployment_inventory),
    )
    entry.add_to_hass(hass)
    respx_mock.get(f"{ENDPOINT}openai/v1/models").respond(
        json={"object": "list", "data": []}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    yield entry
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


def _entity_id(
    hass: HomeAssistant, entry: MockConfigEntry, service: str, deployment: str
) -> str:
    """Find a registered entity by its exact service and deployment, not its title."""
    model_key = CONF_IMAGE_MODEL if service == "ai_task_image" else CONF_CHAT_MODEL
    subentry = next(
        item
        for item in entry.subentries.values()
        if item.subentry_type == service and item.data[model_key] == deployment
    )
    domain = "ai_task" if service.startswith("ai_task") else service
    entity_id = er.async_get(hass).async_get_entity_id(
        domain, DOMAIN, subentry.subentry_id
    )
    assert entity_id is not None
    return entity_id


@pytest.mark.parametrize("remove_all", [False, True])
async def test_deleted_services_are_not_recreated(
    hass: HomeAssistant,
    loaded_oauth_entry: MockConfigEntry,
    remove_all: bool,
) -> None:
    """Service deletion persists through the automatic reload and a fresh setup."""
    registry = er.async_get(hass)
    original_entities = {
        item.config_subentry_id: item.entity_id
        for item in er.async_entries_for_config_entry(
            registry, loaded_oauth_entry.entry_id
        )
    }
    removed = set(loaded_oauth_entry.subentries)
    if not remove_all:
        removed = {
            item.subentry_id
            for item in loaded_oauth_entry.subentries.values()
            if item.subentry_type == "conversation"
            and item.data[CONF_CHAT_MODEL] == "ha-chat"
        }
    for subentry_id in removed:
        assert hass.config_entries.async_remove_subentry(
            loaded_oauth_entry, subentry_id
        )
    await hass.async_block_till_done()
    expected = set(original_entities) - removed
    assert set(loaded_oauth_entry.subentries) == expected
    for subentry_id in removed:
        assert registry.async_get(original_entities[subentry_id]) is None

    assert await hass.config_entries.async_unload(loaded_oauth_entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_setup(loaded_oauth_entry.entry_id)
    await hass.async_block_till_done()
    assert set(loaded_oauth_entry.subentries) == expected
    assert {
        item.entity_id
        for item in er.async_entries_for_config_entry(
            registry, loaded_oauth_entry.entry_id
        )
    } == {original_entities[subentry_id] for subentry_id in expected}


def _text_stream(text: str) -> str:
    """Build a minimal real Responses API stream consumed by the OpenAI SDK."""
    events = [
        {
            "type": "response.output_item.added",
            "sequence_number": 1,
            "output_index": 0,
            "item": {
                "type": "message",
                "id": "message-1",
                "role": "assistant",
                "status": "in_progress",
                "content": [],
            },
        },
        {
            "type": "response.output_text.delta",
            "sequence_number": 2,
            "item_id": "message-1",
            "output_index": 0,
            "content_index": 0,
            "delta": text,
            "logprobs": [],
        },
    ]
    return "".join(f"data: {json.dumps(event)}\n\n" for event in events) + (
        "data: [DONE]\n\n"
    )


@pytest.mark.parametrize(
    ("deployment", "reasoning"),
    [("ha-chat", True), ("daily-chat", False)],
)
async def test_conversation_alias_and_model_specific_parameters(
    hass: HomeAssistant,
    loaded_oauth_entry: MockConfigEntry,
    respx_mock: MockRouter,
    deployment: str,
    reasoning: bool,
) -> None:
    """Each selectable agent sends its alias and uses the underlying model's options."""
    route = respx_mock.post(f"{ENDPOINT}openai/v1/responses").respond(
        text=_text_stream("Hello from Azure"),
        headers={"Content-Type": "text/event-stream"},
    )
    result = await conversation.async_converse(
        hass,
        text="Hello",
        conversation_id=None,
        context=Context(),
        language="en",
        agent_id=_entity_id(hass, loaded_oauth_entry, "conversation", deployment),
    )
    assert result.response.speech["plain"]["speech"] == "Hello from Azure"
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer inference-token"
    body = json.loads(request.content)
    assert body["model"] == deployment
    assert "temperature" not in body
    assert "top_p" not in body
    assert ("reasoning" in body) is reasoning
    if reasoning:
        assert body["reasoning"]["effort"] == RECOMMENDED_REASONING_EFFORT
        assert "verbosity" in body["text"]
        assert body["include"] == ["reasoning.encrypted_content"]


@pytest.mark.parametrize("service", ["conversation", "ai_task_data"])
@pytest.mark.parametrize(
    ("model_name", "expected_effort"),
    [
        ("gpt-5.2-pro", "medium"),
        ("gpt-5-pro", "high"),
    ],
)
async def test_reasoning_models_use_supported_recommended_effort(
    hass: HomeAssistant,
    loaded_oauth_entry: MockConfigEntry,
    respx_mock: MockRouter,
    service: str,
    model_name: str,
    expected_effort: str,
) -> None:
    """Discovered services use valid effort defaults without opening their settings."""
    inventory = [
        {**item, "model_name": model_name} if item["name"] == "ha-chat" else item
        for item in loaded_oauth_entry.data[CONF_DEPLOYMENTS]
    ]
    hass.config_entries.async_update_entry(
        loaded_oauth_entry,
        data={**loaded_oauth_entry.data, CONF_DEPLOYMENTS: inventory},
    )
    await hass.async_block_till_done()
    route = respx_mock.post(f"{ENDPOINT}openai/v1/responses").respond(
        text=_text_stream("A supported response"),
        headers={"Content-Type": "text/event-stream"},
    )
    entity_id = _entity_id(hass, loaded_oauth_entry, service, "ha-chat")
    if service == "conversation":
        result = await conversation.async_converse(
            hass,
            text="Hello",
            conversation_id=None,
            context=Context(),
            language="en",
            agent_id=entity_id,
        )
        assert result.response.speech["plain"]["speech"] == "A supported response"
    else:
        result = await ai_task.async_generate_data(
            hass,
            task_name="Recommended task",
            entity_id=entity_id,
            instructions="Respond to this example",
        )
        assert result.data == "A supported response"
    body = json.loads(route.calls[0].request.content)
    assert body["reasoning"]["effort"] == expected_effort


async def test_data_task_uses_its_chat_deployment(
    hass: HomeAssistant,
    loaded_oauth_entry: MockConfigEntry,
    respx_mock: MockRouter,
) -> None:
    """A data task works through Home Assistant with the same renewable OAuth client."""
    route = respx_mock.post(f"{ENDPOINT}openai/v1/responses").respond(
        text=_text_stream("A concise summary"),
        headers={"Content-Type": "text/event-stream"},
    )
    result = await ai_task.async_generate_data(
        hass,
        task_name="Summary",
        entity_id=_entity_id(hass, loaded_oauth_entry, "ai_task_data", "daily-chat"),
        instructions="Summarize this example",
    )
    assert result.data == "A concise summary"
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer inference-token"
    body = json.loads(request.content)
    assert body["model"] == "daily-chat"
    assert "temperature" not in body
    assert "top_p" not in body


@pytest.mark.parametrize("service", ["conversation", "ai_task_data"])
@pytest.mark.parametrize(
    ("deployment", "effort", "sampling"),
    [
        ("daily-chat", None, True),
        ("ha-chat", "none", True),
        ("ha-chat", "high", False),
    ],
)
async def test_initial_settings_send_effort_and_compatible_opt_in_sampling(
    hass: HomeAssistant,
    loaded_oauth_entry: MockConfigEntry,
    respx_mock: MockRouter,
    service: str,
    deployment: str,
    effort: str | None,
    sampling: bool,
) -> None:
    """Gear settings with Recommended enabled reach the actual inference request."""
    if effort == "none":
        inventory = [
            {**item, "model_name": "gpt-5.4"} if item["name"] == deployment else item
            for item in loaded_oauth_entry.data[CONF_DEPLOYMENTS]
        ]
        hass.config_entries.async_update_entry(
            loaded_oauth_entry,
            data={**loaded_oauth_entry.data, CONF_DEPLOYMENTS: inventory},
        )
        await hass.async_block_till_done()
    subentry = next(
        item
        for item in loaded_oauth_entry.subentries.values()
        if item.subentry_type == service and item.data[CONF_CHAT_MODEL] == deployment
    )
    result = await hass.config_entries.subentries.async_init(
        (loaded_oauth_entry.entry_id, service),
        context={"source": "reconfigure", "subentry_id": subentry.subentry_id},
    )
    settings = {
        CONF_CHAT_MODEL: deployment,
        "recommended": True,
        CONF_SEND_SAMPLING_PARAMETERS: True,
        CONF_TOP_P: 0.35,
        CONF_TEMPERATURE: 0.65,
    }
    if effort is not None:
        settings[CONF_REASONING_EFFORT] = effort
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], settings
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    route = respx_mock.post(f"{ENDPOINT}openai/v1/responses").respond(
        text=_text_stream("Configured response"),
        headers={"Content-Type": "text/event-stream"},
    )
    entity_id = _entity_id(hass, loaded_oauth_entry, service, deployment)
    if service == "conversation":
        result = await conversation.async_converse(
            hass,
            text="Hello",
            conversation_id=None,
            context=Context(),
            language="en",
            agent_id=entity_id,
        )
        assert result.response.speech["plain"]["speech"] == "Configured response"
    else:
        result = await ai_task.async_generate_data(
            hass,
            task_name="Configured task",
            entity_id=entity_id,
            instructions="Respond to this example",
        )
        assert result.data == "Configured response"
    body = json.loads(route.calls[0].request.content)
    assert body["model"] == deployment
    assert ("reasoning" in body) is (effort is not None)
    if effort is not None:
        assert body["reasoning"]["effort"] == effort
    assert ("temperature" in body) is sampling
    assert ("top_p" in body) is sampling
    if sampling:
        assert body["temperature"] == 0.65
        assert body["top_p"] == 0.35


async def test_image_task_uses_its_image_deployment(
    hass: HomeAssistant,
    loaded_oauth_entry: MockConfigEntry,
    respx_mock: MockRouter,
) -> None:
    """A dedicated image task uses Images, never a text or default image deployment."""
    image = b"generated-image-bytes"
    route = respx_mock.post(f"{ENDPOINT}openai/v1/images/generations").respond(
        json={
            "created": 1,
            "data": [{"b64_json": base64.b64encode(image).decode()}],
            "size": "1024x1024",
            "output_format": "png",
        }
    )
    entity_id = _entity_id(hass, loaded_oauth_entry, "ai_task_image", "art")
    entity = hass.data[ai_task.DATA_COMPONENT].get_entity(entity_id)
    assert isinstance(entity, AzureOpenAITaskEntity)
    with async_get_chat_session(hass) as session:
        result = await entity.internal_async_generate_image(
            session, ai_task.GenImageTask(name="Art", instructions="Draw an example")
        )
    assert result.image_data == image
    assert result.model == "art"
    assert result.width == result.height == 1024
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer inference-token"
    body = json.loads(request.content)
    assert body["model"] == "art"
    assert "temperature" not in body
    assert "top_p" not in body


async def test_stt_uses_its_transcription_deployment(
    hass: HomeAssistant,
    loaded_oauth_entry: MockConfigEntry,
    respx_mock: MockRouter,
) -> None:
    """STT sends the discovered alias and a WAV file with an inference bearer token."""
    route = respx_mock.post(f"{ENDPOINT}openai/v1/audio/transcriptions").respond(
        json={"text": "Turn on the lights"}
    )
    entity = stt.async_get_speech_to_text_entity(
        hass, _entity_id(hass, loaded_oauth_entry, "stt", "listen")
    )
    assert entity is not None
    metadata = stt.SpeechMetadata(
        language="en-US",
        format=stt.AudioFormats.WAV,
        codec=stt.AudioCodecs.PCM,
        bit_rate=stt.AudioBitRates.BITRATE_16,
        sample_rate=stt.AudioSampleRates.SAMPLERATE_16000,
        channel=stt.AudioChannels.CHANNEL_MONO,
    )

    async def audio() -> AsyncGenerator[bytes]:
        """Provide a short PCM stream without reading local user recordings."""
        yield b"\0\0" * 16

    result = await entity.async_process_audio_stream(metadata, audio())
    assert result.result is stt.SpeechResultState.SUCCESS
    assert result.text == "Turn on the lights"
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer inference-token"
    assert b'name="model"\r\n\r\nlisten' in request.content
    assert b'name="language"\r\n\r\nen' in request.content
    assert b"RIFF" in request.content


@pytest.mark.parametrize(
    ("model_name", "supports_instructions"),
    [
        ("tts", False),
        ("tts-1", False),
        ("gpt-4o-mini-tts", True),
    ],
)
async def test_tts_uses_alias_and_underlying_model_capabilities(
    hass: HomeAssistant,
    loaded_oauth_entry: MockConfigEntry,
    respx_mock: MockRouter,
    model_name: str,
    supports_instructions: bool,
) -> None:
    """Speech aliases do not accidentally send unsupported legacy TTS instructions."""
    inventory = [
        {**item, "model_name": model_name} if item["name"] == "speak" else item
        for item in loaded_oauth_entry.data[CONF_DEPLOYMENTS]
    ]
    subentry = next(
        item
        for item in loaded_oauth_entry.subentries.values()
        if item.subentry_type == "tts"
    )
    hass.config_entries.async_update_entry(
        loaded_oauth_entry,
        data={**loaded_oauth_entry.data, CONF_DEPLOYMENTS: inventory},
    )
    hass.config_entries.async_update_subentry(
        loaded_oauth_entry,
        subentry,
        data={
            **subentry.data,
            CONF_MODEL_NAME: model_name,
            "prompt": "Speak cheerfully",
        },
    )
    await hass.async_block_till_done()
    route = respx_mock.post(f"{ENDPOINT}openai/v1/audio/speech").respond(
        content=b"generated-audio", headers={"Content-Type": "audio/mpeg"}
    )
    entity_id = _entity_id(hass, loaded_oauth_entry, "tts", "speak")
    entity = hass.data[tts.DATA_COMPONENT].get_entity(entity_id)
    assert isinstance(entity, AzureOpenAITTSEntity)
    result = await entity.async_get_tts_audio(
        "Hello", "en-US", dict(entity.default_options)
    )
    assert result == ("mp3", b"generated-audio")
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer inference-token"
    body = json.loads(request.content)
    assert body["model"] == "speak"
    assert ("instructions" in body) is supports_instructions
    if supports_instructions:
        assert body["instructions"] == "Speak cheerfully"


async def test_loaded_reconfigure_adds_services_with_one_reload(
    hass: HomeAssistant,
    loaded_oauth_entry: MockConfigEntry,
    deployment_inventory: list[DeploymentData],
) -> None:
    """Token updates reuse the client; rediscovery preserves entities and adds services once."""
    subentry = next(
        item
        for item in loaded_oauth_entry.subentries.values()
        if item.subentry_type == "conversation"
        and item.data[CONF_CHAT_MODEL] == "ha-chat"
    )
    hass.config_entries.async_update_subentry(
        loaded_oauth_entry,
        subentry,
        data={**subentry.data, "prompt": "Keep my instructions", "max_tokens": 9000},
    )
    await hass.async_block_till_done()
    original_data = dict(subentry.data)
    removed_speech = next(
        item
        for item in loaded_oauth_entry.subentries.values()
        if item.subentry_type == "stt"
    )
    assert hass.config_entries.async_remove_subentry(
        loaded_oauth_entry, removed_speech.subentry_id
    )
    await hass.async_block_till_done()
    assert removed_speech.subentry_id not in loaded_oauth_entry.subentries
    registry = er.async_get(hass)
    original_ids = {
        item.entity_id
        for item in er.async_entries_for_config_entry(
            registry, loaded_oauth_entry.entry_id
        )
    }
    inventory = [
        *(item for item in deployment_inventory if item["name"] != "daily-chat"),
        DeploymentData(
            id=f"{RESOURCE_ID}/deployments/new-chat",
            name="new-chat",
            model_name="gpt-4.1-mini",
            services=["conversation", "ai_task_data"],
            unsupported_reason="",
        ),
        DeploymentData(
            id=f"{RESOURCE_ID}/deployments/new-speech",
            name="new-speech",
            model_name="gpt-4o-mini-tts",
            services=["tts"],
            unsupported_reason="",
        ),
    ]
    with (
        patch.object(
            EntraOAuth2Implementation,
            "_token_request",
            return_value={"access_token": "management-token", "expires_in": 3600},
        ),
        patch(
            "custom_components.azure_openai_conversation.config_flow.async_discover_deployments",
            return_value=DeploymentDiscovery(ENDPOINT, inventory),
        ),
        patch(
            "custom_components.azure_openai_conversation.config_flow.validate_input",
            return_value=None,
        ),
        patch.object(
            hass.config_entries,
            "async_reload",
            wraps=hass.config_entries.async_reload,
        ) as reload,
    ):
        client = loaded_oauth_entry.runtime_data
        hass.config_entries.async_update_entry(
            loaded_oauth_entry,
            data={
                **loaded_oauth_entry.data,
                "token": {
                    **loaded_oauth_entry.data["token"],
                    "access_token": "rotated-token",
                },
            },
        )
        await hass.async_block_till_done()
        reload.assert_not_awaited()
        assert loaded_oauth_entry.runtime_data is client
        hass.config_entries.async_update_subentry(
            loaded_oauth_entry, subentry, title="My assistant"
        )
        await hass.async_block_till_done()
        reload.assert_awaited_once_with(loaded_oauth_entry.entry_id)
        reload.reset_mock()
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": "reconfigure",
                "entry_id": loaded_oauth_entry.entry_id,
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "entra_id"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"tenant_id": TENANT_ID, "resource_id": RESOURCE_ID},
        )
        assert result["step_id"] == "discovery_confirm"
        # Only new-chat, new-speech, and the deleted listen service remain to add.
        assert result["description_placeholders"]["service_count"] == "4"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "conversation": ["new-chat"],
                "ai_task_data": ["new-chat"],
                "stt": ["listen"],
            },
        )
        await hass.async_block_till_done()
        assert result["reason"] == "reconfigure_successful"
        reload.assert_awaited_once_with(loaded_oauth_entry.entry_id)
    subentry = loaded_oauth_entry.subentries[subentry.subentry_id]
    assert subentry.data == original_data
    assert subentry.title == "My assistant"
    assert removed_speech.subentry_id not in loaded_oauth_entry.subentries
    assert _entity_id(hass, loaded_oauth_entry, "stt", "listen")
    assert not sync_deployment_subentries(hass, loaded_oauth_entry)
    entities = er.async_entries_for_config_entry(registry, loaded_oauth_entry.entry_id)
    assert len(entities) == 9
    assert original_ids <= {item.entity_id for item in entities}
    for item in entities:
        state = hass.states.get(item.entity_id)
        assert state is not None
        assert state.state != "unavailable"
        service = loaded_oauth_entry.subentries[item.config_subentry_id]
        if service.subentry_type == "conversation":
            agent = conversation.async_get_agent(hass, item.entity_id)
            assert agent is not None
            assert agent.subentry is service
        elif service.subentry_type.startswith("ai_task"):
            features = ai_task.AITaskEntityFeature(
                state.attributes["supported_features"]
            )
            assert bool(features & ai_task.AITaskEntityFeature.GENERATE_DATA) == (
                service.subentry_type == "ai_task_data"
            )
            assert bool(features & ai_task.AITaskEntityFeature.GENERATE_IMAGE) == (
                service.subentry_type == "ai_task_image"
            )
