"""Assemble the core tool registry."""
from jarvis.tools.base import Registry
from jarvis.tools import apps, windows, files, system, web


def build_registry(mem=None) -> Registry:
    reg = Registry()
    apps.register(reg)
    windows.register(reg)
    files.register(reg)
    system.register(reg)
    web.register(reg)
    if mem is not None:
        from jarvis.memory import tools as memory_tools
        memory_tools.register(reg, mem)
    return reg
