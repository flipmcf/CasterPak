#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
class EncodingManagerError(Exception):
    """Base class for errors raised by EncodingManager."""
    pass


class EncodingAlreadyInProgressError(EncodingManagerError):
    """Raised when asked to start a background encode for a video that
    already has one in progress (see EncodingManager.in_progress())."""
    pass

from encoding.encodingmanager import EncodingManager