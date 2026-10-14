# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Releases before 5.0.0 are documented in the [GitHub release history](https://github.com/joselcaguilar/azure-openai-ha/releases).

## [5.0.1] — 2026-10-15

### Fixed

- Speech-to-text failed with `DeploymentNotFound`, so Assist showed **speech-to-text failed**, because Azure's v1 API can't route audio transcriptions to a deployment. Transcriptions now use the deployment's `/openai/deployments/{deployment}/audio/transcriptions` endpoint with API version `2025-04-01-preview`. If you use a gateway, it must forward this route too. Text-to-speech, conversation agents and AI tasks still use the v1 API. ([#183])

## [5.0.0] — 2026-10-14

This major release rebuilds the integration on the architecture of Home Assistant 2026.10's OpenAI integration, and adds AI tasks, speech-to-text, text-to-speech, and Microsoft Entra ID sign-in with deployment discovery. It includes every change from the 5.0.0-pre.1 to 5.0.0-pre.5 pre-releases, plus the `medium` default reasoning effort and the image quality setting from [#182].

Thanks to [@rac146](https://github.com/rac146) and [@SchmidSP](https://github.com/SchmidSP), whose [#160] and [#162] laid the groundwork for Home Assistant 2026.10 support.

### Breaking changes

- **Home Assistant 2026.10.0 or later is required.** Home Assistant 2026.10 pins `openai==3.10.0`, so the integration now requires `openai>=3.10.0,<4.0.0` (was `>=2.15.0,<3.0.0`). On older Home Assistant versions, stay on 4.5.x. ([#163])
- **The `azure_openai_conversation.generate_content` and `azure_openai_conversation.generate_image` actions are removed.** Use [`ai_task.generate_data`](https://www.home-assistant.io/integrations/ai_task/) and `ai_task.generate_image` in your automations and scripts instead. `generate_image` already failed, because it used DALL-E 3, which is retired on Azure. ([#164])
- **Configuration entries are migrated on first start and can't be downgraded.** Each entry's settings move to a conversation agent that keeps its entity and device, and an AI task that uses the same deployment is added. Settings saved by test builds from [#160] and [#162] are converted too. Version 4.x can't load a migrated entry, so back up Home Assistant before you upgrade. ([#164], [#169])
- **Temperature and Top P are no longer sent by default.** The new **Send sampling parameters (temperature/top_p)** setting is off by default, including for migrated agents. Your saved values are kept: turn the setting on in the agent's or AI task's settings to send them again. ([#168], [#169])

### Added

- AI tasks ([#164]):
  - `ai_task.generate_data` generates text or strict structured output, with image or PDF attachments.
  - `ai_task.generate_image` generates images, or edits attached ones, with the Azure OpenAI Images API. The default image deployment is `gpt-image-2.5-flare`.
- Speech-to-text and text-to-speech services that use your deployments' audio endpoints. Both have an **Instructions** setting, which the `tts` and `tts-hd` models ignore, and text-to-speech also has a **Speed** setting. The default models are `gpt-4o-mini-transcribe` and `gpt-4o-mini-tts`, and models such as `gpt-transcribe`, `whisper`, `tts` and `tts-hd` also work. ([#164], [#169])
- Microsoft Entra ID sign-in as an alternative to API keys. It uses the OAuth 2.0 authorization code flow with PKCE through Home Assistant application credentials, works only with Azure public-cloud endpoints, and needs the **Cognitive Services OpenAI User** role. ([#169])
- Deployment discovery with Entra ID sign-in ([#169], [#178]):
  - Setup finds the resource's deployments through Azure Resource Manager and adds the conversation agents, AI tasks, speech-to-text and text-to-speech services you select.
  - **Reconfigure** > **Microsoft Entra ID and rediscover models** adds newly deployed models, and offers only services that aren't added yet. It can also move an API-key entry to Entra ID sign-in.
  - Services store their deployment's underlying model name, so model-specific settings work with custom deployment names.
- Dedicated image AI tasks for image deployments, including DALL-E models. ([#169])
- **Image quality** setting for image AI tasks, and for data AI tasks with an image deployment. It defaults to `high` and offers only the levels the image model accepts. ([#182])
- **Send sampling parameters (temperature/top_p)** setting for conversation agents and data AI tasks. ([#168], closes [#166])
- Settings for newer models ([#164]):
  - Reasoning summary for o-series, GPT-5 and GPT-6 models, verbosity for GPT-5 and GPT-6, and pro mode for GPT-5.6 and GPT-6.
  - Code interpreter, which runs Python code in a container.
  - **Include links in web search results**.
  - **Store requests and responses in Azure OpenAI**, off by default. Encrypted reasoning lets tool calls continue without stored responses.
- Reauthentication, and reconfiguration of the endpoint and credentials. ([#164], [#169])

### Changed

- The integration follows the architecture of Home Assistant 2026.10's OpenAI integration. Each conversation agent, AI task, speech-to-text and text-to-speech service is a config subentry with its own settings, and you can add more of each. ([#164])
- Reasoning effort is sent to o-series, GPT-5 and GPT-6 models (previously only o-series), and its choices depend on the model. The default is now `medium` (was `low`) until you save a level; GPT-5 pro always uses `high`. ([#164], [#169], [#182])
- The default for **Maximum tokens to return in response** is now 3000 (was 150). ([#164])
- Web search uses the `web_search` tool instead of `web_search_preview`, and works with more models (previously only some GPT-4o and GPT-4.1 models). Answers leave out source links unless **Include links in web search results** is on. ([#164])
- If a deployment rejects an optional parameter, such as `temperature`, `reasoning` or `text.verbosity`, the request is retried without it, and that service stops sending it until the integration reloads. ([#164])
- Requests send `safety_identifier` and `prompt_cache_key` instead of the deprecated `user` parameter. ([#164])

### Fixed

- Setup failed on Home Assistant 2026.10 with `Requirements for azure_openai_conversation not found`. ([#163], fixes [#161])
- Since Home Assistant 2026.9, Assist tools were sent without their parameter schemas, so the model had to guess argument names. Schemas are now converted with `probatio`, as in Home Assistant core, and the `voluptuous-openapi` requirement is dropped. ([#163])
- Traditional Chinese translations never loaded, because the file was named `zh.json` instead of `zh-Hant.json`. ([#178])
- From Home Assistant 2026.11, an empty reply after a tool call no longer triggers tool-loop retries, because it's passed on as an explicit empty answer. ([#181])

### Security

- API keys are hidden while you type or paste them, and validation errors redact them. ([#178], [#181])
- With Entra ID sign-in, only the inference token is stored and refreshed. The short-lived Azure Resource Manager token used for discovery is never stored or logged. ([#169])

### Development

- Development targets Python 3.14 and Home Assistant 2026.10 in the lint workflow, devcontainer, Ruff settings and `docker-compose.yml`. ([#164])
- A pytest suite runs in CI after Ruff. Tests also keep every translation's keys and placeholders in sync with English. ([#169], [#178])
- Dependabot's metadata workflow accepts updates that don't touch `openai`. Version updates are skipped for `openai` and for the test dependencies Home Assistant pins, which must match Home Assistant's versions; security updates are still raised. ([#165], [#178], [#181])
- Updated GitHub Actions: `actions/checkout` v7, `actions/setup-python` v7, `dependabot/fetch-metadata` v3 and `softprops/action-gh-release` v3.0.3. ([#164], [#178])
- Updated development requirements: `homeassistant>=2026.10.0`, `colorlog>=6.12.0`, `pip>=26.2.1` and `ruff>=0.17.0`. ([#164], [#178], [#180])

[5.0.1]: https://github.com/joselcaguilar/azure-openai-ha/compare/v5.0.0...v5.0.1
[5.0.0]: https://github.com/joselcaguilar/azure-openai-ha/compare/v4.5.0...v5.0.0
[#160]: https://github.com/joselcaguilar/azure-openai-ha/pull/160
[#161]: https://github.com/joselcaguilar/azure-openai-ha/issues/161
[#162]: https://github.com/joselcaguilar/azure-openai-ha/pull/162
[#163]: https://github.com/joselcaguilar/azure-openai-ha/pull/163
[#164]: https://github.com/joselcaguilar/azure-openai-ha/pull/164
[#165]: https://github.com/joselcaguilar/azure-openai-ha/pull/165
[#166]: https://github.com/joselcaguilar/azure-openai-ha/issues/166
[#168]: https://github.com/joselcaguilar/azure-openai-ha/pull/168
[#169]: https://github.com/joselcaguilar/azure-openai-ha/pull/169
[#178]: https://github.com/joselcaguilar/azure-openai-ha/pull/178
[#180]: https://github.com/joselcaguilar/azure-openai-ha/pull/180
[#181]: https://github.com/joselcaguilar/azure-openai-ha/pull/181
[#182]: https://github.com/joselcaguilar/azure-openai-ha/pull/182
[#183]: https://github.com/joselcaguilar/azure-openai-ha/pull/183
