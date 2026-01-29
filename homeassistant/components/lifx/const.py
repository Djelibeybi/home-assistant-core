"""Constants for the LIFX integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING, TypedDict

from awesomeversion import AwesomeVersion
from lifx import HSBK, LightWaveform

from homeassistant.util.hass_dict import HassKey

if TYPE_CHECKING:
    from .manager import LIFXManager

DOMAIN = "lifx"
DATA_LIFX_MANAGER: HassKey[LIFXManager] = HassKey(DOMAIN)

LIFX_DEFAULT_PORT = 56700

DISCOVERY_INTERVAL = 10

DISCOVERY_TIMEOUT = 45
DEVICE_TIMEOUT = 8.0
DEVICE_RETRIES = 4
DEVICE_UNAVAILABLE_RETRIES = 3

SCAN_INTERVAL = timedelta(seconds=10)

DEFAULT_BRIGHTNESS = 0.8

CEILING_UPLIGHT_SUFFIX = "_uplight"
CEILING_DOWNLIGHT_SUFFIX = "_downlight"

CONF_LABEL = "label"
CONF_SERIAL = "serial"


class IdentifyWaveformDict(TypedDict):
    """Type definition for IDENTIFY_WAVEFORM."""

    color: HSBK
    period: float
    cycles: float
    waveform: LightWaveform
    transient: bool
    skew_ratio: float


IDENTIFY_WAVEFORM: IdentifyWaveformDict = {
    "color": HSBK(hue=0, saturation=0, brightness=0, kelvin=3500),
    "period": 1.0,
    "cycles": 3.0,
    "waveform": LightWaveform.SINE,
    "transient": True,
    "skew_ratio": 0.5,
}

IDENTIFY = "identify"
IDENTIFY_DELAY = 3.0
RESTART = "restart"

ATTR_DURATION = "duration"
ATTR_INDICATION = "indication"
ATTR_INFRARED = "infrared"
ATTR_POWER = "power"
ATTR_REMAINING = "remaining"
ATTR_RSSI = "rssi"
ATTR_ZONES = "zones"

ATTR_THEME = "theme"

HEV_CYCLE_STATE = "hev_cycle_state"
INFRARED_BRIGHTNESS = "infrared_brightness"
INFRARED_BRIGHTNESS_VALUES_MAP: dict[float, str] = {
    0.0: "Disabled",
    0.25: "25%",
    0.50: "50%",
    1.0: "100%",
}

REQUEST_REFRESH_DELAY = 0.20

RSSI_DBM_FW = AwesomeVersion("2.77")

_LOGGER = logging.getLogger(__package__)
