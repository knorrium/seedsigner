import os
from unittest.mock import mock_open, patch

from seedsigner.hardware.displays.display_detector import (
    CONCRETE_DISPLAY_CONFIGURATIONS,
    DEFAULT_DISPLAY_CONFIGURATION,
    ENV_DISPLAY_CONFIGURATION,
    detect_display_configuration,
    display_config_from_hat_identity,
    parse_boot_display_config,
    resolve_display_configuration,
)
from seedsigner.models.settings_definition import SettingsConstants


ST7789_240 = SettingsConstants.DISPLAY_CONFIGURATION__ST7789__240x240
ST7789_320 = SettingsConstants.DISPLAY_CONFIGURATION__ST7789__320x240
ILI9341_320 = SettingsConstants.DISPLAY_CONFIGURATION__ILI9341__320x240
AUTO = SettingsConstants.DISPLAY_CONFIGURATION__AUTO


class TestHatIdentityMapping:
    def test_blank_identity_is_unknown(self):
        assert display_config_from_hat_identity() is None
        assert display_config_from_hat_identity(vendor="  ", product="") is None

    def test_explicit_320x240_is_st7789(self):
        assert display_config_from_hat_identity(product="SeedSigner 320x240 Display") == ST7789_320
        assert display_config_from_hat_identity(product="Custom 240x320 LCD") == ST7789_320

    def test_explicit_240x240_is_st7789(self):
        assert display_config_from_hat_identity(product="Waveshare 240x240 LCD HAT") == ST7789_240

    def test_ili9341_wins_over_resolution_string(self):
        assert display_config_from_hat_identity(product="ILI9341 320x240 IPS") == ILI9341_320

    def test_ili9486_is_not_guessed(self):
        assert display_config_from_hat_identity(product="ILI9486 480x320") is None

    def test_waveshare_size_names(self):
        assert display_config_from_hat_identity(product="1.3inch LCD HAT") == ST7789_240
        assert display_config_from_hat_identity(product="1.3 inch LCD HAT") == ST7789_240
        assert display_config_from_hat_identity(product="2inch LCD HAT") == ST7789_320
        assert display_config_from_hat_identity(product="2-inch LCD") == ST7789_320
        assert display_config_from_hat_identity(product="2.8inch IPS") == ILI9341_320

    def test_inch_size_does_not_match_larger_numbers(self):
        assert display_config_from_hat_identity(product="12inch LCD") is None

    def test_unknown_product_is_none(self):
        assert display_config_from_hat_identity(vendor="Acme", product="GPIO Expander") is None


class TestBootConfigParsing:
    def test_plain_value(self):
        assert parse_boot_display_config("st7789_320x240\n") == ST7789_320

    def test_comments_and_whitespace(self):
        contents = """
        # SeedSigner display override
        st7789_320x240  # widescreen ST7789
        """
        assert parse_boot_display_config(contents) == ST7789_320

    def test_auto_is_rejected(self):
        assert parse_boot_display_config("auto\n") is None

    def test_unknown_value_is_rejected(self):
        assert parse_boot_display_config("oled_128x64\n") is None

    def test_empty_is_none(self):
        assert parse_boot_display_config("") is None
        assert parse_boot_display_config("# only a comment\n") is None


class TestResolveDisplayConfiguration:
    def test_manual_selection_is_unchanged(self):
        assert resolve_display_configuration(ST7789_240) == ST7789_240
        assert resolve_display_configuration(ST7789_320) == ST7789_320
        assert resolve_display_configuration(ILI9341_320) == ILI9341_320

    def test_auto_uses_detector(self):
        with patch(
            "seedsigner.hardware.displays.display_detector.detect_display_configuration",
            return_value=ST7789_320,
        ) as detect:
            assert resolve_display_configuration(AUTO) == ST7789_320
            detect.assert_called_once()


class TestDetectDisplayConfiguration:
    def setup_method(self):
        os.environ.pop(ENV_DISPLAY_CONFIGURATION, None)

    def teardown_method(self):
        os.environ.pop(ENV_DISPLAY_CONFIGURATION, None)

    def test_defaults_to_st7789_240_when_nothing_identifies(self):
        with patch("seedsigner.hardware.displays.display_detector._detect_from_hat", return_value=None), \
             patch("seedsigner.hardware.displays.display_detector._detect_from_boot_file", return_value=None):
            assert detect_display_configuration() == DEFAULT_DISPLAY_CONFIGURATION
            assert detect_display_configuration() == ST7789_240

    def test_env_selects_st7789_320(self):
        os.environ[ENV_DISPLAY_CONFIGURATION] = ST7789_320
        assert detect_display_configuration() == ST7789_320

    def test_env_auto_is_ignored(self):
        os.environ[ENV_DISPLAY_CONFIGURATION] = AUTO
        with patch("seedsigner.hardware.displays.display_detector._detect_from_hat", return_value=None), \
             patch("seedsigner.hardware.displays.display_detector._detect_from_boot_file", return_value=None):
            assert detect_display_configuration() == ST7789_240

    def test_hat_is_used_when_present(self):
        with patch("seedsigner.hardware.displays.display_detector._detect_from_hat", return_value=ST7789_320), \
             patch("seedsigner.hardware.displays.display_detector._detect_from_boot_file", return_value=ST7789_240) as boot:
            assert detect_display_configuration() == ST7789_320
            boot.assert_not_called()

    def test_boot_file_is_used_when_hardware_is_silent(self):
        with patch("seedsigner.hardware.displays.display_detector._detect_from_hat", return_value=None), \
             patch("seedsigner.hardware.displays.display_detector._detect_from_boot_file", return_value=ST7789_320):
            assert detect_display_configuration() == ST7789_320

    def test_hat_device_tree_null_terminated_product(self):
        with patch("seedsigner.hardware.displays.display_detector._detect_from_env", return_value=None), \
             patch("seedsigner.hardware.displays.display_detector._detect_from_boot_file", return_value=None), \
             patch("seedsigner.hardware.displays.display_detector._read_dt_string", side_effect=["", "SeedSigner 320x240 ST7789\x00"]):
            assert detect_display_configuration() == ST7789_320

    def test_read_dt_string_strips_nulls_and_missing_files(self):
        from seedsigner.hardware.displays.display_detector import _read_dt_string
        with patch("builtins.open", mock_open(read_data=b"SeedSigner 320x240\x00")):
            assert _read_dt_string(("/fake/product",)) == "SeedSigner 320x240"
        with patch("builtins.open", side_effect=OSError):
            assert _read_dt_string(("/missing",)) == ""

    def test_concrete_configs_cover_supported_drivers(self):
        assert AUTO not in CONCRETE_DISPLAY_CONFIGURATIONS
        assert ST7789_240 in CONCRETE_DISPLAY_CONFIGURATIONS
        assert ST7789_320 in CONCRETE_DISPLAY_CONFIGURATIONS
        assert ILI9341_320 in CONCRETE_DISPLAY_CONFIGURATIONS
