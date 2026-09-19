# Upload New Video

Status: **draft / planned.** Not implemented. Originally specified as Priority 3 in `CLAUDE.md`.

Accept a video upload into the library and return a playable URL.

```http
POST /api/upload
Content-Type: multipart/form-data

{
  "file": <binary>,
  "path": "/projects/2024/",         // Optional: target directory
  "filename": "new_video.mp4"        // Optional: override filename
}

Response 201:
{
  "path": "/projects/2024/new_video.mp4",
  "size": 450000000,
  "urls": {
    "abr": "http://casterpak/i/abr/projects/2024/new_video.mp4/master.m3u8",
    "single": "http://casterpak/i/projects/2024/new_video.mp4/index_0_av.m3u8"
  }
}
```
