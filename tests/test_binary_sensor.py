"""Tests for Loxone binary sensor integration."""

from unittest.mock import patch

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN

from custom_components.loxone.binary_sensor import (
    BINARY_SENSOR_TYPES,
    LoxoneDigitalSensor,
    LoxoneSmokeAlarmLevelSensor,
    match_binary_sensor_description,
)


class MockEvent:
    """Mock Loxone event for testing."""

    def __init__(self, data):
        self.data = data


def _make_digital(overrides=None):
    """Create a digital sensor control dict (as async_setup_entry would pass it)."""
    base = {
        "type": "digital",
        "uuidAction": "uuid-digital",
        "name": "Test Digital",
        "room": "Living Room",
        "cat": "Sensors",
        "states": {"active": "state-uuid-active"},
    }
    if overrides:
        base.update(overrides)
    return base


def _make_presence(overrides=None):
    """Create a presence detector control dict (type already overwritten to 'presence')."""
    base = {
        "type": "presence",
        "uuidAction": "uuid-presence",
        "name": "Test Presence",
        "room": "Hallway",
        "cat": "Sensors",
        "states": {"active": "state-uuid-presence-active"},
    }
    if overrides:
        base.update(overrides)
    return base


def _make_smoke(overrides=None):
    """Create a smoke alarm control dict (type already overwritten to 'smoke')."""
    base = {
        "type": "smoke",
        "uuidAction": "uuid-smoke",
        "name": "Test Smoke",
        "room": "Kitchen",
        "cat": "Sensors",
        "states": {
            "areAlarmSignalsOff": "state-uuid-signals-off",
            "level": "state-uuid-level",
        },
    }
    if overrides:
        base.update(overrides)
    return base


# ============================================================================
# Tests: match_binary_sensor_description
# ============================================================================


class TestBinarySensorMatching:
    """Test match_binary_sensor_description — the matching function."""

    # --- Unambiguous control types ---

    def test_presence_type_matches_occupancy(self):
        desc = match_binary_sensor_description("presence")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.OCCUPANCY

    def test_smoke_type_matches_smoke(self):
        desc = match_binary_sensor_description("smoke")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.SMOKE

    def test_presence_ignores_name(self):
        """Presence matches on type alone, name is irrelevant."""
        desc = match_binary_sensor_description("presence", name="Some Door")
        assert desc.device_class == BinarySensorDeviceClass.OCCUPANCY

    # --- Door keywords ---

    def test_door_czech(self):
        desc = match_binary_sensor_description("digital", name="1.04 Dveře")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.DOOR

    def test_door_czech_no_diacritics(self):
        desc = match_binary_sensor_description("digital", name="Hlavni dvere")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.DOOR

    def test_door_english(self):
        desc = match_binary_sensor_description("digital", name="Front Door")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.DOOR

    def test_door_german(self):
        desc = match_binary_sensor_description("digital", name="Haustür")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.DOOR

    def test_door_german_no_diacritics(self):
        desc = match_binary_sensor_description("digital", name="Haustuer")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.DOOR

    def test_door_french(self):
        desc = match_binary_sensor_description("digital", name="Porte d'entrée")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.DOOR

    # --- Window keywords ---

    def test_window_czech(self):
        desc = match_binary_sensor_description("digital", name="1.04 Okno")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.WINDOW

    def test_window_english(self):
        desc = match_binary_sensor_description("digital", name="Bedroom Window")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.WINDOW

    def test_window_german(self):
        desc = match_binary_sensor_description("digital", name="Schlafzimmer Fenster")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.WINDOW

    def test_window_french(self):
        desc = match_binary_sensor_description("digital", name="Fenêtre salon")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.WINDOW

    def test_window_french_no_diacritics(self):
        desc = match_binary_sensor_description("digital", name="Fenetre salon")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.WINDOW

    # --- Light keywords ---

    def test_light_czech(self):
        desc = match_binary_sensor_description("digital", name="Hlavní světlo")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.LIGHT

    def test_light_czech_no_diacritics(self):
        desc = match_binary_sensor_description("digital", name="Hlavni svetlo")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.LIGHT

    def test_light_czech_lampicka(self):
        desc = match_binary_sensor_description("digital", name="Levá lampička")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.LIGHT

    def test_light_czech_lampicka_no_diacritics(self):
        desc = match_binary_sensor_description("digital", name="Leva lampicka")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.LIGHT

    def test_light_czech_lampa(self):
        desc = match_binary_sensor_description("digital", name="Stojací lampa")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.LIGHT

    def test_light_english(self):
        desc = match_binary_sensor_description("digital", name="Living Room Light")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.LIGHT

    def test_light_english_lamp(self):
        desc = match_binary_sensor_description("digital", name="Desk Lamp")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.LIGHT

    def test_light_german(self):
        desc = match_binary_sensor_description("digital", name="Deckenlicht")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.LIGHT

    def test_light_german_lampe(self):
        desc = match_binary_sensor_description("digital", name="Nachttisch Lampe")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.LIGHT

    def test_light_german_leuchte(self):
        desc = match_binary_sensor_description("digital", name="Wandleuchte")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.LIGHT

    def test_light_french(self):
        desc = match_binary_sensor_description("digital", name="Lumière cuisine")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.LIGHT

    def test_light_french_no_diacritics(self):
        desc = match_binary_sensor_description("digital", name="Lumiere cuisine")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.LIGHT

    # --- Case insensitivity ---

    def test_case_insensitive_door(self):
        desc = match_binary_sensor_description("digital", name="DVEŘE")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.DOOR

    def test_case_insensitive_window(self):
        desc = match_binary_sensor_description("digital", name="OKNO LOŽNICE")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.WINDOW

    def test_case_insensitive_light(self):
        desc = match_binary_sensor_description("digital", name="HLAVNÍ SVĚTLO")
        assert desc is not None
        assert desc.device_class == BinarySensorDeviceClass.LIGHT

    # --- No match ---

    def test_digital_no_keyword_returns_none(self):
        desc = match_binary_sensor_description("digital", name="Test Digital")
        assert desc is None

    def test_digital_generic_name_returns_none(self):
        desc = match_binary_sensor_description("digital", name="Ochrana proti přehřátí")
        assert desc is None

    def test_futura_does_not_match_door(self):
        """Regression: 'Futura' must not match German 'tür'/'tuer' door keyword."""
        desc = match_binary_sensor_description("digital", name="Futura Povolení Chlazení")
        assert desc is None

    def test_unknown_type_returns_none(self):
        desc = match_binary_sensor_description("unknown_type", name="Door Sensor")
        assert desc is None

    def test_empty_name_digital_returns_none(self):
        desc = match_binary_sensor_description("digital")
        assert desc is None


# ============================================================================
# Tests: BINARY_SENSOR_TYPES structure validation
# ============================================================================


class TestBinarySensorTypesStructure:
    """Validate BINARY_SENSOR_TYPES tuple is well-formed."""

    def test_all_entries_have_device_class(self):
        for desc in BINARY_SENSOR_TYPES:
            assert desc.device_class is not None, f"{desc.key} missing device_class"

    def test_all_entries_have_loxone_type(self):
        for desc in BINARY_SENSOR_TYPES:
            assert desc.loxone_type, f"{desc.key} missing loxone_type"

    def test_keyword_entries_have_nonempty_keywords(self):
        """Digital-type entries must have keywords; type-based entries must not."""
        for desc in BINARY_SENSOR_TYPES:
            if desc.loxone_type == "digital":
                assert desc.name_keywords, f"{desc.key}: digital type needs keywords"
            else:
                assert not desc.name_keywords, f"{desc.key}: non-digital shouldn't have keywords"

    def test_unique_keys(self):
        keys = [desc.key for desc in BINARY_SENSOR_TYPES]
        assert len(keys) == len(set(keys)), "Duplicate keys in BINARY_SENSOR_TYPES"


# ============================================================================
# Tests: LoxoneDigitalSensor device_class via entity_description
# ============================================================================


class TestPresenceDetectorDeviceClass:
    """Test PresenceDetector device_class assignment."""

    def test_presence_detector_gets_occupancy_device_class(self):
        sensor = LoxoneDigitalSensor(**_make_presence())
        assert sensor.device_class == BinarySensorDeviceClass.OCCUPANCY

    def test_presence_detector_state_uuid_is_active(self):
        sensor = LoxoneDigitalSensor(**_make_presence())
        assert sensor._state_uuid == "state-uuid-presence-active"


class TestSmokeAlarmDeviceClass:
    """Test SmokeAlarm device_class assignment."""

    def test_smoke_alarm_gets_smoke_device_class(self):
        sensor = LoxoneDigitalSensor(**_make_smoke())
        assert sensor.device_class == BinarySensorDeviceClass.SMOKE

    def test_smoke_alarm_state_uuid_is_arealarmsignalsoff(self):
        sensor = LoxoneDigitalSensor(**_make_smoke())
        assert sensor._state_uuid == "state-uuid-signals-off"


class TestDigitalSensorKeywordDeviceClass:
    """Test InfoOnlyDigital gets device_class from name keywords."""

    def test_door_keyword_in_name(self):
        sensor = LoxoneDigitalSensor(**_make_digital({"name": "1.04 Dveře"}))
        assert sensor.device_class == BinarySensorDeviceClass.DOOR

    def test_window_keyword_in_name(self):
        sensor = LoxoneDigitalSensor(**_make_digital({"name": "1.04 Okno"}))
        assert sensor.device_class == BinarySensorDeviceClass.WINDOW

    def test_light_keyword_in_name(self):
        sensor = LoxoneDigitalSensor(**_make_digital({"name": "Hlavní světlo"}))
        assert sensor.device_class == BinarySensorDeviceClass.LIGHT

    def test_light_keyword_lampicka(self):
        sensor = LoxoneDigitalSensor(**_make_digital({"name": "Levá lampička"}))
        assert sensor.device_class == BinarySensorDeviceClass.LIGHT

    def test_no_keyword_no_device_class(self):
        sensor = LoxoneDigitalSensor(**_make_digital())
        assert sensor.device_class is None

    def test_generic_name_no_device_class(self):
        sensor = LoxoneDigitalSensor(**_make_digital({"name": "Cirkulace"}))
        assert sensor.device_class is None


class TestControlFlowStateUuidSelection:
    """Test if/elif chain correctly selects state UUIDs."""

    def test_smoke_uses_arealarmsignalsoff_not_active(self):
        """If a SmokeAlarm also had 'active' in states, areAlarmSignalsOff wins."""
        control = _make_smoke({"states": {
            "areAlarmSignalsOff": "state-signals-off",
            "active": "state-active",
        }})
        sensor = LoxoneDigitalSensor(**control)
        assert sensor._state_uuid == "state-signals-off"

    def test_presence_uses_active_state(self):
        sensor = LoxoneDigitalSensor(**_make_presence())
        assert sensor._state_uuid == "state-uuid-presence-active"

    def test_digital_falls_back_to_uuid_action(self):
        sensor = LoxoneDigitalSensor(**_make_digital())
        assert sensor._state_uuid == "uuid-digital"


# ============================================================================
# Tests: Icon behavior
# ============================================================================


class TestIconProperty:
    """Test icon is delegated to HA when device_class is set."""

    def test_icon_none_when_device_class_set(self):
        sensor = LoxoneDigitalSensor(**_make_presence())
        assert sensor.icon is None

    def test_icon_generic_when_no_device_class(self):
        sensor = LoxoneDigitalSensor(**_make_digital())
        assert sensor.icon == "mdi:checkbox-blank-circle-outline"

    def test_icon_none_for_door(self):
        sensor = LoxoneDigitalSensor(**_make_digital({"name": "1.04 Dveře"}))
        assert sensor.icon is None

    def test_icon_none_for_light(self):
        sensor = LoxoneDigitalSensor(**_make_digital({"name": "Hlavní světlo"}))
        assert sensor.icon is None


# ============================================================================
# Tests: Original smoke alarm (areAlarmSignalsOff) semantics unchanged
# ============================================================================


class TestOriginalSmokeAlarmSemantics:
    """Test original smoke alarm (areAlarmSignalsOff) semantics unchanged."""

    @patch("homeassistant.helpers.entity.Entity.async_schedule_update_ha_state")
    def test_smoke_alarm_signals_off_true_is_on(self, mock_update):
        sensor = LoxoneDigitalSensor(**_make_smoke())
        event = MockEvent({"state-uuid-signals-off": 1.0})

        import asyncio
        asyncio.run(sensor.event_handler(event))

        assert sensor.is_on is True

    @patch("homeassistant.helpers.entity.Entity.async_schedule_update_ha_state")
    def test_smoke_alarm_signals_active_is_off(self, mock_update):
        sensor = LoxoneDigitalSensor(**_make_smoke())
        event = MockEvent({"state-uuid-signals-off": 0})

        import asyncio
        asyncio.run(sensor.event_handler(event))

        assert sensor.is_on is False


# ============================================================================
# Tests: SmokeAlarmLevelSensor
# ============================================================================


class TestSmokeAlarmLevelSensor:
    """Test new SmokeAlarmLevelSensor with correct semantics."""

    def test_level_sensor_has_smoke_device_class(self):
        sensor = LoxoneSmokeAlarmLevelSensor(**_make_smoke())
        assert sensor.device_class == BinarySensorDeviceClass.SMOKE

    def test_level_sensor_unique_id_suffix(self):
        sensor = LoxoneSmokeAlarmLevelSensor(**_make_smoke())
        assert sensor.unique_id == "uuid-smoke_level"

    def test_level_sensor_derived_name(self):
        sensor = LoxoneSmokeAlarmLevelSensor(**_make_smoke())
        assert sensor.name == "Test Smoke (Alarm Level)"

    @patch("homeassistant.helpers.entity.Entity.async_schedule_update_ha_state")
    def test_level_sensor_on_when_level_one_prealarm(self, mock_update):
        sensor = LoxoneSmokeAlarmLevelSensor(**_make_smoke())
        event = MockEvent({"state-uuid-level": 1})

        import asyncio
        asyncio.run(sensor.event_handler(event))

        assert sensor.is_on is True

    @patch("homeassistant.helpers.entity.Entity.async_schedule_update_ha_state")
    def test_level_sensor_on_when_level_two_mainalarm(self, mock_update):
        sensor = LoxoneSmokeAlarmLevelSensor(**_make_smoke())
        event = MockEvent({"state-uuid-level": 2})

        import asyncio
        asyncio.run(sensor.event_handler(event))

        assert sensor.is_on is True

    @patch("homeassistant.helpers.entity.Entity.async_schedule_update_ha_state")
    def test_level_sensor_off_when_level_zero(self, mock_update):
        sensor = LoxoneSmokeAlarmLevelSensor(**_make_smoke())
        event = MockEvent({"state-uuid-level": 0})

        import asyncio
        asyncio.run(sensor.event_handler(event))

        assert sensor.is_on is False

    @patch("homeassistant.helpers.entity.Entity.async_schedule_update_ha_state")
    def test_level_sensor_off_when_level_negative(self, mock_update):
        sensor = LoxoneSmokeAlarmLevelSensor(**_make_smoke())
        event = MockEvent({"state-uuid-level": -1})

        import asyncio
        asyncio.run(sensor.event_handler(event))

        assert sensor.is_on is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
