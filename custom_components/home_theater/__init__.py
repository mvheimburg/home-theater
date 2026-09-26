"""Home Theater: one device per room for a TV, an AV receiver and their players."""

from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_platform_entity_service

from .const import DOMAIN, PLATFORMS
from .theater import Theater

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass, config):
    async_register_platform_entity_service(
        hass,
        DOMAIN,
        "use_receiver",
        entity_domain="media_player",
        schema={},
        func="async_use_receiver",
    )
    return True


async def async_setup_entry(hass, entry):
    theater = Theater(hass, entry)
    await theater.load()
    entry.runtime_data = theater
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    theater.start()
    entry.async_on_unload(entry.add_update_listener(update_options))
    return True


async def update_options(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        entry.runtime_data.stop()
        return True
    return False
