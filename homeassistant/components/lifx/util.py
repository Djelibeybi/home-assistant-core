"""Utility functions for the LIFX integration."""

from __future__ import annotations

from typing import Any

from lifx import HSBK

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_BRIGHTNESS_STEP,
    ATTR_BRIGHTNESS_STEP_PCT,
    ATTR_COLOR_NAME,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_XY_COLOR,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.util.color import color_name_to_rgb, color_RGB_to_hs, color_xy_to_hs

from .const import _LOGGER, INFRARED_BRIGHTNESS_VALUES_MAP


def infrared_brightness_value_to_option(value: float) -> str | None:
    """Convert infrared brightness from value to option."""
    return INFRARED_BRIGHTNESS_VALUES_MAP.get(value)


def infrared_brightness_option_to_value(option: str) -> float | None:
    """Convert infrared brightness option to value."""
    option_values = {v: k for k, v in INFRARED_BRIGHTNESS_VALUES_MAP.items()}
    return option_values.get(option)


def normalize_serial(serial: str) -> str:
    """Normalize a LIFX serial number to lower-case raw hex."""
    if not serial:
        return ""
    return dr.format_mac(serial).replace(":", "")


def mac_matches_serial(mac_addr: str, serial: str) -> bool:
    """Check if a MAC address matches a LIFX serial number.

    LIFX devices use their serial number as the MAC address, but some
    firmware versions have an off-by-one in the last byte.
    """
    formatted_mac = normalize_serial(mac_addr)
    formatted = normalize_serial(serial)
    if formatted and formatted == formatted_mac:
        return True
    # Check off-by-one: serial + 1 in last byte
    if len(formatted) != 12:
        return False
    try:
        octets = [int(formatted[i : i + 2], 16) for i in range(0, 12, 2)]
    except ValueError:
        return False
    octets[5] = (octets[5] + 1) % 256
    offset_serial = "".join(f"{octet:02x}" for octet in octets)
    return offset_serial == formatted_mac


def generate_hsbk(current_color: HSBK, is_on: bool, **kwargs: Any) -> HSBK:
    """Generate a target HSBK from the current color and service call kwargs."""
    _LOGGER.debug(
        "Generating new HSBK from current: %s and kwargs: %s", current_color, kwargs
    )

    if ATTR_BRIGHTNESS_STEP in kwargs or ATTR_BRIGHTNESS_STEP_PCT in kwargs:
        # Convert 0-1.0 float brightness to 0-255 scale for step math
        brightness_8bit = (
            round(current_color.brightness * 255)
            if is_on and current_color.brightness
            else 0
        )

        if ATTR_BRIGHTNESS_STEP in kwargs:
            brightness_8bit += kwargs.pop(ATTR_BRIGHTNESS_STEP)
        else:
            brightness_pct = (brightness_8bit / 255) * 100
            brightness_8bit = round(
                (brightness_pct + kwargs.pop(ATTR_BRIGHTNESS_STEP_PCT)) / 100 * 255
            )

        kwargs[ATTR_BRIGHTNESS] = max(0, min(255, brightness_8bit))

    color = current_color

    # Convert color attributes to HS color
    if ATTR_COLOR_NAME in kwargs:
        try:
            color_name = kwargs.pop(ATTR_COLOR_NAME)
            rgb = color_name_to_rgb(color_name)
            kwargs[ATTR_HS_COLOR] = color_RGB_to_hs(*rgb)
        except ValueError:
            _LOGGER.warning("Invalid color name %s, using default color", color_name)
            kwargs[ATTR_HS_COLOR] = (0, 0)

    if ATTR_RGB_COLOR in kwargs:
        rgb = kwargs.pop(ATTR_RGB_COLOR)
        kwargs[ATTR_HS_COLOR] = color_RGB_to_hs(*rgb)

    if ATTR_XY_COLOR in kwargs:
        xy = kwargs.pop(ATTR_XY_COLOR)
        kwargs[ATTR_HS_COLOR] = color_xy_to_hs(*xy)

    if ATTR_HS_COLOR in kwargs:
        hue, saturation = kwargs[ATTR_HS_COLOR]
        color = color.with_hue(int(hue)).with_saturation(saturation / 100)

    if ATTR_COLOR_TEMP_KELVIN in kwargs:
        kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
        color = color.with_saturation(0).with_kelvin(kelvin)

    if ATTR_BRIGHTNESS in kwargs:
        brightness = kwargs[ATTR_BRIGHTNESS] / 255
        color = color.with_brightness(brightness)

    if ATTR_BRIGHTNESS_PCT in kwargs:
        brightness = kwargs[ATTR_BRIGHTNESS_PCT] / 100
        color = color.with_brightness(brightness)

    _LOGGER.debug("Generated HSBK: %s", color)
    return color
