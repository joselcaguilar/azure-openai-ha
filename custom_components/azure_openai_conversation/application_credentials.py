"""Application credentials for Microsoft Entra ID account linking."""

from homeassistant.components.application_credentials import ClientCredential
from homeassistant.core import HomeAssistant

from .auth import EntraOAuth2Implementation


async def async_get_auth_implementation(
    hass: HomeAssistant, auth_domain: str, credential: ClientCredential
) -> EntraOAuth2Implementation:
    """Return the browser OAuth implementation for user-provided credentials."""
    return EntraOAuth2Implementation(
        hass,
        auth_domain,
        credential.client_id,
        credential.client_secret,
        credential.name,
    )


async def async_get_description_placeholders(hass: HomeAssistant) -> dict[str, str]:
    """Return documentation for registering the user's own OAuth application."""
    return {
        "console_url": "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
        "redirect_url": "https://my.home-assistant.io/redirect/oauth",
    }
