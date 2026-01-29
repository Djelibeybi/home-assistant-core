"""Migrate LIFX device and entity identifiers."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import _LOGGER, CONF_SERIAL, DOMAIN
from .coordinator import LIFXConfigEntry
from .util import normalize_serial


@callback
def async_migrate_device_identifiers(
    hass: HomeAssistant, entry: LIFXConfigEntry
) -> None:
    """Migrate device and entity identifiers from colon-formatted to raw hex.

    Old upstream code (aiolifx) stored device identifiers and entity unique_ids
    using colon-formatted serial numbers (e.g., "d0:73:d5:36:dc:03"). The new
    code (lifx-async) uses raw hex (e.g., "d073d536dc03"). Without this
    migration, both the device registry and entity registry end up with
    duplicates.
    """
    serial = normalize_serial(entry.data[CONF_SERIAL])
    if not serial:
        return
    formatted = dr.format_mac(serial)

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    # Look up by the old colon-formatted identifier
    old_device = device_registry.async_get_device(identifiers={(DOMAIN, formatted)})
    if old_device is None:
        # No old device; still migrate entity unique_ids if they exist
        _async_migrate_entity_unique_ids(entity_registry, entry, formatted, serial)
        return

    # Check if a different device with the raw hex identifier already exists
    new_device = device_registry.async_get_device(identifiers={(DOMAIN, serial)})
    if new_device is not None and new_device.id != old_device.id:
        # A separate device with the raw hex identifier was already created
        # (e.g., by entity setup on a previous run). Migrate entities first
        # (before removing the old device, which would auto-remove its entities).
        _async_migrate_entity_unique_ids(entity_registry, entry, formatted, serial)
        # Move preserved entities from the old device to the new device
        for reg_entity in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        ):
            if reg_entity.device_id == old_device.id:
                entity_registry.async_update_entity(
                    reg_entity.entity_id, device_id=new_device.id
                )
        _LOGGER.debug(
            "Removing stale device %s with old identifiers %s",
            old_device.id,
            old_device.identifiers,
        )
        device_registry.async_remove_device(old_device.id)
        return

    # Strip old MAC connections so the entity setup adds only the correct one.
    # The old aiolifx code computed the MAC from the serial (with a possible
    # off-by-one offset), while lifx-async reads the actual MAC from the device
    # state. Keeping the old connection would leave a stale duplicate.
    cleaned_connections = {
        (conn_type, value)
        for conn_type, value in old_device.connections
        if conn_type != dr.CONNECTION_NETWORK_MAC
    }
    _LOGGER.debug(
        "Migrating device identifiers from %s to {(%s, %s)}",
        old_device.identifiers,
        DOMAIN,
        serial,
    )
    device_registry.async_update_device(
        old_device.id,
        new_identifiers={(DOMAIN, serial)},
        new_connections=cleaned_connections,
    )
    _async_migrate_entity_unique_ids(entity_registry, entry, formatted, serial)


@callback
def _async_migrate_entity_unique_ids(
    entity_registry: er.EntityRegistry,
    entry: LIFXConfigEntry,
    old_serial: str,
    new_serial: str,
) -> None:
    """Migrate entity unique_ids from colon-formatted to raw hex serial."""
    for reg_entity in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if not reg_entity.unique_id.startswith(old_serial):
            continue
        new_unique_id = new_serial + reg_entity.unique_id[len(old_serial) :]
        existing = entity_registry.async_get_entity_id(
            reg_entity.domain, DOMAIN, new_unique_id
        )
        if existing is not None:
            # An entity with the new unique_id already exists (created by
            # a previous entity setup). Remove the duplicate and rename the
            # original to preserve its entity_id.
            _LOGGER.debug(
                "Removing duplicate entity %s in favor of %s (unique_id %s)",
                existing,
                reg_entity.entity_id,
                reg_entity.unique_id,
            )
            entity_registry.async_remove(existing)
        _LOGGER.debug(
            "Migrating entity unique_id from %s to %s",
            reg_entity.unique_id,
            new_unique_id,
        )
        entity_registry.async_update_entity(
            reg_entity.entity_id, new_unique_id=new_unique_id
        )
