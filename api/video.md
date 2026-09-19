# Video Metadata and Status

Status: **draft / planned.** Not implemented. Originally specified as Priority 2 in `CLAUDE.md`.

Detailed metadata and transcode/cache status for one video.

```http
GET /api/video?path=/projects/2024/final_cut.mp4

Response 200:
{
  "source": {
    "path": "/projects/2024/final_cut.mp4",
    "size": 524288000,
    "duration": 142.5,
    "resolution": "1920x1080",
    "bitrate": 5000000,
    "codec": "h264"
  },
  "transcodes": {
    "directory": "/transcodes/projects/2024/final_cut.mp4.transcodes",
    "storage_type": "separate_volume",
    "status": "ready",
    "disk_usage": 306000000,
    "renditions": [
      {
        "label": "720p",
        "filename": "final_cut_720p.mp4",
        "path": "/transcodes/projects/2024/final_cut.mp4.transcodes/final_cut_720p.mp4",
        "size": 156000000,
        "bitrate": 2500000,
        "resolution": "1280x720",
        "status": "ready",
        "created": "2024-04-01T08:00:00Z",
        "last_accessed": "2024-04-06T14:00:00Z"
      }
      // ... other renditions
    ]
  },
  "hls_cache": {
    "status": "cached",
    "segment_count": 142,
    "disk_usage": 8500000,
    "expires": "2024-04-13T14:00:00Z"
  },
  "urls": {
    "abr": "http://casterpak/i/abr/projects/2024/final_cut.mp4/master.m3u8",
    "single": "http://casterpak/i/projects/2024/final_cut.mp4/index_0_av.m3u8"
  }
}
```
