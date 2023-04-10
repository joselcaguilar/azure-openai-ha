[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![GitHub all releases](https://img.shields.io/github/downloads/joselcaguilar/azure-openai-ha/total)
[![BuyMeACoffee](https://img.shields.io/badge/-Buy_me_a%C2%A0coffee-gray?logo=buy-me-a-coffee)](https://www.buymeacoffee.com/joselcaguilar)

[Azure OpenAI Conversation Custom Integration](https://github.com/joselcaguilar/azure-openai-ha) for Home Assistant

# What This Is:

This custom integration adds a conversation agent powered by [Azure OpenAI](https://azure.microsoft.com/products/cognitive-services/openai-service) in Home Assistant, it's based on the original [OpenAI Conversation integration](https://www.home-assistant.io/integrations/openai_conversation/) for Home Assistant.

# What It Does:

This conversation agent is unable to control your house. It can only query information that has been provided by Home Assistant. To be able to answer questions about your house, Home Assistant will need to provide OpenAI with the details of your house, which include areas, devices and their states.

# Limitations

- Home Assistant 2023.4.0+ is required
- Supported [Azure OpenAI API Versions](https://learn.microsoft.com/en-us/azure/cognitive-services/openai/reference#completions):
  - 2023-03-15-preview
  - 2022-12-01

## AI Models supported:

- gpt-35-turbo
- gpt-4
- gpt-4-32k

# Installation and Configuration via HACS

1. Ensure that the conversation integration is enabled, it allows you to converse with Home Assistant, add the line below to your `configuration.yaml`:
```yaml
conversation:
```
2. Go to HACS -> Integrations
3. Add [this](https://github.com/joselcaguilar/azure-openai-ha) repo into your HACS custom repositories
4. Search for `Azure OpenAI Conversation` and download it
5. Restart your Home Assistant instance
6. Go to Settings -> Devices & Services -> Add Integration
7. Search for `Azure OpenAI Conversation`
8. Type your `API Key`, `API Base` and `API Version` used following the example below and hit submit:
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
The starting text for the AI language model to generate new text from. This text can include information about your Home Assistant instance, devices, and areas and is written using Home Assistant Templating.

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

## Documentation

The [README](./README.md) file will be used for Documentation, if it's expanded in the future with automations or other tweaks, we can think on a wiki for that purpose.

> **Disclaimer:** Don't worry about making mistakes as we can revert using the history 😊.

# License

[MIT](LICENSE) - By providing a contribution, you agree the contribution is licensed under MIT.

# Buy me a coffee

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/joselcaguilar)