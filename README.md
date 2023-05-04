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

This conversation agent is unable to control your house. It can only query information that has been provided by Home Assistant. To be able to answer questions about your house, Home Assistant will need to provide OpenAI with the details of your house, which include areas, devices and their states.

# Limitations

- Supported [Azure OpenAI API Versions](https://learn.microsoft.com/en-us/azure/cognitive-services/openai/reference#completions):
  - 2023-03-15-preview
  - 2022-12-01
- **Home Assistant versions** supported: Due to the breaking changes introduced by [Home Assistant Core](https://github.com/home-assistant/core/releases) for custom assistants, the Azure OpenAI Conversation integration is compatible with the following Home Assistant versions:
<center>

| Azure OpenAI Conversation Version | Home Assistant Version |
| --------------------------------- | ---------------------- |
| 0.x.y                             | 2023.4.x               |
| 1.x.y                             | 2023.5.x               |
</center>

## AI Models supported:

- gpt-35-turbo
- gpt-4
- gpt-4-32k

# Installation and Configuration

1. Ensure that the conversation integration is enabled, it allows you to converse with Home Assistant, add the line below to your `configuration.yaml`:
```yaml
conversation:
```
2. Download and install the integration from HACS: [Azure OpenAI Conversation](https://my.home-assistant.io/redirect/hacs_repository/?owner=joselcaguilar&repository=azure-openai-ha&category=integration)
3. Restart your Home Assistant instance
4. Go to Settings -> Devices & Services -> Add Integration
5. Search for `Azure OpenAI Conversation`
6. Type your `API Key`, `API Base` and `API Version` used following the example below and hit submit:
> - API Key: 1234567890abcdef1234567890abcdef <br>
> - API Base: https://iotlabopenai.openai.azure.com/ <br>
> - API Version: 2023-03-15-preview <br>

#  Options

Options for Azure OpenAI Conversation can be set via the user interface, by taking the following steps:

1. Browse to your Home Assistant instance.
2. In the sidebar click on Settings.
3. From the configuration menu select: Devices & Services.
4. If multiple instances of OpenAI Conversation are configured, choose the instance you want to configure.
Click on "Options".

Options available:
- **Prompt Template:**
The starting text for the AI language model to generate new text from. This text can include information about your Home Assistant instance, devices, and areas and is written using [Home Assistant Templating](https://www.home-assistant.io/docs/configuration/templating).

- **Completion Model:** The name of the GPT language model deployed for text generation (i.e.- `my-gpt35-model`). You can find more details on the available models in the [Azure OpenAI Documentation](https://learn.microsoft.com/en-us/azure/cognitive-services/openai/concepts/models#finding-what-models-are-available).

- Maximum Tokens to Return in Response
The maximum number of words or "tokens" that the AI model should generate in its completion of the prompt. For more information, see the [Azure OpenAI Completion Documentation](https://learn.microsoft.com/en-us/azure/cognitive-services/openai/overview#tokens).

- **Temperature:** A value that determines the level of creativity and risk-taking the model should use when generating text. A higher temperature means the model is more likely to generate unexpected results, while a lower temperature results in more deterministic results. See the [Azure OpenAI Completion Documentation](https://learn.microsoft.com/en-us/azure/cognitive-services/openai/how-to/completions) for more information.

- **Top P:** An alternative to temperature, top_p determines the proportion of the most likely word choices the model should consider when generating text. A higher top_p means the model will only consider the most likely words, while a lower top_p means a wider range of words, including less likely ones, will be considered. For more information, see the [Azure OpenAI Completion Documentation](https://learn.microsoft.com/en-us/azure/cognitive-services/openai/how-to/completions).

# Changelog

Please reference the [release history](https://github.com/joselcaguilar/azure-openai-ha/releases).

# How to Help

While it'd be nice to have more developers, you can contribute without knowing how to code. You can [file bugs/feature requests](https://github.com/joselcaguilar/azure-openai-ha/issues), or you can help with other tasks like [UI Translations](#ui-translations) and updating the [README](./README.md).

## UI Translations

More languages can be added [here](./custom_components/azure_openai_conversation/translations), contributions are welcome :)

Languages available:
- English
- Spanish
- Dutch (credits to: [@jobvk](https://github.com/jobvk))
- French (credits to: [@jobvk](https://github.com/jobvk))
- German (credits to: [@jobvk](https://github.com/jobvk))
- Portuguese (credits to: [@ViPeR5000](https://github.com/ViPeR5000))

## Documentation

The [README](./README.md) file will be used for Documentation, if it's expanded in the future with automations or other tweaks, we can think on a wiki for that purpose.

> **Disclaimer:** Don't worry about making mistakes as we can revert using the history 😊.

# Funding

|                                                                       GitHub                                                                       |                                                            Buy me a coffee                                                             |
| :------------------------------------------------------------------------------------------------------------------------------------------------: | :------------------------------------------------------------------------------------------------------------------------------------: |
| <a href="https://github.com/sponsors/joselcaguilar"><img src="https://i.imgur.com/v2T6P4w.png"  alt="GitHub Sponsor" width="100" height="100"></a> | [![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/joselcaguilar) |

# License

[MIT](LICENSE) - By providing a contribution, you agree the contribution is licensed under MIT.