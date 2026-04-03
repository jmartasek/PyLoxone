"""Support for Loxone binary sensors."""

from __future__ import annotations

import logging
from functools import cached_property
from typing import Literal, final

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.binary_sensor import (PLATFORM_SCHEMA,
                                                    BinarySensorDeviceClass,
                                                    BinarySensorEntity,
                                                    BinarySensorEntityDescription)
from homeassistant.components.sensor import CONF_STATE_CLASS
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (CONF_DEVICE_CLASS, CONF_NAME,
                                 CONF_UNIT_OF_MEASUREMENT, CONF_VALUE_TEMPLATE,
                                 STATE_OFF, STATE_ON, STATE_UNKNOWN)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import LoxoneEntity
from .const import CONF_ACTIONID, DOMAIN, SENDDOMAIN
from .helpers import (add_room_and_cat_to_value_values, get_all,
                      get_or_create_device)
from .miniserver import get_miniserver_from_hass

_LOGGER = logging.getLogger(__name__)
NEW_SENSOR = "binairy_sensors"
DEFAULT_NAME = "Loxone Binary Sensor"

LOXONE_DEVICE_CLASS_MAP: dict[str, BinarySensorDeviceClass] = {
    "presence": BinarySensorDeviceClass.PRESENCE,
    "smoke": BinarySensorDeviceClass.SMOKE,
}


class LoxoneBinarySensorDescription(BinarySensorEntityDescription, frozen_or_thawed=True):
    """Describes a Loxone binary sensor entity.

    Mirrors LoxoneEntityDescription from sensor.py. For known control types
    (PresenceDetector, SmokeAlarm), loxone_type alone is sufficient.
    For InfoOnlyDigital, name_keywords disambiguate door/window/light.
    """

    loxone_type: str
    name_keywords: tuple[str, ...] = ()


BINARY_SENSOR_TYPES: tuple[LoxoneBinarySensorDescription, ...] = (
    # --- Unambiguous: known control types ---
    LoxoneBinarySensorDescription(
        key="occupancy",
        loxone_type="presence",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
    ),
    LoxoneBinarySensorDescription(
        key="smoke",
        loxone_type="smoke",
        device_class=BinarySensorDeviceClass.SMOKE,
    ),
    # --- InfoOnlyDigital: name-keyword disambiguation (CZ/EN/DE/FR) ---
    LoxoneBinarySensorDescription(
        key="door",
        loxone_type="digital",
        name_keywords=("dveře", "dvere", "door", "tür", "tuer", "porte"),
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    LoxoneBinarySensorDescription(
        key="window",
        loxone_type="digital",
        name_keywords=("okno", "window", "fenster", "fenêtre", "fenetre"),
        device_class=BinarySensorDeviceClass.WINDOW,
    ),
    LoxoneBinarySensorDescription(
        key="light",
        loxone_type="digital",
        name_keywords=(
            "světlo", "svetlo", "lampička", "lampicka", "lampa",
            "light", "lamp",
            "licht", "lampe", "leuchte",
            "lumière", "lumiere",
        ),
        device_class=BinarySensorDeviceClass.LIGHT,
    ),
)


def match_binary_sensor_description(
    loxone_type: str, name: str = "",
) -> LoxoneBinarySensorDescription | None:
    """Find the first matching description for a Loxone binary sensor.

    Known control types (presence, smoke) match immediately.
    InfoOnlyDigital ("digital") requires a keyword hit in name.
    Returns None if no description matches.
    """
    name_lower = name.lower()
    for desc in BINARY_SENSOR_TYPES:
        if loxone_type != desc.loxone_type:
            continue
        if not desc.name_keywords:
            return desc
        if any(kw in name_lower for kw in desc.name_keywords):
            return desc
    return None


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_devices: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up Loxone Sensor from yaml"""
    value_template = config.get(CONF_VALUE_TEMPLATE)
    if value_template is not None:
        value_template.hass = hass

    # Devices from yaml
    if config != {}:
        # Here setup all Sensors in Yaml-File
        new_sensor = LoxoneCustomBinarySensor(**config)
        async_add_devices([new_sensor])
        return True
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entry."""
    miniserver = get_miniserver_from_hass(hass, config_entry)
    loxconfig = miniserver.lox_config.json
    entities = []

    for sensor in get_all(loxconfig, "InfoOnlyDigital"):
        sensor = add_room_and_cat_to_value_values(loxconfig, sensor)
        sensor.update({"type": "digital"})
        entities.append(LoxoneDigitalSensor(**sensor))

    for sensor in get_all(loxconfig, "PresenceDetector"):
        sensor = add_room_and_cat_to_value_values(loxconfig, sensor)
        sensor.update({"type": "presence"})
        entities.append(LoxoneDigitalSensor(**sensor))

    for smoke_control in get_all(loxconfig, "SmokeAlarm"):
        smoke_control = add_room_and_cat_to_value_values(loxconfig, smoke_control)
        smoke_control.update({"type": "smoke"})
        entities.append(LoxoneDigitalSensor(**smoke_control))

        # Add second sensor for level state (correct semantics)
        if "level" in smoke_control.get("states", {}):
            smoke_level = add_room_and_cat_to_value_values(
                loxconfig, smoke_control.copy()
            )
            entities.append(LoxoneSmokeAlarmLevelSensor(**smoke_level))

    @callback
    def async_add_binary_sensors(_):
        async_add_entities(_, True)

    miniserver.listeners.append(
        async_dispatcher_connect(
            hass,
            miniserver.async_signal_new_device("sensors"),
            async_add_binary_sensors,
        )
    )
    async_add_entities(entities)


class LoxoneDigitalSensor(LoxoneEntity, BinarySensorEntity):
    """Representation of a binary Loxone device."""

    _attr_is_on: bool | None = None
    _attr_state: None = None
    _attr_available = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._attr_state = STATE_UNKNOWN
        self._attr_is_on = STATE_UNKNOWN
        self._from_loxone_config = False

        if (
            "type" in kwargs
            and "room" in kwargs
            and "cat" in kwargs
            and hasattr(self, "states")
        ):
            self._from_loxone_config = True
            if self.type == "smoke":
                self._state_uuid = self.states["areAlarmSignalsOff"]
            elif self.type == "presence":
                self._state_uuid = self.states["active"]
            elif "active" in self.states:
                self._state_uuid = self.uuidAction
            else:
                self._state_uuid = self.uuidAction

            # Set HA device_class via description matching
            desc = match_binary_sensor_description(self.type, self.name)
            if desc:
                self.entity_description = desc
        else:
            self._state_uuid = self.uuidAction

        self._state = STATE_UNKNOWN
        self._format = self._get_format(kwargs.get("details", {}).get("format", ""))
        self._parent_id = kwargs.get("parent_id", None)
        self._on_state = STATE_ON
        self._off_state = STATE_OFF
        self._attr_available = True
        if self.type in LOXONE_DEVICE_CLASS_MAP:
            self._attr_device_class = LOXONE_DEVICE_CLASS_MAP[self.type]
        else:
            self._attr_device_class = None

        if self._parent_id:
            self.uuidAction = self._parent_id

        if self._from_loxone_config:
            self._attr_device_info = get_or_create_device(
                self.unique_id, self.name, self.type, self.room
            )
        else:
            self._attr_device_info = get_or_create_device(
                self.unique_id, self.name, self.type, ""
            )

        if self._from_loxone_config:
            self._attr_extra_state_attributes.update(
                {
                    "state_uuid": self._state_uuid,
                    "device_type": self.type,
                }
            )
        else:
            self._attr_extra_state_attributes.update(
                {
                    "device_type": self._attr_device_class,
                }
            )

    @property
    def icon(self):
        if self.device_class:
            return None  # Let HA choose icon based on device_class
        return "mdi:checkbox-blank-circle-outline"


    async def event_handler(self, e):
        if self._state_uuid in e.data:
            self._state = e.data[self._state_uuid]
            if self._state == 1.0:
                self._state = self._on_state
            else:
                self._state = self._off_state
            if not self._attr_available:
                self._attr_available = True
            self.async_schedule_update_ha_state()

    @final
    @property
    def state(self) -> Literal["on", "off"] | None:
        """Return the state of the binary sensor."""
        if (is_on := self.is_on) is None:
            return None
        return STATE_ON if is_on else STATE_OFF

    @property
    def is_on(self) -> bool | None:
        """Return true if sensor is on."""
        return self._state == self._on_state


class LoxoneSmokeAlarmLevelSensor(LoxoneEntity, BinarySensorEntity):
    """Smoke alarm level binary sensor with correct semantics.

    Uses the 'level' state where level >= 1 means Pre-Alarm or Main Alarm.
    This provides correct semantics: ON when alarm is active, OFF when silent.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._attr_device_class = BinarySensorDeviceClass.SMOKE
        self._state_uuid = self.states.get("level")
        self._state = STATE_UNKNOWN
        self._attr_available = True
        self._on_state = STATE_ON
        self._off_state = STATE_OFF

        # Create derived name to distinguish from original sensor
        self._attr_name = f"{self.name} (Alarm Level)"

        # Group with the original smoke sensor via shared device_info
        self._attr_device_info = get_or_create_device(
            self.unique_id, self.name, self.type, self.room
        )

        self._attr_extra_state_attributes.update(
            {
                "state_uuid": self._state_uuid,
                "device_type": "smoke_alarm_level",
            }
        )

    async def event_handler(self, e):
        """Handle state updates from Loxone.

        level >= 1 means alarm is active (Pre-Alarm=1 or Main Alarm=2).
        level < 1 means no alarm.
        """
        if self._state_uuid and self._state_uuid in e.data:
            level = e.data[self._state_uuid]
            self._state = self._on_state if level >= 1 else self._off_state
            self.async_schedule_update_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return true if alarm is active."""
        return self._state == self._on_state

    @final
    @property
    def state(self) -> Literal["on", "off"] | None:
        """Return the state of the binary sensor."""
        if (is_on := self.is_on) is None:
            return None
        return STATE_ON if is_on else STATE_OFF

    @cached_property
    def unique_id(self) -> str:
        """Return unique ID with _level suffix to distinguish from original sensor."""
        return f"{self.uuidAction}_level"


class LoxoneCustomBinarySensor(LoxoneEntity, BinarySensorEntity):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._name = kwargs["name"]
        self._state = STATE_UNKNOWN
        self._on_state = STATE_ON
        self._off_state = STATE_OFF

        if "uuidAction" in kwargs:
            self.uuidAction = kwargs["uuidAction"]
        else:
            self.uuidAction = ""

    @property
    def is_on(self) -> bool | None:
        """Return true if sensor is on."""
        return self._state == self._on_state

    @property
    def state(self) -> Literal["on", "off"] | None:
        """Return the state of the binary sensor."""
        if (is_on := self.is_on) is None:
            return None
        return STATE_ON if is_on else STATE_OFF

    async def event_handler(self, e):
        if self.uuidAction in e.data:
            data = e.data[self.uuidAction]
            if data == 1.0:
                self._state = self._on_state
            else:
                self._state = self._off_state
            self.async_schedule_update_ha_state()

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name
