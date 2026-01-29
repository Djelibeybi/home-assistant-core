"""Config flow for LIFX."""

from __future__ import annotations

from typing import Any

from lifx import (
    Device,
    LifxConnectionError,
    LifxDeviceNotFoundError,
    LifxTimeoutError,
    LifxUnsupportedCommandError,
)
import voluptuous as vol

from homeassistant.components import onboarding
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.helpers.typing import DiscoveryInfoType

from .const import (
    _LOGGER,
    CONF_SERIAL,
    DEVICE_RETRIES,
    DEVICE_TIMEOUT,
    DOMAIN,
    LIFX_DEFAULT_PORT,
)
from .util import mac_matches_serial, normalize_serial


class LIFXConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a LIFX config flow."""

    VERSION = 2

    _ip: str
    _port: int = LIFX_DEFAULT_PORT
    _serial: str
    _label: str = "LIFX Light"
    _group: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input.get(CONF_HOST, "")
            port: int = user_input.get(CONF_PORT, LIFX_DEFAULT_PORT)
            serial_input = user_input.get(CONF_SERIAL, "")
            serial = normalize_serial(serial_input) if serial_input else None
            if host:
                try:
                    return await self._async_try_connect(
                        host, port=port, serial=serial or None, raise_on_progress=False
                    )
                except LifxTimeoutError:
                    errors["base"] = "timeout_connect"
                except (LifxConnectionError, LifxDeviceNotFoundError):
                    errors["base"] = "cannot_connect"
                except LifxUnsupportedCommandError:
                    return self.async_abort(reason="invalid_device")
            else:
                return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_PORT): int,
                    vol.Optional(CONF_SERIAL): str,
                }
            ),
            errors=errors,
        )

    async def async_step_dhcp(
        self,
        discovery_info: DhcpServiceInfo,
    ) -> ConfigFlowResult:
        """Handle DHCP discovery."""
        mac = discovery_info.macaddress
        host = discovery_info.ip

        # Try to match this MAC against known serial numbers
        for entry in self._async_current_entries():
            if entry.unique_id and mac_matches_serial(mac, entry.unique_id):
                if entry.data.get(CONF_HOST) != host:
                    self.hass.config_entries.async_update_entry(
                        entry, data={**entry.data, CONF_HOST: host}
                    )
                    await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="already_configured")

        _LOGGER.debug("DHCP discovered LIFX device at %s (mac: %s)", host, mac)

        try:
            return await self._async_try_connect(host, raise_on_progress=True)
        except (
            LifxConnectionError,
            LifxDeviceNotFoundError,
            LifxTimeoutError,
        ):
            return self.async_abort(reason="cannot_connect")
        except LifxUnsupportedCommandError:
            return self.async_abort(reason="invalid_device")

    async def async_step_homekit(
        self,
        discovery_info: ZeroconfServiceInfo,
    ) -> ConfigFlowResult:
        """Handle HomeKit discovery."""
        host = discovery_info.host
        _LOGGER.debug("HomeKit discovered LIFX device at %s", host)
        try:
            return await self._async_try_connect(host, raise_on_progress=True)
        except (
            LifxConnectionError,
            LifxDeviceNotFoundError,
            LifxTimeoutError,
        ):
            return self.async_abort(reason="cannot_connect")
        except LifxUnsupportedCommandError:
            return self.async_abort(reason="invalid_device")

    async def async_step_zeroconf(
        self,
        discovery_info: ZeroconfServiceInfo,
    ) -> ConfigFlowResult:
        """Handle zeroconf discovery."""
        host = discovery_info.host
        serial: str = str(discovery_info.properties.get("id", ""))
        _LOGGER.debug(
            "Zeroconf discovered LIFX device at %s (serial: %s)", host, serial
        )
        try:
            return await self._async_try_connect(
                host, serial=serial or None, raise_on_progress=True
            )
        except (
            LifxConnectionError,
            LifxDeviceNotFoundError,
            LifxTimeoutError,
        ):
            return self.async_abort(reason="cannot_connect")
        except LifxUnsupportedCommandError:
            return self.async_abort(reason="invalid_device")

    async def async_step_integration_discovery(
        self,
        discovery_info: DiscoveryInfoType,
    ) -> ConfigFlowResult:
        """Handle integration discovery."""
        host: str = discovery_info[CONF_HOST]
        port: int = discovery_info[CONF_PORT]
        serial: str = discovery_info[CONF_SERIAL]
        try:
            return await self._async_try_connect(
                host,
                port=port,
                serial=serial,
                raise_on_progress=True,
                auto_confirm=True,
            )
        except (
            LifxConnectionError,
            LifxDeviceNotFoundError,
            LifxTimeoutError,
        ):
            return self.async_abort(reason="cannot_connect")
        except LifxUnsupportedCommandError:
            return self.async_abort(reason="invalid_device")

    async def async_step_discovery_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        if user_input is not None:
            return self._async_create_entry()

        self._set_confirm_only()
        placeholders = {"label": self._label, "group": self._group}
        self.context["title_placeholders"] = placeholders
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders=placeholders,
        )

    @callback
    def _async_create_entry(self) -> ConfigFlowResult:
        """Create the config entry."""
        return self.async_create_entry(
            title=self._label,
            data={
                CONF_HOST: self._ip,
                CONF_PORT: self._port,
                CONF_SERIAL: self._serial,
            },
        )

    async def _async_try_connect(
        self,
        host: str,
        port: int = LIFX_DEFAULT_PORT,
        serial: str | None = None,
        raise_on_progress: bool = True,
        auto_confirm: bool = False,
    ) -> ConfigFlowResult:
        """Try to connect to a LIFX device and set up the flow."""
        normalized_serial = normalize_serial(serial) if serial else None
        async with await Device.connect(
            ip=host,
            port=port,
            serial=normalized_serial,
            timeout=DEVICE_TIMEOUT,
            max_retries=DEVICE_RETRIES,
        ) as light:
            if type(light) is Device:
                # Only non-light devices would be a Device here
                return self.async_abort(reason="invalid_device")

            self._label = light.state.label
            self._ip = light.ip
            self._port: int = light.port
            self._serial = normalize_serial(light.serial)
            self._group = light.state.group_name

        await self.async_set_unique_id(
            self._serial, raise_on_progress=raise_on_progress
        )

        self._abort_if_unique_id_configured(
            updates={
                CONF_HOST: self._ip,
                CONF_PORT: self._port,
                CONF_SERIAL: self._serial,
            }
        )

        if auto_confirm or not onboarding.async_is_onboarded(self.hass):
            return self._async_create_entry()

        return await self.async_step_discovery_confirm()
