# Examples

Plain HTML, no build step. Open them from disk or serve them from anywhere.

| File | Needs an account? | What it shows |
|---|---|---|
| `player.html` | **No** | The minimum a web page needs to play a CasterPak stream: `<video>` + hls.js. `player.html?src=<stream URL>` |
| `library.html` | To upload | Sign in / create account, upload with a progress bar, list your videos, play them, copy embed code |

Local demo (see `library/README.md` for the servers):

```
open examples/library.html          # API defaults to http://localhost:5001
```

Both pages load [hls.js](https://github.com/video-dev/hls.js) from the jsDelivr CDN for browsers that
can't play HLS natively (everything but Safari). For an intranet with no internet, download it and
change the `<script src>`.

The streaming URLs work from any origin: CasterPak answers with `Access-Control-Allow-Origin: *`.
The library API sends CORS headers too (`[library] cors_origins`, default `*`, safe because the API
uses bearer tokens rather than cookies).
