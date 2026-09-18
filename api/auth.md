# Authentication

Status: **draft / planned.** Not implemented.

Every `/api` endpoint that changes state or reveals server layout must be authenticated from the
first release. That includes cache removal, transcoding, upload and library browsing.
`CLAUDE.md` originally deferred this. The cache-clearing operations are why it cannot wait.

## Approach

Start with something simple, then move to a standard token scheme:

1. **First:** HTTP Digest authentication.
2. **Later:** JWT / OAuth, for the Plone integration and other clients.

Authentication should live in one place, applied to every `/api` route, so replacing the scheme
does not touch any endpoint.

## Open questions

1. **Digest and multiple workers.** Digest needs the server to hold shared nonce state, and the app
   runs several gunicorn workers. That state has to be shared or the scheme breaks intermittently.
2. **Digest versus alternatives.** The stack now serves HTTPS. Digest's main advantage is
   authenticating without TLS, so a static API key sent as `Authorization: Bearer <key>` may be
   simpler and, unlike Digest, is the same header shape JWT uses later.
3. **Where credentials live:** config file, environment, or the database. How keys or users are
   added and revoked.
4. **Rate limiting.** `CLAUDE.md` calls for it on upload. Should it apply to other endpoints?
