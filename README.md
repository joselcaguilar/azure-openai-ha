[![release][release-badge]][release-url]

[![Support the author on Patreon][patreon-shield]][patreon]

[![Buy me a coffee][buymeacoffee-shield]][buymeacoffee]

[patreon-shield]: https://frenck.dev/wp-content/uploads/2019/12/patreon.png
[patreon]: https://www.patreon.com/dutchdatadude

[buymeacoffee]: https://www.buymeacoffee.com/dutchdatadude
[buymeacoffee-shield]: https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png
[release-url]: https://github.com/jeroenterheerdt/azure-openai-ha/releases
[release-badge]: https://img.shields.io/github/v/release/jeroenterheerdt/azure-openai-ha?style=flat-square

<p align="center">
<img src="https://raw.githubusercontent.com/joselcaguilar/azure-openai-ha/main/.attachments/icon.png#gh-light-mode-only">
<img src="https://raw.githubusercontent.com/joselcaguilar/azure-openai-ha/main/.attachments/dark_icon.png#gh-dark-mode-only">
</p>

<h3 align="center">

[Azure OpenAI Conversation Custom Integration](https://github.com/jeroenterheerdt/azure-openai-ha) for Home Assistant
</h3>

# What This Is

This custom integration adds a conversation agent powered by [Azure OpenAI](https://azure.microsoft.com/products/cognitive-services/openai-service) in Home Assistant, it's based on the original [OpenAI Conversation integration](https://www.home-assistant.io/integrations/openai_conversation/) for Home Assistant.

# What It Does

This is equivalent to the built-in [OpenAI Conversation integration](https://www.home-assistant.io/integrations/openai_conversation/). The difference is that it uses the OpenAI algorithms available through Azure. Other than that the goal is to keep the differences to a minimum. You can use this conversation integration with Assistants in Home Assistant to control you house. They have all the capabilities the built-in OpenAI Conversation integration has.

# Limitations

- **Home Assistant versions** required: 2025.1.0 +

# Installation and Configuration
1. Download and install the integration from HACS by adding this repo as a custom repo and then installing Azure OpenAI Conversation. Notice that the [Azure OpenAI Conversation](https://my.home-assistant.io/redirect/hacs_repository/?owner=joselcaguilar&repository=azure-openai-ha&category=integration) integration available in HACS by default has not been updated for years and no longer works, so be sure to pick the right one.
2. Restart your Home Assistant instance
3. Go to [Settings -> Devices & Services -> Add Integration -> Azure OpenAI Conversation](https://my.home-assistant.io/redirect/config_flow_start/?domain=azure_openai_conversation)
4. Type your `API Key`, `API Base` and `API Version` used following the example below and hit submit:
> - API Key: 1234567890abcdef1234567890abcdef <br>
> - API Base: https://iotlabopenai.openai.azure.com/ <br>
> - API Version: 2023-03-15-preview <br>
5. Configure your assistant to use the Azure OpenAI Conversation.

#  Options

Options for Azure OpenAI Conversation can be set via the user interface, by taking the following steps:

1. Browse to your Home Assistant instance.
2. In the sidebar click on [Settings -> Devices & Services](https://my.home-assistant.io/redirect/integrations/).
3. FInd the Azure Open AI Conversation integration and click 'Options'

Options available (same as built-in OpenAI conversation):
- **Prompt:**
The starting text for the AI language model to generate new text from. This text can include information about your Home Assistant instance, devices, and areas and is written using [Home Assistant Templating](https://www.home-assistant.io/docs/configuration/templating).

- **Model:** The name of the GPT language model deployed for text generation (i.e.- `my-gpt35-model`). You can find more details on the available models in the [Azure OpenAI Documentation](https://learn.microsoft.com/azure/cognitive-services/openai/concepts/models#finding-what-models-are-available). If you are having issues using an assistant that uses this integration please check this model is the model you actually deployed.

- Maximum Tokens to Return in Response
The maximum number of words or "tokens" that the AI model should generate in its completion of the prompt. For more information, see the [Azure OpenAI Completion Documentation](https://learn.microsoft.com/azure/cognitive-services/openai/overview#tokens).

- **Temperature:** A value that determines the level of creativity and risk-taking the model should use when generating text. A higher temperature means the model is more likely to generate unexpected results, while a lower temperature results in more deterministic results. See the [Azure OpenAI Completion Documentation](https://learn.microsoft.com/azure/cognitive-services/openai/how-to/completions) for more information.

- **Top P:** An alternative to temperature, top_p determines the proportion of the most likely word choices the model should consider when generating text. A higher top_p means the model will only consider the most likely words, while a lower top_p means a wider range of words, including less likely ones, will be considered. For more information, see the [Azure OpenAI Completion Documentation](https://learn.microsoft.com/azure/cognitive-services/openai/how-to/completions).

# Changelog

Please reference the [release history](https://github.com/jeroenterheerdt/azure-openai-ha/releases).

# How to Help

While it'd be nice to have more developers, you can contribute without knowing how to code. You can [file bugs/feature requests](https://github.com/jeroenterheerdt/azure-openai-ha/issues), or you can help with other tasks like [UI Translations](#ui-translations) and updating the [README](./README.md).

## UI Translations

More languages can be added [here](./custom_components/azure_openai_conversation/translations), contributions are welcome :)

Languages available:
- English

## Documentation

The [README](./README.md) file will be used for Documentation, if it's expanded in the future with automations or other tweaks, we can think on a wiki for that purpose.

> **Disclaimer:** Don't worry about making mistakes as we can revert using the history 😊.

# License

[MIT](LICENSE) - By providing a contribution, you agree the contribution is licensed under MIT.
