"""Microsoft Entra ID browser authentication using Home Assistant OAuth2."""

from __future__ import annotations

from typing import Any, override
from uuid import UUID

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import OAuth2TokenRequestConnectionError
from homeassistant.helpers import config_entry_oauth2_flow

from .const import CONF_TENANT_ID, DOMAIN, INFERENCE_SCOPE, MANAGEMENT_SCOPE


class EntraOAuth2Implementation(
    config_entry_oauth2_flow.LocalOAuth2ImplementationWithPkce
):
    """Keep an inference token and request management tokens only for discovery."""

    def __init__(
        self,
        hass: HomeAssistant,
        auth_domain: str,
        client_id: str,
        client_secret: str,
        name: str | None = None,
        tenant_id: str = "organizations",
    ) -> None:
        """Initialize a tenant-specific authorization code flow with PKCE."""
        if tenant_id != "organizations":
            tenant_id = str(UUID(tenant_id))
        authority = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0"
        super().__init__(
            hass,
            auth_domain,
            client_id,
            authorize_url=f"{authority}/authorize",
            token_url=f"{authority}/token",
            client_secret=client_secret,
        )
        self._name = name

    @property
    @override
    def name(self) -> str:
        """Return the application credential's display name."""
        return self._name or self.client_id

    @property
    @override
    def service_domain(self) -> str:
        """Return the integration served by these application credentials."""
        return DOMAIN

    def with_tenant(self, tenant_id: str) -> EntraOAuth2Implementation:
        """Create an independent PKCE implementation for a config flow or entry."""
        return EntraOAuth2Implementation(
            self.hass,
            self.domain,
            self.client_id,
            self.client_secret,
            self._name,
            tenant_id,
        )

    @property
    @override
    def extra_authorize_data(self) -> dict[str, Any]:
        """Request consent for both APIs without requesting Graph permissions."""
        return {
            **super().extra_authorize_data,
            # Static consent covers both APIs registered on the application.
            "scope": f"offline_access {INFERENCE_SCOPE}",
            "prompt": "consent",
        }

    @property
    @override
    def extra_token_resolve_data(self) -> dict[str, Any]:
        """Redeem the authorization code for an inference token only."""
        return {
            **super().extra_token_resolve_data,
            "scope": f"offline_access {INFERENCE_SCOPE}",
        }

    @override
    async def async_resolve_external_data(self, external_data: Any) -> dict[str, Any]:
        """Reject incomplete responses before Home Assistant logs or stores them."""
        token = await super().async_resolve_external_data(external_data)
        self._validate_token(token)
        self._validate_refresh_token(token.get("refresh_token"))
        return token

    @override
    async def _token_request(self, data: dict[str, Any]) -> dict[str, Any]:
        """Map malformed token payloads to Home Assistant's recoverable OAuth error."""
        try:
            token = await super()._token_request(data)
        except ValueError as err:
            raise OAuth2TokenRequestConnectionError(domain=DOMAIN) from err
        if not isinstance(token, dict):
            raise OAuth2TokenRequestConnectionError(domain=DOMAIN)
        return token

    @override
    async def _async_refresh_token(self, token: dict[str, Any]) -> dict[str, Any]:
        """Refresh the inference token, preserving the latest rotated refresh token."""
        refreshed = await self._async_redeem_refresh_token(token, INFERENCE_SCOPE)
        token = {**token, **refreshed}
        self._validate_refresh_token(token["refresh_token"])
        return token

    async def async_get_management_token(self, token: dict[str, Any]) -> str:
        """Acquire a short-lived Azure Resource Manager token that is never stored."""
        management = await self._async_redeem_refresh_token(token, MANAGEMENT_SCOPE)
        return management["access_token"]

    async def _async_redeem_refresh_token(
        self, token: dict[str, Any], scope: str
    ) -> dict[str, Any]:
        """Exchange the refresh token for a validated access token for one API."""
        self._validate_refresh_token(token.get("refresh_token"))
        response = await self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"],
                "scope": scope,
            }
        )
        self._validate_token(response)
        return response

    @staticmethod
    def _validate_refresh_token(token: Any) -> None:
        """Reject absent or malformed refresh tokens before a token exchange."""
        if not isinstance(token, str) or not token:
            raise OAuth2TokenRequestConnectionError(domain=DOMAIN)

    @staticmethod
    def _validate_token(token: dict[str, Any]) -> None:
        """Reject incomplete token responses instead of extending a stale token."""
        try:
            expires_in = int(token["expires_in"])
        except (KeyError, OverflowError, TypeError, ValueError) as err:
            raise OAuth2TokenRequestConnectionError(domain=DOMAIN) from err
        if not isinstance(token.get("access_token"), str) or not token["access_token"]:
            raise OAuth2TokenRequestConnectionError(domain=DOMAIN)
        if expires_in <= 0:
            raise OAuth2TokenRequestConnectionError(domain=DOMAIN)


async def async_get_oauth_implementation(
    hass: HomeAssistant, entry: ConfigEntry
) -> EntraOAuth2Implementation:
    """Resolve application credentials and bind them to the entry's tenant."""
    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    )
    if not isinstance(implementation, EntraOAuth2Implementation):
        raise config_entry_oauth2_flow.UnknownImplementationError
    return implementation.with_tenant(entry.data[CONF_TENANT_ID])
