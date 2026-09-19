# Storage Backend Management

Status: **draft / planned.** Not implemented. Originally specified as Priority 4 in `CLAUDE.md`.

List configured storage backends and their connection health.

```http
GET /api/backends

Response 200:
{
  "backends": [
    {
      "name": "default",
      "type": "filesystem",
      "path": "/mnt/data/videos",
      "readonly": true,
      "connected": true
    },
    {
      "name": "s3-archive",
      "type": "s3",
      "bucket": "video-archive",
      "region": "us-east-1",
      "prefix": "videos/",
      "connected": false,
      "error": "Invalid credentials"
    }
  ]
}
```
