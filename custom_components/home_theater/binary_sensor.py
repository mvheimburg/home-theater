"""A problem sensor for TV sound that is not reaching the receiver."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from .entity import TheaterEntity


async def async_setup_entry(hass, entry, async_add_entities):
    theater = entry.runtime_data
    if theater.tv and theater.receiver:
        async_add_entities([AudioProblem(theater)])


class AudioProblem(TheaterEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, theater):
        super().__init__(theater, "audio")

    @property
    def available(self):
        return self.theater.available(self.theater.tv)

    @property
    def is_on(self):
        return self.theater.arc_problem()

    @property
    def extra_state_attributes(self):
        return {"tv_sound_output": self.theater.attr(self.theater.tv, "sound_output")}
