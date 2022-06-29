# CasterPak

## The CAshing STrEam [R] PAcKager:


This software provides HLS Stream packaging for Video-On-Demand (VOD) with a built in file cache.

The problem it solves is to balance your CPU and Storage costs for streaming Video-on-demand.
Creating an HLS (m3u8) stream from a video file (mp4, et. al.) is CPU cheap and fast compared to video encoding.

It's a very good fit for use cases where videos serve the 'popular' model of access.  Videos that are frequently
accessed remain cached at this server and videos that are not accessed are deleted from cache.

Also it's a great fit for those who own a large 'archive' video file on inexpensive, slow-access storage.  CasterPak can
retrieve source video files from network addressess, copy them locally, and then deliver.   The first video play 
may be slow, but subsequent access to the same video is then fast. 

You don't want to store your HLS stream forever, neither do you want to create a stream package for every request.  
This software provides the utilities to configure how long to store video files locally (video input cache ttl),
files ready for streaming (streaming cache ttl), and creates stream packages on-demand from your encoded renditions
if the files don't exist (handle cache miss).

This package is a good drop-in replacement for Akamai Media Services On Demand (MSOD) for video streaming.
It supports the '.csmil' endpoint that Akamai used to support to generate master manifests of renditions,
and creates media playlists and segments your renditions.

This package does not include encoding of video renditions.

The first endpoint is the master manifest.  it uses the same syntax as Akamai's Media Services On Demand 'csmil' url construction:

https://example.com/i/path/<common_filename_prefix>,<bitrate>,<bitrate>,<bitrate>,<bitrate>,<common_filename_suffix>.csmil/manifest.m3u8

For example, this request will create the following master manifest:

https://this_application/i/20220404/1251/1_5q8yua9n_1_,q2fzuix0,t2rfozqd,rumb24fg,_1.mp4.csmil/manifest.m3u8


    #EXTM3U
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=622044,RESOLUTION=854x480
    https://this_application/i/20220404/1251/1_5q8yua9n_1_q2fzuix0_1.mp4/index_0_av.m3u8
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=741318,RESOLUTION=960x540
    https://this_application/i/20220404/1251/1_5q8yua9n_1_t2rfozqd_1.mp4/index_0_av.m3u8
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=1156684,RESOLUTION=1280x720
    https://this_application/i/20220404/1251/1_5q8yua9n_1_rumb24fg_1.mp4/index_0_av.m3u8

Each one of those url's above will be served by this application.  We call them 'media manifests' or 'segment manifests'
This application will serve segment manifests and the actual segment data.

If the m3u8 is available on-disk, it's served.  Otherwise, it's created and saved

    #EXTM3U
    #EXT-X-TARGETDURATION:10
    #EXT-X-ALLOW-CACHE:YES
    #EXT-X-PLAYLIST-TYPE:VOD
    #EXT-X-VERSION:3
    #EXT-X-MEDIA-SEQUENCE:1
    #EXTINF:10.000,
    https://this_application/i/20220324/1251/1_yd2ohzql_1_pnkbhq6w_1.mp4/segment1_0_av.ts
    #EXTINF:10.000,
    https://this_application/i/20220324/1251/1_yd2ohzql_1_pnkbhq6w_1.mp4/segment2_0_av.ts
    #EXTINF:10.000,
    https://this_application/i/20220324/1251/1_yd2ohzql_1_pnkbhq6w_1.mp4/segment3_0_av.ts
    #EXTINF:10.000,
    ...
    #EXTINF:6.186,
    https://this_application/i/20220324/1251/1_yd2ohzql_1_jj0dd2ah_1.mp4/segment19_0_av.ts
    #EXT-X-ENDLIST

And each one of those .ts files will be available at this application's endpoint until they are removed by the cache cleanup.

Additionally, this package will setup jobs to remove .ts files after they go unaccessed for
A certain amount of time.

----

### Install Dependencies:

 Bento4 https://www.bento4.com/

 Bento4 binary install is required.  Specifically the `mp42hls` and `mp4info` commands and possibly more.
 
 At this time it's recommended compile and use a special version of mp42hls: https://github.com/axiomatic-systems/Bento4/pull/696

 # TODO: https://github.com/flipmcf/CasterPak/issues/8 
 
 Follow these instructions to clone the specific branch / Pull Request
   
    git clone git@github.com:axiomatic-systems/Bento4.git
    cd Bento4
    git fetch origin pull/696/head
    git checkout -b iss693 FETCH_HEAD
   
 Then compile:
   
    mkdir cmakebuild
    cd cmakebuild/
    cmake -DCMAKE_BUILD_TYPE=Release ..
    make
   
 Copy these binaries into the directory configured in 'binaryPath' in config.ini
    
    
### Installation

This is totally in development and doesn't have a python setup yet.  Please contribute.

1. download / clone this repo

2. install a python virtual environment for it:

   `python3 -m venv .`


3. install python dependencies

   `./bin/pip install flask tinydb`


4. configure this application
   
   `cp config_example.ini config.ini`

   `vi config.ini`
   

5. run the application (development and testing)

   `./bin/python -m flask run`


6. configure gunicorn

   `vi gunicorn.conf.py`


7. run the application (production)

   `./bin/python -m gunicorn `

   It's up to the user to setup a web proxy with nginx or any other webserver. See documentation here https://flask.palletsprojects.com/en/2.1.x/deploying/uwsgi/


8. setup a systemd service. see the example casterpak.service unit file and see systemd documentation.


In the future, a complete installation script may be provided that does all the above steps.


### Setting up the cache cleanup task

What caching server is complete without deleting old stuff?

look at 'crontab.tpl' - it's your basic crontab entry.  add it via 'crontab -e' as the user that will be running the flask application
it's configured to run cleanup every 5 minutes, but you can tune it as you wish.

create a file /var/log/casterpak.log and give the application user rights to write to it for logging.

To watch it in action, get a few terminal windows open.

1. you can watch the actual cache of segment files.  If you configured to write your segments to /tmp/segments, run this command:

     `watch tree -L /tmp/segments`

And leave it open - as requests happen, you'll see the files fill up.

2. you can watch the cache database - this tells what files were created when.

    `watch date +%s && cat cacheDB.json`

3. you can watch the log (turn on debug in config.ini for best results):

    `tail -f /var/log/casterpak.log`

and it's always nice to do some requests to fill up the cache.

    curl http://localhost:5000/i/video.mp4/index_0_av.m3u8


## System Setup

Included is a systemd unit config 'casterpak.service'.  No setup script is provided, so you must edit and install this yourself

Open it, edit it to best suit your paths where you installed casterpak and your wsgi server.

then `sudo ln -s /path/to/casterpak.service /etc/systemd/service/casterpak.service`

then `sudo systemctl start casterpak.service`


## Testing

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

----
versions (should update these)
- click==8.1.2
- Flask==2.1.1
- importlib-metadata==4.11.3
- itsdangerous==2.1.2
- Jinja2==3.1.1
- MarkupSafe==2.1.1
- tinydb==4.7.0
- Werkzeug==2.1.1
- zipp==3.8.0


## Debugging

Note that these are techniques to begin learning from.  Use these hints to develop your own strategies on how to debug the app.

diagnosis of the flask application itself is easy enough.  configure to listen on localhost and use `./bin/python -m flask run` to run the app.

gunicorn and thread issues are a bit harder.  Included is a sample gunicorn config `gunicorn-debug.conf.py` that launches the flask application in a single thread you can debug.
`sudo ./venv/bin/python3 -m gunicorn --config gunicorn-debug.conf.py`

Please configure the debug configuration to your needs.



