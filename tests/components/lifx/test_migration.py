"""Tests for LIFX identifier migration."""

from __future__ import annotations

from homeassistant.components.lifx import DOMAIN
from homeassistant.components.lifx.const import CONF_SERIAL
from homeassistant.components.lifx.migration import async_migrate_device_identifiers
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import IP_ADDRESS, LABEL, MAC_ADDRESS, SERIAL_FORMATTED, SERIAL_RAW

from tests.common import MockConfigEntry


async def test_migrate_device_identifiers_colon_to_raw_hex(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test device identifiers and entity unique_ids are migrated."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL_RAW},
        unique_id=SERIAL_RAW,
        version=2,
    )
    entry.add_to_hass(hass)

    # Simulate a device created by old upstream code with colon-formatted identifier
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, SERIAL_FORMATTED)},
        connections={(dr.CONNECTION_NETWORK_MAC, MAC_ADDRESS)},
        name=LABEL,
    )
    assert device.identifiers == {(DOMAIN, SERIAL_FORMATTED)}

    # Simulate entities created by old upstream code with colon-formatted unique_ids
    light_entity = entity_registry.async_get_or_create(
        config_entry=entry,
        platform=DOMAIN,
        domain="light",
        unique_id=SERIAL_FORMATTED,
        device_id=device.id,
    )
    sensor_entity = entity_registry.async_get_or_create(
        config_entry=entry,
        platform=DOMAIN,
        domain="sensor",
        unique_id=f"{SERIAL_FORMATTED}_rssi",
        device_id=device.id,
    )

    async_migrate_device_identifiers(hass, entry)

    updated_device = device_registry.async_get(device.id)
    assert updated_device.identifiers == {(DOMAIN, SERIAL_RAW)}

    # Old MAC connection should be removed so entity setup adds the correct one
    assert updated_device.connections == set()

    # Entity unique_ids should be migrated to raw hex
    updated_light = entity_registry.async_get(light_entity.entity_id)
    assert updated_light.unique_id == SERIAL_RAW
    updated_sensor = entity_registry.async_get(sensor_entity.entity_id)
    assert updated_sensor.unique_id == f"{SERIAL_RAW}_rssi"


async def test_migrate_device_identifiers_already_raw_hex(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test no-op when device already has raw hex identifiers."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL_RAW},
        unique_id=SERIAL_RAW,
        version=2,
    )
    entry.add_to_hass(hass)

    # Device already has raw hex identifier (no migration needed)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, SERIAL_RAW)},
        connections={(dr.CONNECTION_NETWORK_MAC, MAC_ADDRESS)},
        name=LABEL,
    )
    assert device.identifiers == {(DOMAIN, SERIAL_RAW)}

    async_migrate_device_identifiers(hass, entry)

    updated_device = device_registry.async_get(device.id)
    assert updated_device.identifiers == {(DOMAIN, SERIAL_RAW)}


async def test_migrate_device_identifiers_empty_serial(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test migration returns early when serial is empty."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: ""},
        unique_id=SERIAL_RAW,
        version=2,
    )
    entry.add_to_hass(hass)

    async_migrate_device_identifiers(hass, entry)

    assert len(device_registry.devices) == 0


async def test_migrate_device_identifiers_both_formats(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test migration when device has both colon and raw hex identifiers."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL_RAW},
        unique_id=SERIAL_RAW,
        version=2,
    )
    entry.add_to_hass(hass)

    # Device has both formats (as seen in the real device registry)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, SERIAL_FORMATTED), (DOMAIN, SERIAL_RAW)},
        connections={(dr.CONNECTION_NETWORK_MAC, MAC_ADDRESS)},
        name=LABEL,
    )
    assert len(device.identifiers) == 2

    # Both lookups return the same device, so it's updated (not removed)
    async_migrate_device_identifiers(hass, entry)

    updated_device = device_registry.async_get(device.id)
    assert updated_device.identifiers == {(DOMAIN, SERIAL_RAW)}

    # Old MAC connection should be removed so entity setup adds the correct one
    assert updated_device.connections == set()


async def test_migrate_device_identifiers_collision(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test migration when two separate devices and entities exist."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL_RAW},
        unique_id=SERIAL_RAW,
        version=2,
    )
    entry.add_to_hass(hass)

    # Old device with colon-formatted identifier (from upstream aiolifx)
    old_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, SERIAL_FORMATTED)},
        connections={(dr.CONNECTION_NETWORK_MAC, MAC_ADDRESS)},
        name=LABEL,
    )

    # New device with raw hex identifier (created by new entity setup)
    new_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, SERIAL_RAW)},
        name=LABEL,
    )
    assert old_device.id != new_device.id

    # Old entity with colon-formatted unique_id
    old_entity = entity_registry.async_get_or_create(
        config_entry=entry,
        platform=DOMAIN,
        domain="light",
        unique_id=SERIAL_FORMATTED,
        device_id=old_device.id,
    )

    # New entity with raw hex unique_id
    new_entity = entity_registry.async_get_or_create(
        config_entry=entry,
        platform=DOMAIN,
        domain="light",
        unique_id=SERIAL_RAW,
        device_id=new_device.id,
    )

    async_migrate_device_identifiers(hass, entry)

    updated_device = device_registry.async_get(old_device.id)
    assert updated_device is None

    updated_light = entity_registry.async_get(old_entity.entity_id)
    assert updated_light.unique_id == SERIAL_RAW

    duplicate_light = entity_registry.async_get(new_entity.entity_id)
    assert duplicate_light is None
