"""Control Petoi OpenCat robots from Python."""

from petoi.errors import ConnectionFailed, PetoiError, RobotError, RobotTimeout

__version__ = "0.1.0"

__all__ = ["ConnectionFailed", "PetoiError", "RobotError", "RobotTimeout", "__version__"]
