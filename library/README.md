# CasterPak Library

User accounts, upload, listing and embed URLs for the library CasterPak streams from.
Why it is a separate service, and what it can't do yet: [DESIGN.md](DESIGN.md).

## Run it locally (development)

```bash
# 1. config: the library reads config.ini like CasterPak does
cp config_example.ini config.ini            # if you haven't

# 2. the two required settings, via environment
export CASTERPAK_LIBRARY_JWT_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
export CASTERPAK_LIBRARY_REGISTRATION=open  # a dev convenience; the default is 'closed'
export CASTERPAK_FILESYSTEM_VIDEOPARENTPATH=$HOME/casterpak-library   # where users' folders will live

# 3. run both services
./bin/python -m flask --app app run -p 5000            # CasterPak  (plays)
./bin/python -m flask --app library run -p 5001        # Library    (accounts + upload)
```

Then open `examples/library.html`, or run the checks below.

With the default `registration = closed`, make accounts on the command line instead:

```bash
./bin/python -m flask --app library create-user alice --email alice@example.com
./bin/python -m flask --app library list-users
```

## Run it with Docker

```bash
# in .env:  CASTERPAK_LIBRARY_JWT_SECRET=<48 random chars>   (see .env.example)
docker compose --profile library up -d --build
docker compose exec library flask --app library create-user alice
```

`docker compose up` without `--profile library` starts exactly what it always did.
nginx sends `/api/` to the library and everything else to CasterPak.

## Use S3 as the library

Set `input_type = s3` and the `[s3]` section (see [docs/s3-input.md](../docs/s3-input.md)). Both services
then read/write the same bucket and prefix; nothing else changes. Uploads land at
`s3://<bucket>/<prefix><user>/<path>`.

## Check that it works

```bash
pytest library                                       # unit + API tests, no network needed

# end to end against running services:
./bin/python -m library.smoke_test --library http://localhost:5001 \
    --casterpak http://localhost:5000 --file tests/assets/test-video.mp4

# Postman: import api/postman/casterpak-library.postman_collection.json and
# api/postman/casterpak-local.postman_environment.json. Or, headless:
npx newman run api/postman/casterpak-library.postman_collection.json \
    -e api/postman/casterpak-local.postman_environment.json --working-dir .
```

**Do not aim the smoke test or the Postman collection at production**: they create users and upload files.
See [docs/test-access.md](../docs/test-access.md).

## Settings

All in `[library]` in `config_example.ini`, each overridable as `CASTERPAK_LIBRARY_<OPTION>`:
`casterpak_url`, `database_url`, `jwt_secret` (required), `registration`, `registration_code`,
`access_token_minutes`, `refresh_token_days`, `max_upload_mb`, `max_user_mb`, `allowed_extensions`,
`cors_origins`, `abr`.
