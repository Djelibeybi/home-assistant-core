"""Tests for the LIFX integration."""

import asyncio
from collections.abc import AsyncGenerator
import itertools
import socket
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components.lifx.const import CONF_SERIAL, LIFX_DEFAULT_PORT
from homeassistant.const import CONF_HOST, CONF_PORT

from . import _patch_discovery

try:
    from lifx_emulator import (
        EmulatedLifxServer,
        create_color_light,
        create_color_temperature_light,
        create_hev_light,
        create_infrared_light,
        create_multizone_light,
        create_tile_device,
    )
    from lifx_emulator.devices import DeviceManager
    from lifx_emulator.repositories import DeviceRepository

    EMULATOR_AVAILABLE = True

except ImportError:
    EMULATOR_AVAILABLE = False


def pytest_configure(config: pytest.Config) -> None:
    """Add emulator marker."""
    config.addinivalue_line(
        "markers",
        "emulator: marks tests that use lifx-emulator (excluded from CI by default)",
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add --emulator option to include emulator tests."""

    parser.addoption(
        "--emulator",
        action="store_true",
        default=False,
        help="Include emulator tests (excluded by default)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Deselect emulator tests unless --emulator is passed."""

    mock_tests: list[pytest.Item] = []
    emulator_tests: list[pytest.Item] = []

    for item in items:
        if item.get_closest_marker("emulator"):
            emulator_tests.append(item)
        else:
            mock_tests.append(item)

    if EMULATOR_AVAILABLE and config.getoption("--emulator", default=False):
        config.hook.pytest_deselected(items=mock_tests)
        items[:] = emulator_tests
        return

    config.hook.pytest_deselected(items=emulator_tests)
    items[:] = mock_tests


@pytest.fixture
def mock_discovery():
    """Mock discovery."""
    with _patch_discovery():
        yield


@pytest.fixture
def mock_effect_conductor():
    """Mock the effect conductor."""
    mock_conductor = MagicMock()
    mock_conductor.start = AsyncMock()
    mock_conductor.stop = AsyncMock()
    mock_conductor.effect = MagicMock(return_value=None)

    with patch(
        "homeassistant.components.lifx.manager.Conductor",
        return_value=mock_conductor,
    ):
        yield mock_conductor


@pytest.fixture(autouse=True)
def lifx_mock_async_get_ipv4_broadcast_addresses(request: pytest.FixtureRequest):
    """Mock network util's async_get_ipv4_broadcast_addresses.

    For emulator tests, use 127.0.0.1 to discover only the local emulator.
    For other tests, use 255.255.255.255 (won't discover anything with mocked devices).
    """
    # Check if this is an emulator test
    is_emulator_test = "emulator" in [
        marker.name for marker in request.node.iter_markers()
    ]

    broadcast_addr = ["127.0.0.1"] if is_emulator_test else ["255.255.255.255"]

    with patch(
        "homeassistant.components.network.async_get_ipv4_broadcast_addresses",
        return_value=broadcast_addr,
    ):
        yield


# Emulator-specific fixtures for protocol-level integration tests

# Counter for generating unique device serials per test
_device_counter = itertools.count(1)


def _get_free_port() -> int:
    """Get a free UDP port.

    Follows the pattern from lifx-async tests for port allocation.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def emulator_server(socket_enabled: None) -> AsyncGenerator:
    """Create in-process emulator server with all device types.

    Uses lifx-emulator to create an emulated LIFX network in the same
    process, treating it like a set of physical bulbs for integration testing.
    """
    # Create device pool (10 of each type)
    devices = []

    # Color bulbs (serials 1-10)
    for i in range(1, 11):
        serial = f"d073d500{i:04x}"
        devices.append(create_color_light(serial=serial))

    # White bulbs (serials 11-20)
    for i in range(11, 21):
        serial = f"d073d500{i:04x}"
        devices.append(create_color_temperature_light(serial=serial))

    # Infrared bulbs (serials 21-30)
    for i in range(21, 31):
        serial = f"d073d500{i:04x}"
        devices.append(create_infrared_light(serial=serial))

    # HEV bulbs (serials 31-40)
    for i in range(31, 41):
        serial = f"d073d500{i:04x}"
        devices.append(create_hev_light(serial=serial))

    # Multizone (serials 41-50)
    for i in range(41, 51):
        serial = f"d073d500{i:04x}"
        devices.append(create_multizone_light(serial=serial))

    # Tiles (serials 51-60)
    for i in range(51, 61):
        serial = f"d073d500{i:04x}"
        devices.append(create_tile_device(serial=serial))

    # Create device manager and server
    device_manager = DeviceManager(DeviceRepository())
    server = EmulatedLifxServer(
        devices=devices,
        device_manager=device_manager,
        bind_address="127.0.0.1",
        port=LIFX_DEFAULT_PORT,
    )

    await server.start()
    await asyncio.sleep(0.1)  # Give server time to bind

    try:
        yield server
    finally:
        await server.stop()
        await asyncio.sleep(0.1)  # Give server time to clean up


def _make_config(serial: str, port: int) -> dict[str, Any]:
    """Build config entry data for an emulated device."""
    return {
        CONF_HOST: "127.0.0.1",
        CONF_PORT: port,
        CONF_SERIAL: serial,
    }


@pytest.fixture
def emulator_device_config(emulator_server) -> dict[str, Any]:
    """Return config entry data for an emulated color bulb."""
    device_num = (next(_device_counter) % 10) + 1
    serial = f"d073d500{device_num:04x}"
    return _make_config(serial, emulator_server.port)


@pytest.fixture
def emulator_white_config(emulator_server) -> dict[str, Any]:
    """Return config entry data for an emulated white bulb."""
    device_num = (next(_device_counter) % 10) + 11
    serial = f"d073d500{device_num:04x}"
    return _make_config(serial, emulator_server.port)


@pytest.fixture
def emulator_infrared_config(emulator_server) -> dict[str, Any]:
    """Return config entry data for an emulated infrared bulb."""
    device_num = (next(_device_counter) % 10) + 21
    serial = f"d073d500{device_num:04x}"
    return _make_config(serial, emulator_server.port)


@pytest.fixture
def emulator_hev_config(emulator_server) -> dict[str, Any]:
    """Return config entry data for an emulated HEV bulb."""
    device_num = (next(_device_counter) % 10) + 31
    serial = f"d073d500{device_num:04x}"
    return _make_config(serial, emulator_server.port)


@pytest.fixture
def emulator_multizone_config(emulator_server) -> dict[str, Any]:
    """Return config entry data for an emulated multizone strip."""
    device_num = (next(_device_counter) % 10) + 41
    serial = f"d073d500{device_num:04x}"
    return _make_config(serial, emulator_server.port)


@pytest.fixture
def emulator_tile_config(emulator_server) -> dict[str, Any]:
    """Return config entry data for an emulated tile device."""
    device_num = (next(_device_counter) % 10) + 51
    serial = f"d073d500{device_num:04x}"
    return _make_config(serial, emulator_server.port)
