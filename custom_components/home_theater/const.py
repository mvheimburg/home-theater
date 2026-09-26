"""Home Theater constants."""

DOMAIN = "home_theater"
PLATFORMS = ["binary_sensor", "media_player", "remote", "sensor"]
CONF_TV = "tv"
CONF_RECEIVER = "receiver"
CONF_TV_INPUT = "tv_input"
CONF_TV_AUDIO = "tv_audio"
CONF_MAC = "wol_mac"
CONF_SOURCES = "sources"
RECEIVER = "receiver"
TV = "tv"
# Denon/Marantz name the input that plays the TV's own sound over ARC "TV Audio".
DEFAULT_TV_AUDIO = "TV Audio"
# webOS sound output that sends the TV's sound to an ARC/eARC receiver.
RECEIVER_OUTPUT = "external_arc"
LIVE_TV = "Live TV"
# How long to wait for a device to wake or switch before reporting it.
WAKE_TIMEOUT = 40
SWITCH_TIMEOUT = 8
SWITCH_ATTEMPTS = 3
