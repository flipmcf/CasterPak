#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""Builds the CasterPak URLs a user needs to play a video they uploaded.
The library path is already pathsafety-validated, so it is URL-safe as is."""
import html
import typing as t

from library.settings import Settings


def stream_urls(settings: Settings, library_path: str) -> t.Dict[str, str]:
    """
    single  one rendition, packaged straight from the uploaded file
    abr     adaptive bitrate: CasterPak encodes renditions on first play
            (only offered when CasterPak can do that - see Settings.abr_supported)
    hls     the one to embed: abr when available, otherwise single
    """
    base = settings.casterpak_url
    urls = {'single': f"{base}/i/{library_path}/master.m3u8"}
    if settings.abr_supported:
        urls['abr'] = f"{base}/i/abr/{library_path}/master.m3u8"
    urls['hls'] = urls.get('abr', urls['single'])
    return urls


def embed_html(hls_url: str, element_id: str) -> str:
    """A copy-paste snippet. hls.js (from a CDN) where the browser has Media Source
    Extensions - the same order hls.js's own docs use - else native HLS (iPhone/iPad)."""
    url = html.escape(hls_url, quote=True)
    ident = html.escape(element_id, quote=True)
    return (
        f'<video id="{ident}" controls playsinline style="max-width:100%"></video>\n'
        f'<script src="https://cdn.jsdelivr.net/npm/hls.js@1"></script>\n'
        f'<script>\n'
        f'(function () {{\n'
        f'  var v = document.getElementById("{ident}"), u = "{url}";\n'
        f'  if (window.Hls && Hls.isSupported()) {{ var h = new Hls(); h.loadSource(u); h.attachMedia(v); }}\n'
        f'  else if (v.canPlayType("application/vnd.apple.mpegurl")) {{ v.src = u; }}\n'
        f'}})();\n'
        f'</script>'
    )
