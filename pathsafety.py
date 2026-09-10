#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
Defines what CasterPak considers a valid filename or directory-path segment
coming from a URL, and enforces it by validating - never by mutating. An
invalid name is rejected (raises InvalidPathError); it is never silently
rewritten into something else. See Readme.md's "Valid Filenames" section for
the human-readable version of these rules - keep both in sync.

This module has no Flask dependency on purpose: it's used both by
casterpak/routes.py (a Flask blueprint) and vodhls/csmil.py (plain parsing
logic, no request context). Callers translate InvalidPathError into whatever
response their layer needs (routes.py: abort(422)).
"""

import re

# Letters, digits, '_', '-', '+', '.' - see Readme.md for the reasoning
# behind each. Multiple '.' are allowed (not reserved as a single
# extension separator).
VALID_CHAR_RE = re.compile(r'^[A-Za-z0-9_+.-]+$')


class InvalidPathError(ValueError):
    """Raised when a URL-supplied filename or directory segment isn't valid."""
    pass


def validate_filename(name: str) -> str:
    """
    Validates a single path segment (no '/' allowed in it). Returns `name`
    unchanged if it's valid; raises InvalidPathError otherwise. Never mutates.
    """
    if not name:
        raise InvalidPathError("empty filename")
    if name in ('.', '..'):
        raise InvalidPathError(f"invalid filename: {name!r}")
    if name.startswith('-'):
        # Every subprocess call in this project uses argv-list form, not a
        # shell string, so this isn't shell injection - it's protection
        # against ffmpeg/Bento4 reading a filename as one of their own
        # flags instead of a positional argument.
        raise InvalidPathError(f"filename may not start with '-': {name!r}")
    if ',' in name:
        # ',' is reserved as the CSMIL rendition-list delimiter
        # (see vodhls/csmil.py: csmil_string / from_string).
        raise InvalidPathError(f"filename may not contain ',': {name!r}")
    if not VALID_CHAR_RE.match(name):
        raise InvalidPathError(f"filename contains invalid characters: {name!r}")
    return name


def validate_dirname(dirname: str) -> str:
    """
    Validates a directory path made of '/'-separated segments, each checked
    with validate_filename. An empty string (no subdirectory, top-level) is
    valid. Returns `dirname` unchanged if valid; raises InvalidPathError
    otherwise.

    A leading, trailing, or doubled '/' produces an empty segment (e.g.
    '/etc/passwd'.split('/') == ['', 'etc', 'passwd']), which
    validate_filename rejects as "empty filename" - this is what actually
    closes off a rooted or double-slash path, not special-casing '/' itself.
    """
    if dirname == '':
        return dirname
    for segment in dirname.split('/'):
        validate_filename(segment)
    return dirname
