#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
Input rules for the library service. Same principle as pathsafety.py: an
invalid value is REJECTED with a message saying why, never silently rewritten
into something else. Anything that becomes part of a path CasterPak will serve
is checked with pathsafety itself, so the two can never disagree.
"""
import re
import typing as t

from pathsafety import InvalidPathError, validate_dirname, validate_filename

USERNAME_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{2,31}$')
EMAIL_RE = re.compile(r'^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$')
MIN_PASSWORD = 10
MAX_PASSWORD = 128          # scrypt cost grows with input; don't hash megabytes


class ValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def validate_username(username: str, reserved: t.Iterable[str]) -> str:
    if not isinstance(username, str) or not USERNAME_RE.match(username):
        raise ValidationError(
            'invalid_username',
            "username must be 3-32 characters: lowercase letters, digits, '_' or '-', "
            "starting with a letter or digit")
    if username in reserved:
        raise ValidationError('reserved_username', f"'{username}' is reserved")
    return username


def validate_email(email: t.Optional[str]) -> t.Optional[str]:
    if email in (None, ''):
        return None
    if not isinstance(email, str) or len(email) > 254 or not EMAIL_RE.match(email):
        raise ValidationError('invalid_email', "that doesn't look like an email address")
    return email.lower()


def validate_password(password: str, username: str) -> str:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        raise ValidationError('weak_password', f"password must be at least {MIN_PASSWORD} characters")
    if len(password) > MAX_PASSWORD:
        raise ValidationError('invalid_password', f"password must be at most {MAX_PASSWORD} characters")
    if password.lower() == username.lower():
        raise ValidationError('weak_password', "password must not be the same as the username")
    return password


NAME_HINT = ("letters, digits, '_', '-', '+' and '.' only (no spaces or commas), "
             "not starting with '-'")


def validate_upload_name(filename: t.Optional[str], allowed_extensions: t.Iterable[str]) -> str:
    if not filename:
        raise ValidationError('invalid_filename', "no filename was given")
    try:
        validate_filename(filename)
    except InvalidPathError as e:
        raise ValidationError(
            'invalid_filename',
            f"{e}. A filename may use {NAME_HINT}. Rename the file, or send a valid 'filename' field.")
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    allowed = tuple(allowed_extensions)
    if ext not in allowed:
        raise ValidationError('unsupported_type',
                              f"'.{ext}' files are not accepted; allowed: {', '.join('.' + a for a in allowed)}")
    return filename


def validate_directory(directory: t.Optional[str]) -> str:
    """A target directory inside the user's own directory. One leading and
    one trailing '/' are tolerated (so '/trips/2026/' works); anything else
    odd - '..', '//', spaces - is rejected by pathsafety."""
    if directory in (None, '', '/'):
        return ''
    segments = directory.split('/')
    if segments[0] == '':
        segments = segments[1:]
    if segments and segments[-1] == '':
        segments = segments[:-1]
    cleaned = '/'.join(segments)
    try:
        if not cleaned:                     # '//' and friends: not a path
            raise InvalidPathError(f"invalid directory: {directory!r}")
        validate_dirname(cleaned)
    except InvalidPathError as e:
        raise ValidationError('invalid_path', f"{e}. A directory may use {NAME_HINT}.")
    return cleaned


# --- content sniffing -------------------------------------------------------

_ISO_BMFF_BOXES = (b'ftyp', b'moov', b'mdat', b'free', b'skip', b'wide', b'pnot')
_EBML_MAGIC = b'\x1a\x45\xdf\xa3'


def sniff_matches_extension(header: bytes, filename: str) -> bool:
    """True if the first bytes of the file look like the container its name
    claims. A cheap gate against a renamed .exe or .html, not a validator -
    ffprobe on ingest is the real one (see library/DESIGN.md, open questions)."""
    ext = filename.rsplit('.', 1)[-1].lower()
    if ext in ('mp4', 'm4v', 'mov'):
        return len(header) >= 8 and header[4:8] in _ISO_BMFF_BOXES
    if ext in ('mkv', 'webm'):
        return header[:4] == _EBML_MAGIC
    # An extension the operator added to allowed_extensions (avi, ...) that
    # we have no signature for: trust the allowlist rather than refuse it.
    return True
