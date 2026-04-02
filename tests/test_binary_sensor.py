"""Tests for Loxone binary sensor integration."""

from unittest.mock import patch

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN

from custom_components.loxone.binary_sensor import (
    LoxoneDigitalSensor,
    LoxoneSmokeAlarmLevelSensor,
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


class TestDigitalSensorNoDeviceClass:
    """Test InfoOnlyDigital has no device_class."""

    def test_digital_sensor_no_device_class(self):
        sensor = LoxoneDigitalSensor(**_make_digital())
        assert sensor.device_class is None

    def test_digital_sensor_state_uuid_falls_back_to_uuid_action(self):
        sensor = LoxoneDigitalSensor(**_make_digital())
        assert sensor._state_uuid == "uuid-digital"


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
