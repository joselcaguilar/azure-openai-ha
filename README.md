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
2. To enable conversations and AI tasks, [deploy a chat completion model](http://learn.microsoft.com/en-us/azure/ai-foundry/foundry-models/how-to/deploy-foundry-models?view=foundry&preserve-view=true#deploy-a-model) (such as `gpt-4o-mini`, `gpt-4.1-mini` or `gpt-5-mini`)  
   *If your deployment is not named `gpt-4o-mini`, disable **Recommended model settings** and enter your deployment name as the model (see [Options](#options)). Name the deployment after the model, for example `gpt-5-mini`, so the model specific options are shown.*
3. Optionally deploy more models:
   - An image model such as `gpt-image-2.5-flare`, `gpt-image-2` or `gpt-image-1` to generate images with AI tasks.
   - `gpt-4o-mini-transcribe`, `gpt-4o-transcribe` or `whisper` for speech-to-text.
   - `gpt-4o-mini-tts`, `tts-1` or `tts-1-hd` for text-to-speech.

## Setting Up the Integration

4. Download and install the integration from HACS: [Azure OpenAI Conversation](https://my.home-assistant.io/redirect/hacs_repository/?owner=joselcaguilar&repository=azure-openai-ha&category=integration).
5. Restart your Home Assistant instance.
6. [Click here](https://my.home-assistant.io/redirect/config_flow_start/?domain=azure_openai_conversation) or go to **Settings → Devices & Services → Add Integration → Azure OpenAI Conversation**.
7. Enter your `API Key` and `API Base URL` (use the format `https://your-resource.services.ai.azure.com/`) and hit **Submit**.
8. A conversation agent and an AI task are created for you. Configure your assistant to use the Azure OpenAI Conversation agent.
9. To add more conversation agents or AI tasks, or the speech-to-text and text-to-speech services, use the **Add** buttons on the integration page.

Configurations created with versions before 5.0 are migrated automatically: the existing agent keeps its options and an AI task using the same deployment is added.

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

- **Send sampling parameters (temperature/top_p):** Enabled by default for each conversation agent and AI task. Disable **Recommended model settings** to access this option in **Additional settings**, then turn it off for newer models that reject `top_p` or `temperature`. When disabled, both parameters are omitted from the first request, regardless of the deployment name or reasoning effort. Your Temperature and Top P values remain saved and are used again if you re-enable this option for a model that supports them.

- **Temperature:** A value that determines the level of creativity and risk-taking the model should use when generating text. A higher temperature means the model is more likely to generate unexpected results, while a lower temperature results in more deterministic results. See the [Azure OpenAI Completion Documentation](https://learn.microsoft.com/azure/cognitive-services/openai/how-to/completions) for more information.

- **Top P:** An alternative to temperature, top_p determines the proportion of the most likely word choices the model should consider when generating text. A higher top_p means the model will only consider the most likely words, while a lower top_p means a wider range of words, including less likely ones, will be considered. For more information, see the [Azure OpenAI Completion Documentation](https://learn.microsoft.com/azure/cognitive-services/openai/how-to/completions).

- **Store requests and responses:** Keep responses in Azure OpenAI so they can be retrieved later.

Depending on the deployment name, more options are shown:
- **Reasoning effort**, **Reasoning summary**, **Verbosity** and **Pro mode** for reasoning models such as o-series, GPT-5 and GPT-6.
- **Web search:** Lets the model search the web with [Grounding with Bing Search](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/web-search), which has additional costs.
- **Code interpreter:** Lets the model run Python code in a [container](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/responses), billed per session.
- **Image model deployment** (AI tasks only): The deployment used by `ai_task.generate_image`, `gpt-image-2.5-flare` by default.

If a deployment rejects an optional parameter, such as temperature for reasoning models, the request is retried without it.

Speech-to-text and text-to-speech services let you choose the model deployment and instructions to improve the transcripts or control the voice, and the speed for text-to-speech.

## AI tasks

Use the [`ai_task.generate_data`](https://www.home-assistant.io/integrations/ai_task/) action to generate text or structured data, with image or PDF attachments, and `ai_task.generate_image` to generate or edit images. They replace the `azure_openai_conversation.generate_content` and `azure_openai_conversation.generate_image` actions, which were removed in 5.0.

The **Send sampling parameters (temperature/top_p)** option applies to `ai_task.generate_data`, including requests with image/PDF attachments and enabled tools. `ai_task.generate_image` uses the [Azure OpenAI Images API](https://learn.microsoft.com/azure/foundry/openai/how-to/dall-e#specify-api-options), which does not accept `temperature` or `top_p`; image generation and editing always omit both parameters, regardless of this setting.

## Endpoint and API key

To change the API Base URL or the API key, click the ⋮ menu of the integration entry and select **Reconfigure**.

# Changelog

Please reference the [release history](https://github.com/joselcaguilar/azure-openai-ha/releases).

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

## UI Translations

More languages can be added [here](./custom_components/azure_openai_conversation/translations), contributions are welcome :)

Translations are available for Chinese (Traditional), Dutch, English, French, German, Polish, Portuguese, Slovak, and Spanish. The sampling-option label and help text are translated for all of these languages; other UI text may fall back to English.

## Documentation

The [README](./README.md) file will be used for Documentation, if it's expanded in the future with automations or other tweaks, we can think on a wiki for that purpose.

> **Disclaimer:** Don't worry about making mistakes as we can revert using the history 😊.

# Funding

|                                                                      GitHub                                                                       |                                                            Buy me a coffee                                                             |
| :-----------------------------------------------------------------------------------------------------------------------------------------------: | :------------------------------------------------------------------------------------------------------------------------------------: |
| <a href="https://github.com/sponsors/joselcaguilar"><img src="https://i.imgur.com/v2T6P4w.png" alt="GitHub Sponsor" width="100" height="100"></a> | [![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/joselcaguilar) |

# License

[MIT](LICENSE) - By providing a contribution, you agree the contribution is licensed under MIT.
