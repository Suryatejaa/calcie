"""Skill modules for Calcie task routing."""

from .app_access import AppAccessSkill
from .agentic_computer_use import AgenticComputerUseSkill
from .coding import CodingSkill
from .computer_control import ComputerControlSkill
from .screen_memory import ScreenMemoryPipeline
from .screen_vision import ScreenVisionSkill
from .searching import SearchingSkill

__all__ = [
    "AppAccessSkill",
    "AgenticComputerUseSkill",
    "CodingSkill",
    "ComputerControlSkill",
    "ScreenMemoryPipeline",
    "ScreenVisionSkill",
    "SearchingSkill",
]
