# CasterPak-Plone Integration Project Context

## Container Workflow (claude-sandbox)

This repo is also worked on inside ephemeral containers via `~/Projects/claude-sandbox`
(`claude-here`, run from this directory). Mechanics worth knowing if you're reading this from
inside one:

- **Fresh copy every launch.** The entrypoint copies this whole repo into `/work`, reverts any
  uncommitted changes in *that copy*, and checks out (or creates) a `claude` branch. The container
  is destroyed on exit (`--rm`) - nothing persists there between sessions except what got pushed to
  GitHub. Host files are never modified.
- **This file persists because it's tracked.** CLAUDE.md used to be gitignored here, which worked
  but relied on a subtlety (the container's cleanup step, `git clean -fd`, only removes files
  neither tracked nor staged - it doesn't need `.gitignore` for protection, but a fully untracked
  file did depend on it). It's now a normal tracked file instead, so it behaves like everything
  else in the repo: commit it and it survives, same as any other change.
- **You'll start on a `claude` branch, not whatever was last worked on.** To pick up one of the
  branches/PRs mentioned below, `git fetch` and `git checkout <branch>` first.
- **Never merge a PR from inside the container** - claude-sandbox's own rule. Create/push/update
  PRs freely; a human merges.

## Recent Work (snapshot as of 2026-09-23)

Not a full history - see `CHANGELOG.md` and `git log` for that. This is what a fresh session should
know before re-deriving it.

**Shipped, on master (PRs #40-#48, all merged):**
- **CSMIL fix:** rendition filenames are plain concatenation (`prefix + label + suffix`), no
  auto-inserted `_`. Fixes bring-your-own-transcode naming (files like `bbb_360p.avi` needed
  `bbb_,360p,...` in the URL, not `bbb,360p,...`) and a double-underscore 404 bug. `vodhls/csmil.py`.
- **Released 0.9.1-alpha**, pushed to Docker Hub (`flipmcf/casterpak`, `flipmcf/casterpak-proxy`,
  including `latest`). Full release steps are in `docs/pushing_to_docker_hub.md`.
- **CasterPak is container-only now.** Bare-metal/systemd deployment (`casterpak.service`) and
  crontab-driven cleanup (`crontab.tpl`) are deleted. Cleanup and encoding are scheduled exclusively
  by gunicorn's master process (`on_starting` hook in `gunicorn.conf.py`) - there is no other
  supported way to run this in production.
- **Logging architecture rewritten.** The rule: a CasterPak logger never opens its own destination -
  it borrows gunicorn's handlers (`applogging.use_gunicorn_handlers()`), called from both the worker
  (`casterpak/__init__.py`'s `setup_gunicorn_logging`) and the master (`gunicorn.conf.py`'s
  `on_starting`). Every re-pointed logger sets `propagate = False`, or it double-logs through root's
  fallback handler too. Per-subsystem output is tagged (`[vodhls]`/`[cleanup]`/`[encoding]`) via a
  `logging.Filter` (`applogging.TagFilter`) - deliberately not a Formatter, since a Formatter lives
  on the Handler (which gets swapped out wholesale), while a Filter lives on the Logger and survives
  that.
- **`api/` folder added** - draft design docs for the management API (`library.md`, `video.md`,
  `upload.md`, `backends.md`, `transcode.md`, `cache.md`, `auth.md`), moved out of this file (which
  was untracked before today, so those specs were never actually version-controlled). Nothing in
  `api/` is implemented - each file ends with its own "Open questions."
- **`cleanup/cleaner.py` runs standalone for debugging:** `./bin/python -m cleanup.cleaner` from the
  repo root (must be `-m`, not a direct path - see Readme's "Running cleanup manually"). This
  project has no installed package (see below), so it depends on being launched with the repo root
  as `sys.path[0]`, same as gunicorn/flask/pytest already do.

**Library service + S3 input (branch `s3-input-and-library`, see its PR):**
- **Decision (user's, 2026-09-23): CasterPak does NOT grow an API.** It stays a bring-your-own-library
  streamer. The library you bring is a *separate service* in `library/` (same repo, same image, own
  gunicorn via `gunicorn.library.conf.py` - never `gunicorn.conf.py`, which starts cleanup/encoding
  threads). Users, JWT auth, upload, per-user listing, embed URLs. Design: `library/DESIGN.md`.
  It shares only the storage layout with CasterPak; each user gets a directory `<root>/<username>/`.
- **S3 input:** `vodhls/media_manifest_s3.py`, `s3client.py` (shared boto3 client), `docs/s3-input.md`.
  Not yet supported on S3: `/i/abr/` (route and `EncodingManager` read `[filesystem] videoParentPath`).
- Single-bitrate URL is `/i/<path>/master.m3u8` (`index_0_av.m3u8` is the *child* playlist).
- Tests need no AWS: moto (`requirements-dev.txt`). Real-S3 / production access: `docs/test-access.md`.
- Never aim `library/smoke_test.py` or `api/postman/` at production - they create users and files.

**Loose end:** `review_44.md` at the repo root is scratch PR-review notes, marked "never to be
committed" by its own first line. Delete it once you're done referring back to it.

**Decisions already made, not open for re-litigation without a real reason:**
- **No ladder database.** A per-video rendition ladder, if/when built, is a SMIL 3.0 file (Chapter 6,
  Content Control) stored with its transcodes - not a database record. See `api/cache.md`.
- **No bare-metal, no cron, ever.** Container + gunicorn is the only supported production path.
- **This project is not an installed package.** `setup.py` exists but its own comment says it's
  decorative ("indexed by bots," not `pip install`-able). Every top-level module (`config.py`,
  `cachedb.py`, `pathsafety.py`, `applogging.py`, `version.py`) is a flat module, importable only
  because the repo root happens to be on `sys.path` - true for every real entry point, but not for a
  script launched by its own nested path. Making this a real installed package would remove that
  whole class of bug permanently; judged out of scope for now, not forgotten.

## Project Overview

**Goal**: Integrate CasterPak (Python/Flask HLS video streaming server) with Plone CMS to provide zero-migration video streaming capabilities.

**Key Value Proposition**: CasterPak streams video from existing libraries without requiring content migration or pre-encoding. It generates HLS streams on-demand and caches them intelligently.

---

## CasterPak Architecture

### What CasterPak Is
- **Flask-based HLS streaming server** with intelligent caching
- **On-demand stream packager**: Converts video files to HLS on first request
- **Multi-storage backend support**: Local filesystem (working), S3 (high priority), Azure, HTTP
- **Adaptive Bitrate (ABR) support**: Auto-generates multi-bitrate renditions
- **Replacement for**: Akamai Media Services On Demand (MSOD)

### Repository
- GitHub: https://github.com/flipmcf/CasterPak
- Language: Python 3 (Flask)
- Key dependencies: Bento4 (mp42hls), FFmpeg, SQLite

### Current Status
- ✅ Single-bitrate HLS streaming works
- ✅ CSMIL URL syntax (Akamai-compatible) implemented, fixed to be pure prefix+label+suffix
  concatenation (see "Recent Work" above)
- ✅ ABR auto-encoding (`/abr` endpoint) working, released as 0.9.1-alpha
- 🔨 REST API for discovery/metadata: **designed**, not built - see `api/*.md`
- 🔨 S3 backend support (stubbed but not complete)

---

## Storage Architecture

### Three Storage Layers

#### 1. Source Video Library (Read-Only Archive)
```
/mnt/data/videos/
└── projects/
    └── 2024/
        └── final_cut.mp4          # Original source video
```

**Configuration**: `[filesystem]` section in config.ini
- `videoParentPath`: Where source videos live
- Can be: local filesystem, network mount, S3 bucket (future)

#### 2. Transcode Cache (Read/Write)
```
/transcodes/projects/2024/
└── final_cut.mp4.transcodes/
    ├── final_cut_720p.mp4         # Auto-generated rendition
    ├── final_cut_480p.mp4         # Auto-generated rendition
    ├── final_cut_360p.mp4         # Auto-generated rendition
    └── .metadata.json             # Encoding status
```

**Storage Options**:
- **Container volume** (default): Ephemeral, lost on restart
- **Alongside source**: Write `.transcodes` dirs next to originals (requires write access)
- **Separate volume**: Dedicated fast storage (recommended production)

**Configuration**: `[input]` section
- `videoCachePath`: Where transcodes are cached

#### 3. HLS Segment Cache (TTL-Based)
```
/tmp/segments/projects/2024/final_cut.mp4/
├── index_0_av.m3u8                # Media playlist
├── segment1_0_av.ts               # HLS segment
├── segment2_0_av.ts
└── ...
```

**Configuration**: `[output]` section
- `segmentParentPath`: Where HLS segments live
- `[cache]` section controls TTL and cleanup

---

## URL Routing Patterns

### Single-Bitrate Streaming
```
http://casterpak/i/projects/2024/final_cut.mp4/index_0_av.m3u8
```
- **Behavior**: Generates HLS from source video directly
- **Use case**: Simple streaming, no encoding needed

### Adaptive Bitrate Streaming (CSMIL)
```
http://casterpak/i/projects/2024/final_cut_,720p,480p,360p,.mp4.csmil/master.m3u8
```
- **Behavior**: Expects pre-encoded renditions (e.g., `final_cut_720p.mp4`)
- **Use case**: When you've already encoded multiple bitrates externally

### Adaptive Bitrate Streaming (Auto-Encode) - IN DEVELOPMENT
```
http://casterpak/i/abr/projects/2024/final_cut.mp4/master.m3u8
```
- **Behavior**: 
  1. Check if `.transcodes/` exists with renditions
  2. If yes → 302 redirect to CSMIL endpoint
  3. If no → Start background encoding + emergency JIT stream
- **Emergency stream**: Quick, low-quality encoding for immediate playback
- **Background encoding**: High-quality multi-bitrate renditions (slow)

---

## Key Code References

### CSMIL Descriptor
**File**: `vodhls/csmil.py`

```python
class CsmilDescriptor:
    """Parses and constructs CSMIL URL strings"""
    
    def __init__(self, dirname: str, basename: str, ext: str, bitrates: list):
        self.dirname = dirname
        self.basename = basename
        self.ext = ext
        self.bitrates = sorted([str(b) for b in bitrates])  # Always sorted
    
    @classmethod
    def from_string(cls, csmil_str: str) -> 'CsmilDescriptor':
        """Parse: '/dir/video_,720p,480p,360p,.mp4'"""
        # Implementation strips '.csmil', splits on commas, sanitizes
        pass
    
    @property
    def rendition_filenames(self) -> list:
        """Returns: ['video_720p.mp4', 'video_480p.mp4', 'video_360p.mp4']"""
        return [f"{self.basename}_{b}{self.ext}" for b in self.bitrates]
```

**Key insight**: CSMIL assumes rendition files already exist on disk. It just constructs the master manifest.

### ABR Endpoint (Work in Progress)
**File**: `casterpak/routes.py` (or similar)

```python
@bp.route('/i/abr/<path:dir_name>/master.m3u8')
def abr_manifest(dir_name: str):
    """
    State Manager for ABR streaming.
    If encodings exist → redirect to CSMIL.
    If not → start background encoding + emergency stream.
    """
    encoder = EncodingManager(video_file)
    
    if encoder.renditions_exist():
        # Renditions ready → redirect to CSMIL
        csmil_string = CsmilDescriptor(dirname, basename, ext, encoder.bitrates).csmil_string
        return redirect(f"/i/{csmil_string}.csmil/master.m3u8", code=302)
    else:
        # Start heavy background encoding
        encoder.start_background_encoding()
        
        # Start lightweight JIT emergency stream
        trigger_emergency_encoding(
            input_filepath=source_file,
            output_dir=output_dir,
            manifest_path=manifest_path
        )
        
        # Return master manifest pointing to emergency stream
        return Response(master_m3u8_text, mimetype='application/vnd.apple.mpegurl')
```

### Configuration File
**File**: `config_example.ini`

Key sections:
- `[application]`: Debug settings
- `[cache]`: TTL and size limits for segments and input files
- `[input]`: Storage backend type, cache settings
- `[output]`: Segment path, server name for URL generation
- `[bento4]`, `[ffmpeg]`: Binary paths
- `[encoding_ladder]`: Rendition definitions (720p, 480p, 360p)
- `[filesystem]`: Source video path, input caching behavior

---

## Plone Integration Requirements

### Content Type: `casterpak.video`

**Purpose**: Metadata-only content type that references videos in CasterPak's library.

**Schema** (conceptual):
```python
class ICasterPakVideo(model.Schema):
    # Core reference to video in CasterPak library
    source_path = schema.TextLine(
        title="Video Path",
        description="Path in CasterPak library (e.g., /projects/2024/final_cut.mp4)",
        required=True
    )
    
    # Streaming configuration
    streaming_mode = schema.Choice(
        title="Streaming Mode",
        values=["single", "abr"],
        default="abr",
        description="Single-bitrate or adaptive bitrate streaming"
    )
    
    # Cached metadata (refreshed from CasterPak API)
    duration = schema.Float(required=False)
    resolution = schema.TextLine(required=False)
    file_size = schema.Int(required=False)
    transcode_status = schema.TextLine(required=False)  # "none", "generating", "ready"
    
    # Computed property for embed URL
    @property
    def hls_url(self):
        if self.streaming_mode == "abr":
            return f"http://casterpak/i/abr{self.source_path}/master.m3u8"
        else:
            return f"http://casterpak/i{self.source_path}/index_0_av.m3u8"
```

**Key Design Principle**: Plone does NOT store video files. It only stores metadata and references.

### User Workflows

#### Workflow 1: Browse and Link to Existing Video
1. User clicks "Add Video" in Plone
2. Plone widget calls `GET /api/library` to show browsable tree of CasterPak library
3. User selects video from tree
4. Plone creates `casterpak.video` object with selected path
5. Video player embeds using computed `hls_url` property

#### Workflow 2: Upload New Video
1. User uploads `.mp4` file via Plone form
2. Plone calls `POST /api/upload` (uploads to CasterPak)
3. CasterPak stores to configured backend (filesystem/S3)
4. CasterPak returns path and metadata
5. Rest of workflow same as Workflow 1

---

## API Requirements (To Be Built in CasterPak)

The API specs (library, video, upload, backends) now live in `api/`. See `api/README.md`.
Original priority order: 1 library, 2 video, 3 upload, 4 backends.

---

## Development Priorities

### CasterPak Work Required

1. **REST API Implementation** (High Priority)
   - `GET /api/library` - Browse video library
   - `GET /api/video` - Get detailed metadata
   - `POST /api/upload` - Accept video uploads
   - `GET /api/backends` - List storage backends

2. **ABR Endpoint Stabilization** (High Priority)
   - Finish `EncodingManager` class
   - Implement background encoding worker
   - Test emergency JIT encoding
   - Implement transcode persistence logic

3. **S3 Backend Support** (High Priority)
   - Abstract storage layer
   - S3 listing/browsing
   - S3 file fetching to cache
   - Configuration management

4. **Transcode Cache Management** (Medium Priority)
   - Automatic `.transcodes` directory creation
   - TTL-based cleanup (if in cache)
   - Persistence detection (don't clean user-managed files)
   - Storage location reporting in API

### Plone Work Required

1. **Content Type Creation** (High Priority)
   - Define `casterpak.video` Dexterity type
   - Schema with source_path, streaming_mode, cached metadata
   - Computed `hls_url` property

2. **Library Browser Widget** (High Priority)
   - Tree view of CasterPak library
   - Calls `GET /api/library` recursively
   - Shows transcode status, file sizes
   - Select video → populate source_path field

3. **Upload Handler** (Medium Priority)
   - File upload form
   - Calls `POST /api/upload`
   - Progress indicator
   - Error handling

4. **Video Player Integration** (Medium Priority)
   - Embed HLS player (Video.js, Plyr, or native)
   - Use `hls_url` property from content object
   - Display metadata (duration, resolution)

5. **Admin Dashboard** (Low Priority)
   - Show CasterPak connection status
   - Display storage configuration warnings
   - Cache statistics
   - Backend health checks

---



## Testing Strategy

### Manual Testing Workflow

1. **Single-bitrate streaming**:
   ```bash
   curl -i http://localhost:5000/i/test.mp4/index_0_av.m3u8
   # Should return m3u8 playlist
   
   # Open in VLC: Media → Open Network Stream
   # URL: http://localhost:5000/i/test.mp4/index_0_av.m3u8
   ```

2. **CSMIL multi-bitrate** (pre-encoded renditions):
   ```bash
   # Assuming you have: test_720p.mp4, test_480p.mp4, test_360p.mp4
   curl -i http://localhost:5000/i/test_,720p,480p,360p,.mp4.csmil/master.m3u8
   # Should return master playlist with 3 renditions
   ```

3. **ABR auto-encode** (WIP):
   ```bash
   curl -i http://localhost:5000/i/abr/test.mp4/master.m3u8
   # Should start encoding + return emergency stream
   # Second request should redirect to CSMIL
   ```

4. **Cache invalidation test**:
   ```bash
   sqlite3 /var/lib/casterpak/data/cacheDB.db \
     "UPDATE segmentfile SET timestamp = 0; UPDATE inputfile SET timestamp = 0;"
   # Wait for cleanup job (runs every 300s by default)
   # Cache should be wiped
   ```

### Automated Tests

Location: `tests/containertests/run_tests.py`

Current status: Nearly working, needs container setup

---

## Security Considerations

### Path Sanitization

All user-supplied paths must be sanitized:

```python
# From csmil.py
filenameRE = re.compile(r'[^.a-zA-Z\d\_-]')
dirnameRE = re.compile(r'[^.a-zA-Z\d\_/-]')

# Always sanitize before filesystem access
filename = filenameRE.sub('', user_input)
```

### File Access Controls

- Source library should be read-only to CasterPak
- Transcode cache needs write access
- Never allow directory traversal (`../../../etc/passwd`)
- Use Flask's `safe_join()` for path construction

### API Authentication (Future)

API endpoints should require authentication:
- API keys for programmatic access
- OAuth for Plone integration
- Rate limiting for upload endpoint

---

## Open Questions

### 1. S3 Integration Details
- **Browse**: Use boto3 to list bucket objects, build tree structure?
- **Caching**: Download entire video to local cache, or stream directly?
- **Credentials**: Environment vars, IAM roles, or config file?

### 2. Encoding Performance
- **Concurrency**: How many simultaneous encoding jobs?
- **Priority queue**: User-requested vs. background pre-encoding?
- **Resource limits**: CPU/memory caps for encoding workers?

### 3. Plone Deployment
- **Same server**: Deploy CasterPak alongside Plone?
- **Separate services**: CasterPak on dedicated streaming server?
- **Load balancing**: Multiple CasterPak instances behind proxy?

### 4. Metadata Synchronization
- **Cache invalidation**: How does Plone know when CasterPak metadata changes?
- **Polling**: Periodic refresh of video metadata?
- **Webhooks**: CasterPak notifies Plone of status changes?

---

## Next Steps

### Immediate Actions (CasterPak)
1. Define Flask routes for `/api/library`, `/api/video`, `/api/upload`
2. Create storage abstraction layer (prepare for S3)
3. Implement transcode directory detection logic
4. Build metadata extraction utilities (duration, resolution, codec)

### Immediate Actions (Plone)
1. Scaffold `casterpak.video` Dexterity content type
2. Create basic library browser widget (mock data first)
3. Design video player view template
4. Plan API client module for CasterPak communication

### Integration Milestones
- **M1**: Plone can browse CasterPak library via API
- **M2**: Plone can create video objects that play single-bitrate streams
- **M3**: ABR streaming works end-to-end
- **M4**: Upload workflow functional
- **M5**: S3 backend support complete

---

## Contact & Resources

- **Repository**: https://github.com/flipmcf/CasterPak
- **Developer**: Michael McFadden (flipmcf)
  - GitHub: @flipmcf
  - Email: Available via GitHub profile
- **Business**: OpenForge Solutions
  - Website: openforgesolutions.com


---

## Glossary

- **ABR**: Adaptive Bitrate (streaming at multiple quality levels)
- **CSMIL**: Client-Side Manifest Injection Language (Akamai's URL syntax for specifying renditions)
- **HLS**: HTTP Live Streaming (Apple's streaming protocol)
- **Rendition**: A version of a video encoded at a specific resolution/bitrate
- **Segment**: Short video chunk (.ts file) in HLS streaming
- **TTL**: Time To Live (cache expiration)
- **VoD**: Video on Demand
- **Master Manifest**: Top-level .m3u8 file listing available renditions
- **Media Playlist**: Rendition-specific .m3u8 file listing segments

---

_Last Updated: 2026-09-23_
_Context Version: 1.1_

Note: the line below (`docker start -ai ... claude-dev` / `claude --resume <uuid>`) described an
older, non-ephemeral container setup and no longer matches how this repo is actually run - see
"Container Workflow (claude-sandbox)" near the top of this file instead. Left here only so it isn't
silently erased; safe to delete.

docker start -ai <container_name_or_id>  claude-dev
Resume with
claude --resume ab9e82ac-9f41-4ee9-9415-83153bdf944a

