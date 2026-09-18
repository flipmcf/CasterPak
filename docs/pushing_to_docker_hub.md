# Releasing to Docker Hub

This is a "publish to production" move. Don't leave any debug stuff in, and make
sure the tests pass first.

Two images are published, both tagged with the same version:

- `flipmcf/casterpak` - the Flask app
- `flipmcf/casterpak-proxy` - the nginx front end

In the steps below, `X.Y.Z-alpha` is the new version, for example `0.9.1-alpha`.

## 1. Bump the version

Update every place the old version appears, then add an entry to `CHANGELOG.md`:

```
grep -rn "<old version>" --exclude-dir=.git --exclude=CHANGELOG.md .
```

Currently that is `VERSION`, `docker-compose.yml` (three places), `.env.example`
and the title of `docs/Hosting-instructions`.

## 2. Test

```
./bin/pytest --ignore=tests/containertests
./bin/pytest tests/containertests/run_tests.py -vv
```

The container tests rebuild the images and run `docker compose down -v` when they
finish. That replaces any stack running on the machine and deletes the
`casterpak_casterpak_data` volume, so don't run them on a host that is serving
traffic.

## 3. Merge and tag

Merge to `master`, then tag the merge commit and push the tag:

```
git checkout master && git pull
git tag -a X.Y.Z-alpha -m "X.Y.Z-alpha"
git push origin X.Y.Z-alpha
```

## 4. Build

Build from the tagged commit, with the version set explicitly so the image tags
and the version baked into the app can't come from a stale `.env`:

```
CASTERPAK_VERSION=X.Y.Z-alpha docker compose build --no-cache
```

## 5. Push

```
docker login        # if your token has expired
docker push flipmcf/casterpak:X.Y.Z-alpha
docker push flipmcf/casterpak-proxy:X.Y.Z-alpha
```

## 6. Move `latest` (optional)

`latest` is an ordinary tag. Docker never moves it for you; it points at whatever
was last pushed under that name, and it's what `docker pull flipmcf/casterpak`
uses when no tag is given. Production deployments should pin a version instead.

To move it, add the `latest` name to the same image. This is a second name for
one image, not a rebuild:

```
docker tag flipmcf/casterpak:X.Y.Z-alpha        flipmcf/casterpak:latest
docker tag flipmcf/casterpak-proxy:X.Y.Z-alpha  flipmcf/casterpak-proxy:latest
docker push flipmcf/casterpak:latest
docker push flipmcf/casterpak-proxy:latest
```

## 7. Verify

Each `latest` should have the same image ID as the version it was tagged from:

```
docker images | grep flipmcf
```

Then confirm what's on Docker Hub. The digests for `latest` and `X.Y.Z-alpha`
must match, for both images:

```
docker buildx imagetools inspect flipmcf/casterpak:latest | grep Digest
docker buildx imagetools inspect flipmcf/casterpak:X.Y.Z-alpha | grep Digest
docker buildx imagetools inspect flipmcf/casterpak-proxy:latest | grep Digest
docker buildx imagetools inspect flipmcf/casterpak-proxy:X.Y.Z-alpha | grep Digest
```

Finally, check that the app image carries the right version:

```
docker run --rm --entrypoint sh flipmcf/casterpak:X.Y.Z-alpha -c 'echo $CASTERPAK_VERSION'
```
