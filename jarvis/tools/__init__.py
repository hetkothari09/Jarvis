"""Assemble the core tool registry."""
from jarvis.tools.base import Registry
from jarvis.tools import apps, windows, files, system, web


def build_registry() -> Registry:
    reg = Registry()
    apps.register(reg)
    windows.register(reg)
    files.register(reg)
    system.register(reg)
    web.register(reg)
    return reg
