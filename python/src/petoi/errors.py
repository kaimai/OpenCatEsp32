class PetoiError(Exception):
    """Base class for every error raised by petoi."""


class ConnectionFailed(PetoiError):
    """The robot could not be found or the link could not be opened."""


class RobotError(PetoiError):
    """The robot rejected or failed a command."""


class RobotTimeout(RobotError):
    """The robot did not confirm a command in time."""
