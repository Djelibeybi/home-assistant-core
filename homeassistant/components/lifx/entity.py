"""Base entity for the LIFX integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LIFXUpdateCoordinator


class LIFXEntity(CoordinatorEntity[LIFXUpdateCoordinator]):
    """Representation of a LIFX entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LIFXUpdateCoordinator) -> None:
        """Initialize a LIFX entity."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.serial)},
            connections={
                (CONNECTION_NETWORK_MAC, coordinator.mac_address),
            },
            serial_number=coordinator.serial,
            manufacturer="LIFX",
            model=coordinator.data.state.model,
            name=coordinator.label,
            sw_version=coordinator.data.sw_version,
            suggested_area=coordinator.data.group_name,
        )
