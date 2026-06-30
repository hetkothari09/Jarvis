from jarvis.gui.orb import orb_color
from jarvis.gui.theme import IDLE, BUSY, ERROR


def test_orb_color_maps_state():
    assert orb_color("idle") == IDLE
    assert orb_color("busy") == BUSY
    assert orb_color("error") == ERROR
    assert orb_color("anything-else") == IDLE
