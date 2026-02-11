# CasterPak

## The CAching STrEam [R] PAcKager:

This software provides HLS Stream packaging for Video-On-Demand (VOD) with a built in file cache.

The problem it solves is to balance your CPU and Storage costs for streaming Video-on-demand.
Creating an HLS (m3u8) stream from a video file (mp4, et. al.) is CPU cheap and fast compared to video encoding.

It's a very good fit for use cases where videos serve the 'popular' model of access.  Videos that are frequently
accessed remain cached at this server and videos that are not accessed are deleted from cache.

Also it's a great fit for those who own a large 'archive' video file on inexpensive, slow-access storage like AWS S3 Glacier or Microsoft Azure Archive.  
CasterPak can retrieve source video files from network addressess, copy them locally, and then deliver.   The first video play may be slow, but subsequent access to the same video is then fast. 

You don't want to store your HLS stream forever, neither do you want to re-create a stream package for every request.  
This software provides the utilities to configure how long to store origional video files locally (video input cache ttl), files ready for streaming (streaming cache ttl), and creates stream packages on-demand from your encoded renditions
if the files don't exist (handle cache miss).

This package is a good drop-in replacement for Akamai Media Services On Demand (MSOD) for video streaming.
It supports the '.csmil' endpoint that Akamai used to support to generate master manifests of renditions,
and creates media playlists and segments your renditions.

This package does not include encoding of video renditions.

The first endpoint is the master manifest.  it uses the same syntax as Akamai's Media Services On Demand 'csmil' url construction:

http://example.com/i/path/<common_filename_prefix>,< bitrate >,< bitrate >,< bitrate >,< bitrate >,<common_filename_suffix>.csmil/master.m3u8

For example, if you have a master video 'my_video.mp4' and after video encoding you create a 'my_video_highdef.mp4', 'my_video_medium.mp4', and 'my_video_low.mp4', this URL request will create the following master manifest:

http://this_application/i/my_video_,highdef,medium,low,.mp4.csmil/master.m3u8


    #EXTM3U
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=622044,RESOLUTION=854x480
    http://this_application/i/my_video_low.mp4/index_0_av.m3u8
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=741318,RESOLUTION=960x540
    http://this_application/i/my_video_medium.mp4/index_0_av.m3u8
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=1156684,RESOLUTION=1280x720
    http://this_application/i/my_video_highdef.mp4/index_0_av.m3u8

Each one of those url's above will also be served by this application.  We call them 'media manifests' or 'segment manifests' This application will serve segment manifests and the actual segment data.

If the m3u8 manifest is available on-disk, it's served.  Otherwise, it's created and saved

For example, http://this_application/i/my_video_highdef.mp4/index_0_av.m3u8 will reply with

    #EXTM3U
    #EXT-X-TARGETDURATION:10
    #EXT-X-ALLOW-CACHE:YES
    #EXT-X-PLAYLIST-TYPE:VOD
    #EXT-X-VERSION:3
    #EXT-X-MEDIA-SEQUENCE:1
    #EXTINF:10.000,
    http://this_application/i/my_video_highdef.mp4/segment1_0_av.ts
    #EXTINF:10.000,
    http://this_application/i/my_video_highdef.mp4/segment2_0_av.ts
    #EXTINF:10.000,
    http://this_application/i/my_video_highdef.mp4/segment3_0_av.ts
    #EXTINF:10.000,
    ...
    #EXTINF:6.186,
    http://this_application/i/my_video_highdef.mp4/segment19_0_av.ts
    #EXT-X-ENDLIST

And each one of those .ts files will be available at this application's endpoint until they are removed by the cache cleanup.

Additionally, this package will setup jobs to remove .ts files after they go unaccessed for
A certain amount of time.


### CACHING RECIPIES & Tuning

The easiest is no cache.  Start here.   Install this (or run the container) on the same system that has your video files.
(if you're already using a network mount for your video files, you're ahead of the game... but stay with me...)

configure "cache_input = False" in config.ini.

And start streaming.

Next is to turn cache_input on and configure a local spot for your video files - so they are only read over the network once.  This is your 'input cache'.  Currently, casterpak will copy your big video files into the container, but I'm considering other options the 'input cache' configuration.

In the future, we will support directly configuring FTP, SCP, and others so network mounts are not necessary inside containers. (see config.ini), but for now, you must mount the filesystem and map it to the container.

----

# Simple Docker install:

after cloning this repository:

run './setup.py' for required configuration.

`docker-compose up -d --build`

Stop the server with:

`docker-compose down`

And get a clean build with:
`docker-compose down --rmi all --volumes --remove-orphans`

Things should work right out of the box.

open VNC or a browser capable of native HLS streaming, and hit the url where your video is:

http://localhost/i/VIDEOFILENAME.mp4/master.m3u8



### 3. Check the logs

`docker logs -f casterpak_server`

There is also a 'watcher' script './watch_casterpak.sh' you may run at your own risk.  It will open up a bunch of terminal windows to watch the logs, the cache filesystem, the database, and a cli into the container for your own debugging.


# Development Installs 

For dev installs, it's best to get things working without a container, then do a 'docker-compose' to make sure containers still build.

as a developer, you are responsible for running the flask app 'casterpak' and the cache cleanup process separately helps debug stuff.

### configuration
for development, the 'config.ini' is your best place, but for production, use env vars.
All of the options in config.ini will be overridden by environment variables for containerized builds, which is the production path.


### Install System Dependencies:


#### Bento4 https://www.bento4.com/

Bento4 binary install is required.  Specifically the `mp42hls` and `mp4info` commands and possibly more.
best to look at 'docker-compose' and manually follow the instructions there.

#### Sqllite3
   kind of standard quick-and-dirty low fingerprint SQL server to maintain cache state. Go google it or just use 'apt' or 'yum' to install it.  

`apt-get update && apt-get install -y sqlite3`

    
### Installation of casterpak

Once your dependencies are met...

1.  install a python virtual environment for it:

   `python3 -m venv .`

3. install python dependencies

   `./bin/pip install -r requirements.txt`

4. configure this application
   
   `cp config_example.ini config.ini`

   `vi config.ini`

This config file is ONLY for development.  It will not be copied into the container 
when building a container, config_example.ini contains defaults, and .env contains user overrides.

You must configure:
  a servername (localhost:5000 by default)
  videoParentPath for where to find your full-lenght videos (/mnt/data/videos default)
  path to the bento4 binaries
  and if you're reading this, you probably want Debug = True
   

5. run the flask application (development and testing only)
   ```
   export CASTERPAK_FILESYSTEM_VIDEOPARENTPATH=/path/to/videos
   ./bin/python -m flask run
   ```

Now, you can test flask is working by hitting port 5000
Depending on how you configured your  'videoParentPath' - construct your url.

By default, it will look in /mnt/data:
videoParentPath = /mnt/data

and a file /mnt/data/test.mp4 will have the url:

http://localhost:5000/i/test.mp4/index.m3u8

A browser may only download the .m3u8 file, but using VLC or any media player will show the video.
Congrats!  you're now developing.

### Scaling with gunicorn 

What this is doing is taking that single flask thread and creating workers so we can serve multiple requests.

6. configure gunicorn

   `vi gunicorn.conf.py`


7. run the application (production)

   `./bin/gunicorn`

It's up to the user to setup a web proxy with nginx or any other webserver. 
See documentation here https://flask.palletsprojects.com/en/2.1.x/deploying/uwsgi/




## Virtualized System Setup (not docker)

Included is a systemd unit config 'casterpak.service'.  No setup script is provided, so you must edit and install this yourself

Open it, edit it to best suit your paths where you installed casterpak and your wsgi server.

then `sudo ln -s /path/to/casterpak.service /etc/systemd/service/casterpak.service`

then `sudo systemctl start casterpak.service`

### Setting up the cache cleanup task

Currently, casterpak will cleanup imported video files from remote sources and generated segment files and media playlists.
By design (currently) casterpak will not cleanup master playlists because they are very small to store.  This might change in the future.
Deleting master playlists is not a problem, as casterpak will re-create them if necessary.

What caching server is complete without deleting old stuff?

For Virtualized or bare-metal setups, look at 'crontab.tpl' - it's your basic crontab entry.  add it via 'crontab -e' as the user that will be running the flask application
it's configured to run cleanup every 5 minutes, but you can tune it as you wish.

create a file /var/log/casterpak.cache.log and give the application user rights to write to it for logging.


## Testing

Hopefully, a lot of this will be automated soon, but here is the basic testing path.
Before a commit to main:

1. execute `run.sh` at the root of the repository with your testing setup.  
    Make sure videos are served (use VLC "media->open network stream" and hit a master.m3u8 url)

2. execute `docker-compose build --no-cache` to make sure the containers build.
3. execute `docker-compose up -d` to run the server

- make sure videos are served.


note that there is a hard coded root path for url's called "i" so all testing must be to http://127.0.0.1/i/path/to/the/files
This 'feature' may go away in the future.

Place an mp4 file directly under "videoParentPath" or in any subdirectory below "videoParentPath"
  example videoParentPath: /mnt/media/files/
  example mp4 file: /mnt/media/files/videos/video.mp4

Request the CasterPak "childManifestFilename" endpoint:
  curl http://127.0.0.1/i/videos/video.mp4/index_0_av.m3u8

you should get a result that looks like an m3u8 manifest
you should see a new directory and files created in  'segmentParentPath'

you can also point VLC or any other video player that can open a network path to http://127.0.0.1/i/videos/video.mp4/index_0_av.m3u8 and make sure the video plays.

### Testing Cache Cleanup.

the entire cache can be invalidated with a single SQL query:
 `sqlite3 /app/cacheDB.db "UPDATE segmentfile SET timestamp = 0; UPDATE inputfile SET timestamp = 0;"`

setting everything to a timestamp of last access, Jan 1, 1970.   Cleanup should wake up every 300 seconds by default, and wipe the cache.



## Debugging

turn debug logs on in config.ini
```
[application]
debug = True
```

Note that these are techniques to begin learning from.  Use these hints to develop your own strategies on how to debug the app.

diagnosis of the flask application itself is easy enough.  configure to listen on localhost and run the app: 

`./bin/python -m flask run` 

then, use curl to create some requests.

Assuming your video path is configured to point to a directory that directly contains video files:

1. `curl -i http://localhost:5000/i/video.mp4`

You should see a debug log "DEBUG in casterpak: caught 404 for test.mp4"   
  - direct access to mp4 files without streaming is handled, but not supported

2 `http://localhost:5000/i/video.mp4/master.m3u8`
  
  The simplest of calls.
  This does some work, calling that one file and creating a single-bitrate stream.
  the log should show: 
  INFO in _internal: 127.0.0.1 - - [03/Feb/2026 13:33:23] "GET /i/JonBike.MP4/master.m3u8 HTTP/1.1" 200 -

Taking that same url and opening it up in VLC as a "Network Stream" should now play that file as an HLS stream.


gunicorn and thread issues are a bit harder.  Included is a sample gunicorn config `gunicorn-debug.conf.py` that launches the flask application in a single thread you can debug.

`sudo ./venv/bin/python3 -m gunicorn -b :5000 --config gunicorn-debug.conf.py`

Please configure the debug configuration to your needs.

### Cache debugging
This is best to do with a container.

Run casterpak container:


`docker exec -it casterpak_server /bin/bash`

you can watch the actual cache of segment files.  If you configured to write your segments to /tmp/segments, run this command:

     `watch tree -L 2 /tmp/segments`

And leave it open - as requests happen, you'll see the files fill up.

2. you can watch the cache database - this tells what files were created when.

    `watch date +%s && cat cacheDB.json`

3. you can watch the log (turn on debug in config.ini for best results):

    `tail -f /var/log/casterpak.log`

and it's always nice to do some requests to fill up the cache.

    curl http://localhost:5000/i/video.mp4/index_0_av.m3u8



