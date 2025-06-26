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

This custom integration adds a conversation agent powered by [Azure OpenAI](https://azure.microsoft.com/products/cognitive-services/openai-service) in Home Assistant, it's based on the original [OpenAI Conversation integration](https://www.home-assistant.io/integrations/openai_conversation/) for Home Assistant.

# What It Does

This is equivalent to the built-in [OpenAI Conversation integration](https://www.home-assistant.io/integrations/openai_conversation/). The difference is that it uses the OpenAI algorithms available through Azure. Other than that the goal is to keep the differences to a minimum. You can use this conversation integration with Assistants in Home Assistant to control you house. They have all the capabilities the built-in OpenAI Conversation integration has.

# Limitations

<center>

| Azure OpenAI Conversation Version | Home Assistant Version | Minimal API Version |
| --------------------------------- | ---------------------- | ------------------- |
| 0.x.y                             | 2023.4.x               | 2023-06-01-preview  |
| 1.x.y                             | 2023.5+                | 2023-06-01-preview  |
| 2.x.y                             | 2025.1                 | 2023-12-01-preview  |
| 3.x.y                             | 2025.6                 | 2025-03-01-preview  |

</center>


# Installation and Configuration

1. Download and install the integration from HACS: [Azure OpenAI Conversation](https://my.home-assistant.io/redirect/hacs_repository/?owner=joselcaguilar&repository=azure-openai-ha&category=integration).
2. Restart your Home Assistant instance
3. Go to [Settings -> Devices & Services -> Add Integration -> Azure OpenAI Conversation](https://my.home-assistant.io/redirect/config_flow_start/?domain=azure_openai_conversation)
4.  To have a conversation, made sure to deploy a chat completion model (like gpt-4o-mini or gpt-4.1-mini) in Azure. 
5. If you want to generate images using the available `generate_image` service, make sure to deploy the `dall-e-3` model as well.
5. Type your `API Key`, `API Base` and `API Version` (API version must be no less than 2025-03-01-preview, use the latest available version) used following the example below and hit submit:
> - API Key: 1234567890abcdef1234567890abcdef <br>
> - API Base: https://your-resource.openai.azure.com/ <br>
> - API Version: 2025-03-01-preview <br>
6. Configure your assistant to use the Azure OpenAI Conversation.

#  Options

Options for Azure OpenAI Conversation can be set via the user interface, by taking the following steps:

1. Browse to your Home Assistant instance.
2. In the sidebar click on [Settings -> Devices & Services](https://my.home-assistant.io/redirect/integrations/).
3. Find the Azure Open AI Conversation integration and click 'Configure'

Options available (same as built-in OpenAI conversation):
- **Instructions:**
The starting text for the AI language model to generate new text from. This text can include information about your Home Assistant instance, devices, and areas and is written using [Home Assistant Templating](https://www.home-assistant.io/docs/configuration/templating).

- **Model:** The name of the GPT language model deployed for text generation (i.e.- `my-gpt35-model`). You can find more details on the available models in the [Azure OpenAI Documentation](https://learn.microsoft.com/azure/cognitive-services/openai/concepts/models#finding-what-models-are-available). If you are having issues using an assistant that uses this integration please check this model is the model you actually deployed.

- **Maximum Tokens to Return in Response**
The maximum number of words or "tokens" that the AI model should generate in its completion of the prompt. For more information, see the [Azure OpenAI Completion Documentation](https://learn.microsoft.com/azure/cognitive-services/openai/overview#tokens).

- **Temperature:** A value that determines the level of creativity and risk-taking the model should use when generating text. A higher temperature means the model is more likely to generate unexpected results, while a lower temperature results in more deterministic results. See the [Azure OpenAI Completion Documentation](https://learn.microsoft.com/azure/cognitive-services/openai/how-to/completions) for more information.

- **Top P:** An alternative to temperature, top_p determines the proportion of the most likely word choices the model should consider when generating text. A higher top_p means the model will only consider the most likely words, while a lower top_p means a wider range of words, including less likely ones, will be considered. For more information, see the [Azure OpenAI Completion Documentation](https://learn.microsoft.com/azure/cognitive-services/openai/how-to/completions).

## API Version change

This value couldn't be changed through options, to update it you must need to delete and recreate the integration. Make sure that you have all required values like API key saved before recreation.

# Changelog

Please reference the [release history](https://github.com/joselcaguilar/azure-openai-ha/releases).

# How to Help

While it'd be nice to have more developers, you can contribute without knowing how to code. You can [file bugs/feature requests](https://github.com/joselcaguilar/azure-openai-ha/issues), or you can help with other tasks like [UI Translations](#ui-translations) and updating the [README](./README.md).

## UI Translations

More languages can be added [here](./custom_components/azure_openai_conversation/translations), contributions are welcome :)

Languages available:
- English

## Documentation

The [README](./README.md) file will be used for Documentation, if it's expanded in the future with automations or other tweaks, we can think on a wiki for that purpose.

> **Disclaimer:** Don't worry about making mistakes as we can revert using the history 😊.

# Funding

|                                                                      GitHub                                                                       |                                                            Buy me a coffee                                                             |
| :-----------------------------------------------------------------------------------------------------------------------------------------------: | :------------------------------------------------------------------------------------------------------------------------------------: |
| <a href="https://github.com/sponsors/joselcaguilar"><img src="https://i.imgur.com/v2T6P4w.png" alt="GitHub Sponsor" width="100" height="100"></a> | [![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/joselcaguilar) |

# License

[MIT](LICENSE) - By providing a contribution, you agree the contribution is licensed under MIT.
