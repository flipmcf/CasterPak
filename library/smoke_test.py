#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
End-to-end check of a RUNNING library + CasterPak pair, over plain HTTP:

    register -> log in -> upload -> list -> fetch the playlist -> fetch a segment

    ./bin/python -m library.smoke_test \\
        --library http://localhost:5001 --casterpak http://localhost:5000 \\
        --file tests/assets/test-video.mp4

Point it at a local or staging stack. It creates a real user and uploads a
real file, so do not aim it at production. (The same requests, for a human, are
in api/postman/.)  If the library has registration = closed, create a user with
`flask --app library create-user` and pass --username / --password.
"""
import argparse
import os
import sys
import uuid

import requests


def step(ok, message):
    print(('PASS  ' if ok else 'FAIL  ') + message)
    if not ok:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--library', default='http://localhost:5001')
    ap.add_argument('--casterpak', default=None, help="defaults to the URL the library says to use")
    ap.add_argument('--file', required=True, help='an .mp4 to upload')
    ap.add_argument('--username')
    ap.add_argument('--password', default='smoke-test-password-1')
    ap.add_argument('--invite-code')
    args = ap.parse_args()

    lib = args.library.rstrip('/')
    http = requests.Session()
    http.headers['Accept'] = 'application/json'

    health = http.get(f'{lib}/api/health', timeout=10)
    step(health.status_code == 200, f"library is up ({health.json()})")

    username = args.username
    if not username:
        username = f"smoke-{uuid.uuid4().hex[:8]}"
        payload = {'username': username, 'password': args.password}
        if args.invite_code:
            payload['invite_code'] = args.invite_code
        r = http.post(f'{lib}/api/users', json=payload, timeout=10)
        step(r.status_code == 201, f"registered {username}" if r.ok else f"register failed: {r.status_code} {r.text}")

    r = http.post(f'{lib}/api/auth/login', json={'username': username, 'password': args.password}, timeout=10)
    step(r.status_code == 200, f"logged in as {username}")
    tokens = r.json()
    auth = {'Authorization': f"Bearer {tokens['access_token']}"}

    r = requests.post(f'{lib}/api/upload', timeout=10, files={'file': ('smoke.mp4', b'x')})
    step(r.status_code == 401, "upload without a token is refused (401)")

    name = f"smoke-{uuid.uuid4().hex[:8]}.mp4"
    with open(args.file, 'rb') as f:
        r = http.post(f'{lib}/api/upload', headers=auth, timeout=600,
                      data={'path': 'smoke-tests'}, files={'file': (name, f, 'video/mp4')})
    step(r.status_code == 201, f"uploaded {name}" if r.ok else f"upload failed: {r.status_code} {r.text}")
    video = r.json()

    r = http.get(f'{lib}/api/videos', headers=auth, timeout=10)
    step(r.status_code == 200 and video['path'] in [v['path'] for v in r.json()['videos']],
         "the upload shows up in the listing")

    url = video['urls']['single']
    if args.casterpak:
        url = url.replace(url.split('/i/')[0], args.casterpak.rstrip('/'), 1)
    r = requests.get(url, timeout=120)
    step(r.status_code == 200 and r.text.startswith('#EXTM3U'), f"CasterPak serves the master playlist ({url})")

    child = next(l for l in r.text.splitlines() if l and not l.startswith('#'))
    if not child.startswith('http'):
        child = url.rsplit('/', 1)[0] + '/' + child
    if args.casterpak:
        child = child.replace(child.split('/i/')[0], args.casterpak.rstrip('/'), 1)
    r = requests.get(child, timeout=120)
    step(r.status_code == 200 and '#EXTINF' in r.text, "CasterPak serves the media playlist")

    segment = next(l for l in r.text.splitlines() if l and not l.startswith('#'))
    if not segment.startswith('http'):
        segment = child.rsplit('/', 1)[0] + '/' + segment
    if args.casterpak:
        segment = segment.replace(segment.split('/i/')[0], args.casterpak.rstrip('/'), 1)
    r = requests.get(segment, timeout=120)
    step(r.status_code == 200 and len(r.content) > 0, f"CasterPak serves a segment ({len(r.content)} bytes)")

    print(f"\nAll good. Play it: {video['urls']['hls']}")


if __name__ == '__main__':
    main()
