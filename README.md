[![hacs_badge](https://img.shields.io/badge/My_HACS-Azure_OpenAI_Conversation-41BDF5?logo=homeassistant&logoColor=white)](https://my.home-assistant.io/redirect/hacs_repository/?owner=joselcaguilar&repository=azure-openai-ha&category=integration)
[![Validate workflow](https://img.shields.io/github/actions/workflow/status/joselcaguilar/azure-openai-ha/validate.yaml?label=Validate&logo=GitHub)](https://github.com/joselcaguilar/azure-openai-ha/actions/workflows/validate.yaml)
[![Lint workflow](https://img.shields.io/github/actions/workflow/status/joselcaguilar/azure-openai-ha/lint.yaml?label=Lint&logo=GitHub)](https://github.com/joselcaguilar/azure-openai-ha/actions/workflows/lint.yaml)
![GitHub all releases](https://img.shields.io/github/downloads/joselcaguilar/azure-openai-ha/total?color=d9810f&label=Downloads&logo=GitHub)
[![GitHub Sponsor](https://img.shields.io/static/v1?label=Sponsor&message=%E2%9D%A4&logo=GitHub&color=%23fe8e86)](https://github.com/sponsors/joselcaguilar)
[![BuyMeACoffee](https://img.shields.io/badge/-Buy_me_a%C2%A0coffee-gray?logo=buy-me-a-coffee)](https://www.buymeacoffee.com/joselcaguilar)

<p align="center">
<img src="https://raw.githubusercontent.com/joselcaguilar/azure-openai-ha/main/.attachments/icon.png#gh-light-mode-only">
<img src="https://raw.githubusercontent.com/joselcaguilar/azure-openai-ha/main/.attachments/dark_icon.png#gh-dark-mode-only">
</p>

<h3 align="center">

[Azure OpenAI Conversation Custom Integration](https://github.com/joselcaguilar/azure-openai-ha) for Home Assistant
</h3>

# What This Is

This custom integration adds conversation agents, AI tasks, speech-to-text and text-to-speech powered by [Azure OpenAI](https://azure.microsoft.com/products/cognitive-services/openai-service) in Home Assistant, it's based on the original [OpenAI Conversation integration](https://www.home-assistant.io/integrations/openai_conversation/) for Home Assistant.

# What It Does

This is equivalent to the built-in [OpenAI Conversation integration](https://www.home-assistant.io/integrations/openai_conversation/). The difference is that it uses the OpenAI algorithms available through Azure. Other than that the goal is to keep the differences to a minimum. You can use this conversation integration with Assistants in Home Assistant to control you house. They have all the capabilities the built-in OpenAI Conversation integration has.

# Limitations

<center>

| Azure OpenAI Conversation Version | Home Assistant Version | Minimal API Version    |
| --------------------------------- | ---------------------- | ---------------------- |
| 0.x.y                             | 2023.4.x               | 2023-06-01-preview     |
| 1.x.y                             | 2023.5+                | 2023-06-01-preview     |
| 2.x.y                             | 2025.1                 | 2023-12-01-preview     |
| 3.1.y                             | 2025.6                 | - no need to specify - |
| 4.0.y                             | 2025.8 - 2025.9        | - no need to specify - |
| 4.1.y                             | 2025.10+               | - no need to specify - |
| 4.2.y                             | 2025.12+               | - no need to specify - |
| 4.3.y                             | 2026.2.1+              | - no need to specify - |
| 4.4.y                             | 2026.6.0+              | - no need to specify - |
| 4.5.y                             | 2026.9.0+              | - no need to specify - |
| 5.0.y                             | 2026.10.0+             | - no need to specify - |

</center>

# Installation and Configuration

## Configuring Azure Models

1. Deploy an [Azure AI Foundry](https://portal.azure.com/#create/Microsoft.CognitiveServicesAIFoundry) instance to a **region supported by the [Responses API](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/responses?tabs=python-secure#region-availability)**.  
   *(If you already have a Foundry instance, you can skip this step.)*
2. To enable conversations and AI tasks, [deploy a Responses-compatible model](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/responses#supported-models), such as `gpt-4.1-mini`, `gpt-5-mini`, or `gpt-6.1-sol`.
   *Deployment names can be different from model names. Microsoft sign-in discovers both automatically; API-key users enter the exact deployment name in the service's first configuration screen. **Recommended model settings** never changes the selected deployment.*
3. Optionally deploy more models:
   - An image model such as `gpt-image-2.5-flare`, `gpt-image-2` or `gpt-image-1` to generate images with AI tasks.
   - `gpt-transcribe`, `gpt-4o-mini-transcribe`, `gpt-4o-transcribe` or `whisper` for speech-to-text.
   - `gpt-4o-mini-tts`, `tts` or `tts-hd` for text-to-speech. Legacy `tts-1` and `tts-1-hd` model names remain supported.

## Setting Up the Integration

4. Download and install the integration from HACS: [Azure OpenAI Conversation](https://my.home-assistant.io/redirect/hacs_repository/?owner=joselcaguilar&repository=azure-openai-ha&category=integration).
5. Restart your Home Assistant instance.
6. [Click here](https://my.home-assistant.io/redirect/config_flow_start/?domain=azure_openai_conversation) or go to **Settings → Devices & Services → Add Integration → Azure OpenAI Conversation**.
7. Choose **Microsoft Entra ID sign-in and model discovery** to discover deployed models, or **API key** for manual configuration.
8. With Microsoft sign-in, enter the tenant ID and the ARM resource ID of your Foundry or Azure OpenAI **account**, link your Microsoft account, then select models separately for **Conversation**, **Data AI tasks**, **Image AI tasks**, **Speech-to-text**, and **Text-to-speech**. Nothing is preselected; only your selected deployment/service pairs are added. With an API key, enter the key and endpoint (for example `https://your-resource.services.ai.azure.com/`); the legacy conversation agent and AI task are created, and you select their deployment names manually.
9. Select the desired conversation, speech-to-text, and text-to-speech entities in your Assist pipeline. Use the **Add** buttons if you want additional customized instances.

Configurations created with versions before 5.0 are migrated automatically: the existing agent keeps its options and an AI task using the same deployment is added.

## Microsoft Entra ID browser sign-in

This integration uses Home Assistant's native OAuth2 account linking, authorization code flow with PKCE, and token refresh. It does not use a resource API key, a custom MSAL login window, or device-code authentication.

Before linking your account:

1. Create a dedicated **Microsoft Entra ID > App registrations** application for your Home Assistant instance. A single-tenant registration is sufficient. Under **Authentication**, add a **Web** redirect URI of `https://my.home-assistant.io/redirect/oauth` when using the My Home Assistant integration. Without it, register the exact Home Assistant frontend callback URL, `{frontend-url}/auth/external/callback`. Do not register the callback as a SPA.
2. Add **delegated** `user_impersonation` API permissions for **Microsoft Cognitive Services** and **Azure Service Management**. Remove unrelated default Microsoft Graph permissions from this dedicated application. Grant admin consent if your directory requires it. The sign-in requests `offline_access` for refresh tokens and static consent for the application's configured permissions.
3. Create an application client secret and record its **value**, application/client ID, and directory/tenant ID. Add the client ID and secret when Home Assistant asks for **Application Credentials**, or under **Settings > Devices & Services > Application Credentials**. This secret authenticates your Web application; it is not the Azure inference API key. Do not place credentials in source code or automations, and renew the secret before it expires.
4. Give the **signed-in user**, or a group containing that user, resource-scoped **Cognitive Services OpenAI User** access. This role includes both inference permissions and the account/deployment/model reads needed for discovery; a separate **Reader** assignment is not required. If using custom roles, include both kinds of permission. OAuth consent alone is not an Azure RBAC assignment, and assigning roles only to the app's service principal does not authorize the signed-in user.
5. Copy the account's ARM resource ID from its Azure portal **Properties** or **JSON view**. Its shape is `/subscriptions/<subscription-id>/resourceGroups/<group>/providers/Microsoft.CognitiveServices/accounts/<account>`, not a Foundry project or deployment child ID.

Home Assistant stores and refreshes only the inference token. Discovery requests a short-lived Azure Resource Manager token when it runs and never stores it. Access and refresh tokens are never logged by this integration. OAuth is limited to trusted Azure public-cloud inference endpoints. Sovereign-cloud endpoints and custom API gateways continue to require the manual API-key path.

Application credentials and refresh tokens are sensitive data in Home Assistant's configuration storage and backups. Restrict access to that storage and protect backups with encryption. Revoking consent, expiring the application secret, or changing Conditional Access policies can require Microsoft sign-in again and interrupt unattended Assist.

For OAuth consent details, see [Microsoft identity platform scopes](https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc#the-default-scope). For Home Assistant account linking, see [Application Credentials](https://www.home-assistant.io/integrations/application_credentials/).

## Automatic deployed-model discovery

Discovery reads the selected resource's actual ARM **deployments**, including all pages, and filters to the OpenAI publisher. The available-model catalog is used only for capability metadata; undeployed catalog models are never added.

| Deployed model capability | Available services to select |
| --- | --- |
| Responses-compatible chat/reasoning, including `gpt-6.1-sol` | Conversation agents and/or data/structured-data AI tasks |
| OpenAI image generation | One dedicated image AI task per deployment |
| File transcription (`whisper`, `gpt-transcribe`, `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`) | One speech-to-text service per deployment |
| Speech generation (`tts`, `tts-hd`, legacy `tts-1*`, `gpt-4o-mini-tts`) | One text-to-speech service per deployment |
| Embeddings, realtime/audio chat, diarization, video, completion-only or other incompatible APIs | Reported in the discovery summary; no incompatible service is created |

Batch-only deployments and deployments that have not succeeded are also reported rather than added. The discovery dialog shows how many deployments cannot be added and lists them by name and model; with debug logging enabled, the log shows why each one was not added. A chat-completions model is not assumed to support the Responses API merely because it supports chat. Capability-matched services remain subject to Azure model, region, quota, and networking availability.

To add newly deployed models, use the **integration entry's** menu > **Reconfigure** > **Microsoft Entra ID and rediscover models**, then select which models to add for each service type. The dialog counts and lists the deployments that still have services to add, and only model/service pairs that are not already added can be selected; if every supported model is already added, the dialog says so, and submitting only saves the refreshed sign-in and deployment inventory. A valid linked account is reused. API-key configurations can migrate to Microsoft sign-in through the same menu. Selecting a conversation model does not also add an AI task; leave unwanted service types empty. You can leave every selection empty to refresh the inventory without adding services.

Reconfiguration adds only explicitly selected missing services without duplicating matching deployment/service pairs or changing existing entity IDs, names, prompts, or customized options. Existing services are not offered again and remain configured. Removed or unsupported deployments do not cause existing services to be deleted; remove or retarget stale services yourself. Services created by discovery use the deployment alias for API requests and the underlying model name for model-specific options, even when an alias is named `home-assistant` instead of `gpt-6.1-sol`.

Delete an unwanted model/service from its menu under the integration entry. It stays removed across integration reloads, Home Assistant restarts, reauthentication, and rediscovery unless you explicitly select it again or manually add it. Startup refreshes existing deployment metadata without creating missing services. You do not need to delete the deployed model from Azure.

API keys authorize inference, not ARM deployment discovery. The manual API-key path therefore does not automatically enumerate your deployments and keeps existing gateway configurations working.

### Speech models and realtime audio

For an Assist pipeline, a practical OpenAI pairing is **`gpt-transcribe` for STT** and **`gpt-4o-mini-tts` for TTS**, where those models are available in your Foundry account's region. Microsoft recommends `gpt-transcribe` for file transcription, and the integration passes it your pipeline's language as a hint. TTS uses the REST `/openai/v1/audio/speech` endpoint. STT uses the deployment's REST `/openai/deployments/{deployment}/audio/transcriptions` endpoint with API version `2025-04-01-preview`, because Azure's v1 transcription endpoint returns `DeploymentNotFound`; if you use a gateway, make sure it forwards this route too.

**`gpt-realtime-2.1` is not a drop-in STT or TTS model for these endpoints.** Realtime speech-to-speech models use a separate streaming API with WebRTC, WebSocket, or SIP sessions; supporting them requires a dedicated realtime implementation. Discovery therefore reports realtime models as unsupported rather than creating incompatible STT/TTS entities. The realtime-only `gpt-live-transcribe` and `gpt-realtime-whisper` models are also excluded. See Microsoft's [audio model catalog](https://learn.microsoft.com/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure#audio-models) for current model versions and availability.

#  Options

Each conversation agent, AI task, speech-to-text and text-to-speech service has its own options:

1. Browse to your Home Assistant instance.
2. In the sidebar click on [Settings -> Devices & Services](https://my.home-assistant.io/redirect/integrations/).
3. Find the Azure OpenAI Conversation integration and click the ⋮ menu of the agent or service you want to change, then **Reconfigure**.

Options available:
- **Instructions:**
The starting text for the AI language model to generate new text from. This text can include information about your Home Assistant instance, devices, and areas and is written using [Home Assistant Templating](https://www.home-assistant.io/docs/configuration/templating).

- **Model deployment:** The name of the model deployment used for text generation (i.e.- `my-gpt35-model`). You can find more details on the available models in the [Azure OpenAI Documentation](https://learn.microsoft.com/azure/cognitive-services/openai/concepts/models#finding-what-models-are-available). If you are having issues using an assistant that uses this integration please check this model is the model you actually deployed.

- **Maximum Tokens to Return in Response**
The maximum number of words or "tokens" that the AI model should generate in its completion of the prompt. For more information, see the [Azure OpenAI Completion Documentation](https://learn.microsoft.com/azure/cognitive-services/openai/overview#tokens).

- **Send sampling parameters (temperature/top_p):** **Off by default** for conversation agents and data AI tasks, and available directly in their initial settings dialog even with **Recommended model settings** enabled. Existing explicit on/off choices are preserved. **Temperature and Top P appear only while this checkbox is enabled.** When disabled, both parameters are omitted from the first request, regardless of the deployment name or reasoning effort. Saved numeric values are retained for re-enabling. Reasoning models still omit sampling parameters unless their reasoning effort is `none`.

- **Reasoning effort:** Available directly in the initial settings dialog for supported reasoning models, even with **Recommended model settings** enabled. The selector offers only levels supported by the underlying model; fixed-effort and non-reasoning models do not show it. Discovery metadata resolves deployment aliases to model families. The recommended effort is `medium`, which services also use until a level is saved in their settings; fixed-effort models such as `gpt-5-pro` use their only supported level. If changing deployment makes the selected effort invalid, the form asks you to choose a supported level instead of saving it. Image AI tasks and speech-to-text services do not show it because the Images and audio transcription APIs have no reasoning parameter; image tasks offer **Image quality** instead.

- **Temperature:** A value that determines the level of creativity and risk-taking the model should use when generating text. A higher temperature means the model is more likely to generate unexpected results, while a lower temperature results in more deterministic results. See the [Azure OpenAI Completion Documentation](https://learn.microsoft.com/azure/cognitive-services/openai/how-to/completions) for more information.

- **Top P:** An alternative to temperature, top_p determines the proportion of the most likely word choices the model should consider when generating text. A higher top_p means the model will only consider the most likely words, while a lower top_p means a wider range of words, including less likely ones, will be considered. For more information, see the [Azure OpenAI Completion Documentation](https://learn.microsoft.com/azure/cognitive-services/openai/how-to/completions).

- **Store requests and responses:** Keep responses in Azure OpenAI so they can be retrieved later.

Depending on the underlying discovered model, including metadata retained after switching to API-key authentication, more options are shown. If the model is unknown, manual API-key configurations use the deployment name:
- **Reasoning summary**, **Verbosity** and **Pro mode** for reasoning models such as o-series, GPT-5 and GPT-6, after disabling **Recommended model settings**.
- **Web search:** Lets the model search the web with [Grounding with Bing Search](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/web-search), which has additional costs.
- **Code interpreter:** Lets the model run Python code in a [container](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/responses), billed per session.
- **Image model deployment** (data AI tasks only): An optional image deployment to also enable `ai_task.generate_image` on that task. Automatically discovered chat tasks do not assume an image model is deployed. Image models get their own dedicated AI tasks. Legacy API-key tasks keep their previous image-model default until explicitly configured.
- **Image quality** (image AI tasks, and data AI tasks once an image model deployment is saved): Defaults to `high`, the Azure OpenAI Images API default. The selector offers only levels the image model accepts: `low`, `medium` and `high` for GPT-image models, plus `xhigh`, `max` and `auto` for `gpt-image-2.5` models. DALL-E models do not receive it. If changing deployment makes the selected level invalid, the form asks you to choose a supported one; if a deployment's underlying model changes and rejects the saved level, requests use `high`.

If a deployment rejects an optional parameter, such as temperature for reasoning models, the request is retried without it.

Speech-to-text and text-to-speech services let you choose the model deployment and instructions to improve the transcripts or control the voice, and the speed for text-to-speech. Editing instructions keeps the selected deployment. Azure `tts`/`tts-hd` and legacy `tts-1`/`tts-1-hd` models do not receive the unsupported instructions parameter.

## AI tasks

Use the [`ai_task.generate_data`](https://www.home-assistant.io/integrations/ai_task/) action to generate text or structured data, with image or PDF attachments, and `ai_task.generate_image` to generate or edit images. They replace the `azure_openai_conversation.generate_content` and `azure_openai_conversation.generate_image` actions, which were removed in 5.0.

Dedicated image tasks expose image generation only, not text or structured-data generation. DALL-E 3 does not support image editing; DALL-E 2 accepts at most one image attachment.

The **Send sampling parameters (temperature/top_p)** option applies to `ai_task.generate_data`, including requests with image/PDF attachments and enabled tools. `ai_task.generate_image` uses the [Azure OpenAI Images API](https://learn.microsoft.com/azure/foundry/openai/how-to/dall-e#specify-api-options), which does not accept `temperature` or `top_p`; image generation and editing always omit both parameters, regardless of this setting.

## Authentication, endpoint, and model inventory

To change authentication or the API-key endpoint, or refresh Microsoft sign-in deployment discovery, click the integration entry's menu and select **Reconfigure**. Changing a service's own options does not rediscover the resource.

# Changelog

See the [changelog](https://github.com/joselcaguilar/azure-openai-ha/blob/main/CHANGELOG.md) for notable changes from 5.0.0 onward, including breaking changes and upgrade steps. Earlier versions are in the [release history](https://github.com/joselcaguilar/azure-openai-ha/releases).

# How to Help

While it'd be nice to have more developers, you can contribute without knowing how to code. You can [file bugs/feature requests](https://github.com/joselcaguilar/azure-openai-ha/issues), or you can help with other tasks like [UI Translations](#ui-translations) and updating the [README](./README.md).

## Getting Started (Developers)

1. Clone the repository and move into it.
2. Copy the environment template and set your GitHub token (required for HACS checks):
   - `cp .env.example .env`
   - set `GITHUB_TOKEN` in `.env` with read-only access to **Contents** and **Metadata**.
3. Run local checks using Docker:
   - `make lint` runs Ruff
   - `make hassfest` runs Home Assistant integration validation
   - `make hacs` runs HACS validation
   - `make test` runs all of the above
4. (Optional) Start Home Assistant locally for manual testing:
   - `docker compose up -d homeassistant`
   - Integration files are mounted from `./custom_components/azure_openai_conversation` into the container.

For the OAuth/discovery regression tests, create a Python 3.14 virtual environment, install `requirements-test.txt`, and run `python -m pytest -q`. Tests mock Microsoft authentication and Azure HTTP responses; they do not access your account or deploy Azure resources.

## UI Translations

More languages can be added [here](./custom_components/azure_openai_conversation/translations), contributions are welcome :)

The full UI is translated into Chinese (Traditional), Dutch, English, French, German, Polish, Portuguese, Slovak, and Spanish. Translation files use Home Assistant language codes (for example, `zh-Hant.json`, not `zh.json`), must contain the same keys as `en.json`, and must keep every `{placeholder}` unchanged; the tests enforce this.

## Documentation

The [README](./README.md) file will be used for Documentation, if it's expanded in the future with automations or other tweaks, we can think on a wiki for that purpose.

> **Disclaimer:** Don't worry about making mistakes as we can revert using the history 😊.

# Funding

|                                                                      GitHub                                                                       |                                                            Buy me a coffee                                                             |
| :-----------------------------------------------------------------------------------------------------------------------------------------------: | :------------------------------------------------------------------------------------------------------------------------------------: |
| <a href="https://github.com/sponsors/joselcaguilar"><img src="https://i.imgur.com/v2T6P4w.png" alt="GitHub Sponsor" width="100" height="100"></a> | [![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/joselcaguilar) |

# License

[MIT](LICENSE) - By providing a contribution, you agree the contribution is licensed under MIT.
