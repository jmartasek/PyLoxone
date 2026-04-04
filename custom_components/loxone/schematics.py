"""Auto-generate a Lovelace dashboard from Loxone SystemScheme schematics.

Extracts schematic images and control positions from the Loxone structure file,
downloads the images, and creates a picture-elements dashboard in Home Assistant.
"""

import logging
import os
from pathlib import Path

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

# Map HA platform domain → (element_type, tap_action)
_ELEMENT_MAP: dict[str, tuple[str, str]] = {
    "light": ("state-icon", "toggle"),
    "switch": ("state-icon", "toggle"),
    "fan": ("state-icon", "toggle"),
    "scene": ("state-icon", "toggle"),
    "cover": ("state-icon", "more-info"),
    "climate": ("state-badge", "more-info"),
    "media_player": ("state-icon", "more-info"),
    "button": ("state-icon", "more-info"),
    "alarm_control_panel": ("state-icon", "more-info"),
    "sensor": ("state-label", "more-info"),
    "binary_sensor": ("state-label", "more-info"),
    "number": ("state-label", "more-info"),
}

# Domains that show values — get a readable label style on the floor plan
_LABEL_DOMAINS = {"sensor", "binary_sensor", "number"}
_LABEL_STYLE = {
    "font-size": "0.9vw",
    "color": "white",
    "background-color": "rgba(0, 0, 0, 0.65)",
    "border-radius": "3px",
    "transform": "scale(0.85)",
    "transform-origin": "center center",
    "line-height": "1.1",
    "white-space": "nowrap",
}


async def async_setup_schematics(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    coordinator,
) -> None:
    """Set up the schematics dashboard. Runs as a background task."""
    try:
        await _async_setup_schematics_inner(hass, config_entry, coordinator)
    except Exception:
        _LOGGER.exception("Failed to set up schematics dashboard")


async def _async_setup_schematics_inner(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    coordinator,
) -> None:
    structure = coordinator.api.structure_file
    schematics = _get_schematics(structure)
    if not schematics:
        _LOGGER.debug("No SystemScheme controls found, skipping schematics dashboard")
        return

    _LOGGER.info("Found %d SystemScheme schematic(s)", len(schematics))

    # Ensure www/pyloxone dir and /local/ route
    pyloxone_path = await _async_ensure_local_serving(hass)

    # Download images
    image_urls = await _async_download_images(
        hass, coordinator, schematics, pyloxone_path
    )

    # Map Loxone UUIDs → HA entity_ids
    uuid_map = _build_uuid_entity_map(hass)

    # Build views (one per schematic)
    views = []
    for ctrl in schematics:
        details = ctrl.get("details", {})
        image_url = image_urls.get(ctrl["uuidAction"])
        if not image_url:
            continue

        card = _build_picture_elements_card(ctrl, image_url, uuid_map)
        views.append(
            {
                "title": ctrl.get("name", "Schematic"),
                "icon": "mdi:floor-plan",
                "panel": True,
                "cards": [card],
            }
        )

    if not views:
        _LOGGER.warning("No schematics with downloadable images, skipping dashboard")
        return

    # Create/update the dashboard
    ms_name = structure.get("msInfo", {}).get("msName")
    await _async_create_or_update_dashboard(hass, config_entry, views, ms_name)


def _get_schematics(structure_file: dict) -> list[dict]:
    """Return SystemScheme controls from the structure file."""
    return [
        ctrl
        for ctrl in structure_file.get("controls", {}).values()
        if ctrl.get("type") == "SystemScheme"
    ]


async def _async_ensure_local_serving(hass: HomeAssistant) -> Path:
    """Ensure www/pyloxone dir exists and /local/ route is registered."""
    www_path = Path(hass.config.path("www"))
    pyloxone_path = www_path / "pyloxone"
    await hass.async_add_executor_job(
        lambda: pyloxone_path.mkdir(parents=True, exist_ok=True)
    )

    # /local/ is only registered if www/ existed at frontend startup.
    # Register it ourselves if missing.
    registered = any(
        getattr(resource, "canonical", None) == "/local"
        for resource in hass.http.app.router.resources()
    )
    if not registered:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig("/local", str(www_path), True)]
        )
        _LOGGER.debug("Registered /local/ static path for www/ directory")

    return pyloxone_path


async def _async_download_images(
    hass: HomeAssistant,
    coordinator,
    schematics: list[dict],
    pyloxone_path: Path,
) -> dict[str, str]:
    """Download schematic images. Returns {ctrl_uuid: '/local/pyloxone/filename'}."""
    session = async_get_clientsession(hass)
    base_url = f"{coordinator.api.scheme}://{coordinator.api.url}"
    auth = aiohttp.BasicAuth(coordinator.api.username, coordinator.api.password)
    timeout = aiohttp.ClientTimeout(total=30)

    result: dict[str, str] = {}

    for ctrl in schematics:
        uuid = ctrl["uuidAction"]
        details = ctrl.get("details", {})
        image_path = details.get("imagePath")
        image_version = details.get("imageVersion", 0)

        if not image_path:
            _LOGGER.warning("Schematic '%s' has no imagePath, skipping", ctrl.get("name"))
            continue

        ext = Path(image_path).suffix or ".jpg"
        # Versioned filename busts both browser cache and HA's server-side LRU
        versioned_name = f"{uuid}_{image_version}{ext}"
        local_file = pyloxone_path / versioned_name

        if local_file.exists():
            _LOGGER.debug("Image %s already cached", versioned_name)
            result[uuid] = f"/local/pyloxone/{versioned_name}"
            continue

        url = f"{base_url}/{image_path}"
        try:
            resp = await session.get(url, auth=auth, timeout=timeout)
            if resp.status != 200:
                _LOGGER.error(
                    "Failed to download image for '%s': HTTP %d from %s",
                    ctrl.get("name"),
                    resp.status,
                    url,
                )
                continue
            data = await resp.read()
            await hass.async_add_executor_job(local_file.write_bytes, data)
            result[uuid] = f"/local/pyloxone/{versioned_name}"
            _LOGGER.info(
                "Downloaded schematic image '%s' (%d KB)",
                ctrl.get("name"),
                len(data) // 1024,
            )
        except Exception:
            _LOGGER.exception("Error downloading image for '%s'", ctrl.get("name"))

    return result


def _build_uuid_entity_map(hass: HomeAssistant) -> dict[str, tuple[str, str | None]]:
    """Build mapping from Loxone UUID → (entity_id, device_class)."""
    registry = er.async_get(hass)
    mapping: dict[str, tuple[str, str | None]] = {}
    for entry in registry.entities.values():
        if entry.platform == "loxone":
            dc = entry.device_class or entry.original_device_class
            mapping[entry.unique_id] = (entry.entity_id, dc)
    return mapping


def _resolve_entity(
    uuid: str, uuid_map: dict[str, tuple[str, str | None]]
) -> tuple[str, str | None] | None:
    """Find (entity_id, device_class) for a Loxone UUID."""
    if uuid in uuid_map:
        return uuid_map[uuid]
    # Prefix match for Meter subsensors (unique_id = uuidAction + attr_name)
    for unique_id, value in uuid_map.items():
        if unique_id.startswith(uuid):
            return value
    return None


def _build_picture_elements_card(
    ctrl: dict,
    image_url: str,
    uuid_map: dict[str, tuple[str, str | None]],
) -> dict:
    """Build a picture-elements card from a SystemScheme control."""
    details = ctrl.get("details", {})
    scheme_w = details.get("schemeSize", {}).get("width", 1)
    scheme_h = details.get("schemeSize", {}).get("height", 1)
    refs = details.get("controlReferences", [])

    elements: list[dict] = []
    matched = 0

    for ref in refs:
        ref_uuid = ref.get("uuidAction")
        if not ref_uuid:
            continue

        resolved = _resolve_entity(ref_uuid, uuid_map)
        if not resolved:
            continue

        entity_id, device_class = resolved
        matched += 1
        domain = entity_id.split(".", 1)[0]
        elem_type, tap_action = _ELEMENT_MAP.get(domain, ("state-icon", "more-info"))

        # Binary sensors with device_class get a meaningful icon;
        # those without fall back to state-label showing on/off text
        if domain == "binary_sensor" and device_class:
            elem_type = "state-icon"

        left_pct = round(ref["pos"]["x"] / scheme_w * 100, 2)
        top_pct = round(ref["pos"]["y"] / scheme_h * 100, 2)

        use_label_style = elem_type == "state-label" and domain in _LABEL_DOMAINS

        element: dict = {
            "type": elem_type,
            "entity": entity_id,
            "style": {
                "left": f"{left_pct}%",
                "top": f"{top_pct}%",
                **(_LABEL_STYLE if use_label_style else {}),
            },
            "tap_action": {"action": tap_action},
        }

        # Add text prefix from the schematic definition (e.g. "Heating: ", "Cíl: ")
        text = ref.get("text", "").strip()
        if text and elem_type == "state-label":
            element["prefix"] = text

        elements.append(element)

    _LOGGER.debug(
        "Schematic '%s': mapped %d of %d controls to entities",
        ctrl.get("name"),
        matched,
        len(refs),
    )

    return {
        "type": "picture-elements",
        "image": image_url,
        "elements": elements,
    }


async def _async_create_or_update_dashboard(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    views: list[dict],
    miniserver_name: str | None,
) -> None:
    """Create or update the schematics Lovelace dashboard."""
    try:
        from homeassistant.components.frontend import async_register_built_in_panel
        from homeassistant.components.lovelace.const import LOVELACE_DATA
        from homeassistant.components.lovelace.dashboard import LovelaceStorage
    except ImportError:
        _LOGGER.warning("Lovelace components not available, skipping schematics dashboard")
        return

    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        _LOGGER.warning("Lovelace not loaded, skipping schematics dashboard")
        return

    url_path = f"loxone-schematics-{config_entry.entry_id[:8]}"
    dashboard_id = f"loxone_schematics_{config_entry.entry_id[:8]}"
    title = f"Schematics ({miniserver_name})" if miniserver_name else "Loxone Schematics"

    dashboard_item = {
        "id": dashboard_id,
        "url_path": url_path,
        "title": title,
        "icon": "mdi:floor-plan",
        "show_in_sidebar": True,
        "require_admin": False,
        "mode": "storage",
    }

    # Create LovelaceStorage if not already present
    if url_path not in lovelace_data.dashboards:
        lovelace_data.dashboards[url_path] = LovelaceStorage(hass, dashboard_item)

    # Always register/update panel (handles restart + config entry reload)
    async_register_built_in_panel(
        hass,
        "lovelace",
        frontend_url_path=url_path,
        sidebar_title=title,
        sidebar_icon="mdi:floor-plan",
        config={"mode": "storage"},
        require_admin=False,
        update=True,
    )

    # Save the dashboard card config
    await lovelace_data.dashboards[url_path].async_save({"views": views})
    _LOGGER.info("Schematics dashboard '%s' ready at /%s", title, url_path)
