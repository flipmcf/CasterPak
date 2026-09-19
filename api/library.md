# Library Discovery

Status: **draft / planned.** Not implemented. Originally specified as Priority 1 in `CLAUDE.md`.

Browse the library: list videos and sub-directories under a path, with transcode status.

```http
GET /api/library?path=/projects/2024/&recursive=false

Response 200:
{
  "path": "/projects/2024/",
  "videos": [
    {
      "path": "/projects/2024/final_cut.mp4",
      "filename": "final_cut.mp4",
      "size": 524288000,
      "modified": "2024-12-15T10:30:00Z",
      "duration": 142.5,
      "resolution": "1920x1080",
      "transcodes": {
        "status": "ready",              // "none" | "generating" | "ready" | "error"
        "location": "separate_volume",   // "container" | "filesystem" | "separate_volume"
        "renditions": [
          {"label": "720p", "size": 156000000, "exists": true},
          {"label": "480p", "size": 98000000, "exists": true},
          {"label": "360p", "size": 52000000, "exists": true}
        ],
        "disk_usage": 306000000,
        "expires": null                  // null = persistent, or ISO timestamp
      },
      "urls": {
        "abr": "http://casterpak/i/abr/projects/2024/final_cut.mp4/master.m3u8",
        "single": "http://casterpak/i/projects/2024/final_cut.mp4/index_0_av.m3u8"
      }
    }
  ],
  "directories": [
    "/projects/2024/rough_cuts/",
    "/projects/2024/final_exports/"
  ]
}
```
