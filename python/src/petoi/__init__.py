"""Control Petoi OpenCat robots from Python."""

from petoi.constants import Joint, Skill
from petoi.errors import ConnectionFailed, PetoiError, RobotError, RobotTimeout
from petoi.protocol import Reply
from petoi.robot import Robot

__version__ = "0.1.0"

__all__ = [
    "ConnectionFailed",
    "Joint",
    "PetoiError",
    "Reply",
    "Robot",
    "RobotError",
    "RobotTimeout",
    "Skill",
    "__version__",
]
