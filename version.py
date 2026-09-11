#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
Resolves CasterPak's own version - the value stamped into generated
manifests (see vodhls/master_manifest.py's CSMIL master manifest,
casterpak/routes.py's JIT emergency manifest) - not to be confused with a
Python packaging __version__. Single home for this so both call sites read
it the same way instead of each carrying their own copy.

Lives at the repo root, next to VERSION, and follows config.py's existing
convention of flat top-level modules (from config import get_config,
from pathsafety import ..., now from version import CASTERPAK_VERSION).
"""
import os


def read_project_version() -> str:
    """
    Resolve CasterPak's version, in order:

    1. CASTERPAK_VERSION env var - set by the Dockerfile's ARG/ENV at image
       build time (see Dockerfile, docker-compose.yml). This is where a real
       CI/CD release pipeline should inject the actual git tag once one
       exists - nothing here would need to change.
    2. The VERSION file at the repo root - fallback for a bare `flask run`
       or a `docker build` with no --build-arg. Reading it relatively (not
       via __file__) matches config.py's existing convention that CWD is
       the repo root by the time application code runs - see cachedb.DB_PATH
       for the established precedent of relying on that.
    3. 'dev' - last resort, so this never raises.
    """
    env_version = os.environ.get('CASTERPAK_VERSION')
    if env_version:
        return env_version
    try:
        with open('VERSION') as f:
            return f.read().strip()
    except OSError:
        return 'dev'


CASTERPAK_VERSION = read_project_version()
