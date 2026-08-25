"""
Detect which display is attached so Auto can choose a driver without a settings visit.

ST7789 240x240 and ST7789 320x240 use the same controller and the same 240x320 GRAM.
The Waveshare 1.3" hat also does not wire MISO, so the panel size cannot be read back
over SPI. Auto therefore identifies 320x240 ST7789 hats from:

* Raspberry Pi HAT EEPROM / device-tree product strings
* Optional /boot/display_config (one line, e.g. st7789_320x240)
* SEEDSIGNER_DISPLAY env var (emulator / development)
"""
import logging
import os
import re

from seedsigner.models.settings_definition import SettingsConstants

logger = logging.getLogger(__name__)


DEFAULT_DISPLAY_CONFIGURATION = SettingsConstants.DISPLAY_CONFIGURATION__ST7789__240x240

ENV_DISPLAY_CONFIGURATION = "SEEDSIGNER_DISPLAY"

# Device-tree nodes populated by the Pi firmware when a HAT EEPROM is present.
HAT_PRODUCT_PATHS = (
    "/proc/device-tree/hat/product",
    "/sys/firmware/devicetree/base/hat/product",
)
HAT_VENDOR_PATHS = (
    "/proc/device-tree/hat/vendor",
    "/sys/firmware/devicetree/base/hat/vendor",
)

# FAT boot partition is writable from any computer; useful on stateless boots.
BOOT_CONFIG_PATHS = (
    "/boot/display_config",
    "/boot/firmware/display_config",
)

# Concrete driver configs (not Auto) that Auto is allowed to resolve to.
CONCRETE_DISPLAY_CONFIGURATIONS = {
    SettingsConstants.DISPLAY_CONFIGURATION__ST7789__240x240,
    SettingsConstants.DISPLAY_CONFIGURATION__ST7789__320x240,
    SettingsConstants.DISPLAY_CONFIGURATION__ILI9341__320x240,
}


def resolve_display_configuration(configured: str) -> str:
    """Return a concrete display_config, running detection when Auto is selected."""
    if configured == SettingsConstants.DISPLAY_CONFIGURATION__AUTO:
        detected = detect_display_configuration()
        logger.info("Display Auto-detect resolved to %s", detected)
        return detected
    return configured


def detect_display_configuration() -> str:
    """
    Best-effort hardware detection. Never raises; falls back to 240x240 ST7789.
    """
    for source, detect in (
        ("env", _detect_from_env),
        ("hat", _detect_from_hat),
        ("boot", _detect_from_boot_file),
    ):
        value = detect()
        if value:
            logger.info("Display detected via %s: %s", source, value)
            return value

    logger.info("Display Auto-detect found no identity; using %s", DEFAULT_DISPLAY_CONFIGURATION)
    return DEFAULT_DISPLAY_CONFIGURATION


def display_config_from_hat_identity(vendor: str = "", product: str = "") -> str | None:
    """
    Map a HAT vendor/product string to a concrete display_config.

    Custom 320x240 ST7789 hats should put "320x240" in the EEPROM product name
    (and "ili9341" if that controller is used).
    """
    identity = f"{vendor} {product}".strip().lower()
    if not identity:
        return None

    # Controller name is more specific than resolution, so check it first.
    if "ili9341" in identity:
        return SettingsConstants.DISPLAY_CONFIGURATION__ILI9341__320x240

    if "ili9486" in identity:
        # Driver is not implemented yet; do not guess a working config.
        return None

    if "240x240" in identity or "240*240" in identity:
        return SettingsConstants.DISPLAY_CONFIGURATION__ST7789__240x240

    if any(token in identity for token in ("320x240", "240x320", "320*240", "240*320")):
        return SettingsConstants.DISPLAY_CONFIGURATION__ST7789__320x240

    # Common panel-size names used by Waveshare-style hats
    if _has_inch_size(identity, "1.3"):
        return SettingsConstants.DISPLAY_CONFIGURATION__ST7789__240x240

    if _has_inch_size(identity, "2.4") or _has_inch_size(identity, "2.8"):
        return SettingsConstants.DISPLAY_CONFIGURATION__ILI9341__320x240

    if _has_inch_size(identity, "2") or _has_inch_size(identity, "2.0"):
        return SettingsConstants.DISPLAY_CONFIGURATION__ST7789__320x240

    return None


def _has_inch_size(identity: str, size: str) -> bool:
    """True if `identity` names a panel size like '2inch' / '1.3 inch', not '12inch'."""
    return re.search(rf"(^|[^0-9.]){re.escape(size)}[\s-]*inch", identity) is not None


def parse_boot_display_config(contents: str) -> str | None:
    """Parse a /boot/display_config file: first non-comment, non-empty line."""
    if not contents:
        return None
    for raw_line in contents.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line == SettingsConstants.DISPLAY_CONFIGURATION__AUTO:
            # Avoid recursive Auto.
            return None
        if line in CONCRETE_DISPLAY_CONFIGURATIONS:
            return line
        logger.warning("Ignoring unrecognized display_config value: %s", line)
        return None
    return None


def _detect_from_env() -> str | None:
    value = os.environ.get(ENV_DISPLAY_CONFIGURATION, "").strip()
    if not value:
        return None
    if value == SettingsConstants.DISPLAY_CONFIGURATION__AUTO:
        return None
    if value in CONCRETE_DISPLAY_CONFIGURATIONS:
        return value
    logger.warning("Ignoring unrecognized %s=%s", ENV_DISPLAY_CONFIGURATION, value)
    return None


def _read_dt_string(paths: tuple[str, ...]) -> str:
    for path in paths:
        try:
            with open(path, "rb") as dt_file:
                return dt_file.read().decode("utf-8", errors="replace").rstrip("\x00").strip()
        except OSError:
            continue
    return ""


def _detect_from_hat() -> str | None:
    vendor = _read_dt_string(HAT_VENDOR_PATHS)
    product = _read_dt_string(HAT_PRODUCT_PATHS)
    if not vendor and not product:
        return None
    return display_config_from_hat_identity(vendor=vendor, product=product)


def _detect_from_boot_file() -> str | None:
    for path in BOOT_CONFIG_PATHS:
        try:
            with open(path, "r", encoding="utf-8") as boot_file:
                parsed = parse_boot_display_config(boot_file.read())
        except OSError:
            continue
        if parsed:
            return parsed
    return None
