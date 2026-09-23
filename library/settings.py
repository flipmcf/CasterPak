#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
Settings for the library service, read from the same config.ini (and the
same CASTERPAK_<SECTION>_<OPTION> env overrides) as the streaming service.

The library never has a storage location of its own. It writes exactly where
CasterPak reads - [filesystem] videoParentPath or the [s3] bucket/prefix,
chosen by [input] input_type - so an uploaded file is streamable the moment
it lands, with nothing to keep in sync.
"""
import typing as t
from configparser import ConfigParser
from dataclasses import dataclass, field

import s3client
from vodhls import ConfigurationError

MIN_SECRET_LENGTH = 32


@dataclass
class Settings:
    casterpak_url: str
    database_url: str
    jwt_secret: str
    input_type: str                          # 'filesystem' | 's3'
    library_root: str                        # filesystem only
    registration: str = 'closed'             # closed | invite | open
    registration_code: str = ''
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    max_upload_mb: int = 2048
    max_user_mb: int = 0                     # 0 = unlimited
    allowed_extensions: t.Tuple[str, ...] = ('mp4', 'm4v', 'mov', 'mkv', 'webm')
    cors_origins: t.Tuple[str, ...] = ('*',)
    abr: str = 'auto'                        # auto | true | false
    reserved_usernames: t.FrozenSet[str] = field(default_factory=lambda: RESERVED_USERNAMES)

    @property
    def abr_supported(self) -> bool:
        """Whether /i/abr/ URLs should be offered. 'auto' follows what
        CasterPak itself can do today: it auto-encodes only from a local
        filesystem library (see docs/s3-input.md)."""
        if self.abr == 'auto':
            return self.input_type == 'filesystem'
        return self.abr == 'true'


# Top-level names that CasterPak's own URL space or the storage layout
# already use. A user named 'abr' would make /i/abr/x.mp4/... ambiguous.
RESERVED_USERNAMES = frozenset({
    'abr', 'api', 'i', 'd', 'c', 'admin', 'administrator', 'root', 'system',
    'static', 'examples', 'testing', 'protected_media', 'library',
    'casterpak', 'support', 'null', 'none', 'anonymous',
})


def _csv(value: str) -> t.Tuple[str, ...]:
    return tuple(v.strip().lower().lstrip('.') for v in value.split(',') if v.strip())


def load_settings(config: ConfigParser) -> Settings:
    def opt(option, fallback=''):
        return config.get('library', option, fallback=fallback).strip()

    input_type = config.get('input', 'input_type', fallback='filesystem').strip().lower()
    if input_type not in ('filesystem', 's3'):
        raise ConfigurationError(
            f"the library can only write where CasterPak reads, and input_type = {input_type!r} "
            f"is not writable. Use 'filesystem' or 's3'.")

    if input_type == 's3':
        s3client.bucket_and_prefix(config)          # fail early if [s3] is incomplete
        root = ''
    else:
        root = config.get('filesystem', 'videoParentPath', fallback='').strip()
        if not root:
            raise ConfigurationError("[filesystem] videoParentPath is not configured")

    registration = opt('registration', 'closed').lower()
    if registration not in ('closed', 'invite', 'open'):
        raise ConfigurationError(f"[library] registration must be closed, invite or open - got {registration!r}")
    if registration == 'invite' and len(opt('registration_code')) < 8:
        raise ConfigurationError("[library] registration = invite needs a registration_code of 8+ characters")

    secret = opt('jwt_secret')
    if len(secret) < MIN_SECRET_LENGTH:
        raise ConfigurationError(
            f"[library] jwt_secret must be at least {MIN_SECRET_LENGTH} characters. Set it with the "
            f"CASTERPAK_LIBRARY_JWT_SECRET environment variable, e.g.  "
            f"python3 -c 'import secrets; print(secrets.token_urlsafe(48))'")

    abr = opt('abr', 'auto').lower()
    if abr not in ('auto', 'true', 'false'):
        raise ConfigurationError(f"[library] abr must be auto, true or false - got {abr!r}")

    return Settings(
        casterpak_url=opt('casterpak_url', 'http://localhost:5000').rstrip('/'),
        database_url=opt('database_url', 'sqlite:////var/lib/casterpak/library/library.db'),
        jwt_secret=secret,
        input_type=input_type,
        library_root=root,
        registration=registration,
        registration_code=opt('registration_code'),
        access_token_minutes=int(opt('access_token_minutes', '15')),
        refresh_token_days=int(opt('refresh_token_days', '30')),
        max_upload_mb=int(opt('max_upload_mb', '2048')),
        max_user_mb=int(opt('max_user_mb', '0')),
        allowed_extensions=_csv(opt('allowed_extensions', 'mp4,m4v,mov,mkv,webm')),
        cors_origins=tuple(o.strip() for o in opt('cors_origins', '*').split(',') if o.strip()),
        abr=abr,
    )
