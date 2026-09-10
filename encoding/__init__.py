class EncodingManagerError(Exception):
    """Base class for errors raised by EncodingManager."""
    pass


class EncodingAlreadyInProgressError(EncodingManagerError):
    """Raised when asked to start a background encode for a video that
    already has one in progress (see EncodingManager.in_progress())."""
    pass

from encoding.encodingmanager import EncodingManager