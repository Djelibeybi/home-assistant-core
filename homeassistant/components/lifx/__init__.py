"""Support for LIFX."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from lifx import LifxError, Light

from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    EVENT_HOMEASSISTANT_STARTED,
    Platform,
)
from homeassistant.core import CALLBACK_TYPE, Event, HassJob, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.event import (
    async_call_later,
    async_track_entity_registry_updated_event,
    async_track_time_interval,
)
from homeassistant.helpers.typing import ConfigType

from .const import (
    _LOGGER,
    CEILING_DOWNLIGHT_SUFFIX,
    CEILING_UPLIGHT_SUFFIX,
    CONF_SERIAL,
    DATA_LIFX_MANAGER,
    DEVICE_RETRIES,
    DEVICE_TIMEOUT,
    DOMAIN,
    LIFX_DEFAULT_PORT,
)
from .coordinator import LIFXConfigEntry, LifxLightState, LIFXUpdateCoordinator
from .discovery import async_discover_devices, async_trigger_discovery
from .manager import LIFXManager
from .migration import async_migrate_device_identifiers
from .util import normalize_serial

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LIGHT,
    Platform.SELECT,
    Platform.SENSOR,
]
DISCOVERY_INTERVAL = timedelta(minutes=15)

DISCOVERY_COOLDOWN = 5


class LIFXDiscoveryManager:
    """Manage discovery."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Init the manager."""
        self.hass = hass
        self.lock = asyncio.Lock()
        self._cancel_discovery: CALLBACK_TYPE | None = None

    @callback
    def async_setup_discovery_interval(self) -> None:
        """Set up discovery at an interval."""
        if self._cancel_discovery:
            self._cancel_discovery()
            self._cancel_discovery = None
        _LOGGER.debug(
            "Starting discovery with interval: %s",
            DISCOVERY_INTERVAL,
        )
        self._cancel_discovery = async_track_time_interval(
            self.hass,
            self.async_discovery,
            DISCOVERY_INTERVAL,
            cancel_on_shutdown=True,
        )

    async def async_discovery(self, *_: Any) -> None:
        """Discover LIFX devices."""
        async with self.lock:
            discovered = await async_discover_devices(self.hass)

            if discovered:
                async_trigger_discovery(self.hass, discovered)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the LIFX component."""
    discovery_manager = LIFXDiscoveryManager(hass)

    @callback
    def _async_delayed_discovery(now: datetime) -> None:
        """Start an untracked task to discover devices.

        We do not want the discovery task to block startup.
        """
        hass.async_create_background_task(
            discovery_manager.async_discovery(), "lifx-discovery"
        )

    # Let the system settle a bit before starting discovery
    # to reduce the risk we miss devices because the event
    # loop is blocked at startup.
    discovery_manager.async_setup_discovery_interval()
    async_call_later(
        hass,
        DISCOVERY_COOLDOWN,
        HassJob(_async_delayed_discovery, cancel_on_shutdown=True),
    )
    hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STARTED, discovery_manager.async_discovery
    )

    return True


async def async_migrate_entry(hass: HomeAssistant, entry: LIFXConfigEntry) -> bool:
    """Migrate old entry."""
    if entry.unique_id is None or entry.unique_id == DOMAIN:
        return True
    if entry.version == 1:
        # LIFX serials are hexadecimal numbers, not MAC addresses
        serial = normalize_serial(entry.unique_id or "")
        unique_id = serial
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_SERIAL: serial},
            unique_id=unique_id,
            version=2,
        )
        _LOGGER.debug("Migrated config entry %s to version 2", entry.entry_id)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: LIFXConfigEntry) -> bool:
    """Set up LIFX from a config entry."""
    if entry.unique_id is None or entry.unique_id == DOMAIN:
        _LOGGER.warning(
            "Legacy config entry %s is no longer supported; please remove it "
            "and rediscover your LIFX lights",
            entry.entry_id,
        )
        await hass.config_entries.async_remove(entry.entry_id)
        return False

    assert entry.unique_id is not None

    try:
        async with await Light.connect(
            ip=entry.data[CONF_HOST],
            port=entry.data.get(CONF_PORT, LIFX_DEFAULT_PORT),
            serial=normalize_serial(entry.data[CONF_SERIAL]),
            timeout=DEVICE_TIMEOUT,
            max_retries=DEVICE_RETRIES,
        ) as light:
            lifx_state = LifxLightState(state=light.state)
            light_type = type(light)

    except LifxError as err:
        raise ConfigEntryNotReady(
            f"Error configuring {entry.title} via {entry.data[CONF_HOST]}: {err}"
        ) from err
    except ExceptionGroup as eg:
        errors = eg.subgroup(LifxError)
        if errors is not None:
            raise ConfigEntryNotReady(
                f"Error configuring {entry.title} via {entry.data[CONF_HOST]}: "
                f"{[str(e) for e in errors.exceptions]}"
            ) from eg
        raise

    coordinator = LIFXUpdateCoordinator(hass, entry, lifx_state, light_type)
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        await coordinator.async_close()
        raise

    if coordinator.serial != entry.unique_id:
        await coordinator.async_close()
        raise ConfigEntryNotReady(
            f"Unexpected device found at {entry.data[CONF_HOST]};"
            f" expected {entry.unique_id}, found {coordinator.serial}"
        )

    entry.runtime_data = coordinator
    async_migrate_device_identifiers(hass, entry)

    if DATA_LIFX_MANAGER not in hass.data:
        manager = LIFXManager(hass)
        hass.data[DATA_LIFX_MANAGER] = manager
        manager.async_setup()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if coordinator.has_ceiling:
        _async_setup_ceiling_entity_sync(hass, entry)

    return True


def _async_setup_ceiling_entity_sync(
    hass: HomeAssistant, entry: LIFXConfigEntry
) -> None:
    """Set up synchronized enable/disable for ceiling uplight and downlight entities.

    When either the uplight or downlight entity is enabled or disabled,
    the other must be updated to match, as they cannot exist independently.
    """
    serial = normalize_serial(entry.data[CONF_SERIAL])
    uplight_unique_id = f"{serial}{CEILING_UPLIGHT_SUFFIX}"
    downlight_unique_id = f"{serial}{CEILING_DOWNLIGHT_SUFFIX}"

    entity_registry = er.async_get(hass)

    uplight_entity_id = entity_registry.async_get_entity_id(
        Platform.LIGHT, DOMAIN, uplight_unique_id
    )
    downlight_entity_id = entity_registry.async_get_entity_id(
        Platform.LIGHT, DOMAIN, downlight_unique_id
    )

    if uplight_entity_id is None or downlight_entity_id is None:
        _LOGGER.warning(
            "Could not find ceiling component entities for %s, sync disabled",
            serial,
        )
        return

    entity_pair = {
        uplight_entity_id: downlight_entity_id,
        downlight_entity_id: uplight_entity_id,
    }

    syncing = False

    @callback
    def _async_handle_registry_update(
        event: Event[er.EventEntityRegistryUpdatedData],
    ) -> None:
        """Handle entity registry updates to sync uplight/downlight enabled state."""
        nonlocal syncing

        if syncing:
            return

        data = event.data
        if data["action"] != "update":
            return

        changes = data.get("changes", {})
        if "disabled_by" not in changes:
            return

        entity_id = data["entity_id"]
        other_entity_id = entity_pair[entity_id]

        updated_entry = entity_registry.async_get(entity_id)
        other_entry = entity_registry.async_get(other_entity_id)
        if updated_entry is None or other_entry is None:
            return

        if other_entry.disabled_by != updated_entry.disabled_by:
            syncing = True
            try:
                entity_registry.async_update_entity(
                    other_entity_id, disabled_by=updated_entry.disabled_by
                )
                _LOGGER.debug(
                    "Synced %s disabled_by=%s to match %s",
                    other_entity_id,
                    updated_entry.disabled_by,
                    entity_id,
                )
            finally:
                syncing = False

    entry.async_on_unload(
        async_track_entity_registry_updated_event(
            hass,
            [uplight_entity_id, downlight_entity_id],
            _async_handle_registry_update,
        )
    )


async def async_unload_entry(hass: HomeAssistant, entry: LIFXConfigEntry) -> bool:
    """Unload a config entry."""
    if entry.unique_id is None or entry.unique_id == DOMAIN:
        return True
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_close()
    # Only the DATA_LIFX_MANAGER left, remove it.
    if len(hass.config_entries.async_loaded_entries(DOMAIN)) == 0:
        manager = hass.data.pop(DATA_LIFX_MANAGER)
        manager.async_unload()
    return unload_ok
