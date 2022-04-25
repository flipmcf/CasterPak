CasterPak

The CAshing STrEam [R] PAcKager:


This software only provides HLS Stream packinging, but can easily be enhanced for additional stream packaging technologies.

The problem it solves is to balance your CPU and Storage costs for streaming Video-on-demand.

You don't want to store your HLS stream forever, neither do you want to create a stream package for every request.  
This software provides the utilities to configure how long to store files ready for streaming (streaming cache ttl).
and creates stream packages on-demand from your encoded renditions if the files don't exist (handle cache miss)

This software doesn't create master / parent m3u8 manifests of encoded renditions.  That's the job of your encoder.
However, your encoder should be able to provide a master manifest, and that manifest should provide URL's that this
sofware will reply to.

Let's say your encoder creates this file of video renditions and this is what you serve to your player:

    #EXTM3U
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=622044,RESOLUTION=854x480
    https://this_application/i/20220404/1251/1_5q8yua9n_1_q2fzuix0_1.mp4/index_0_av.m3u8
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=741318,RESOLUTION=960x540
    https://this_application/i/20220404/1251/1_5q8yua9n_1_t2rfozqd_1.mp4/index_0_av.m3u8
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=1156684,RESOLUTION=1280x720
    https://this_application/i/20220404/1251/1_5q8yua9n_1_rumb24fg_1.mp4/index_0_av.m3u8

Each one of those url's above will be served by this application.  We call them 'segment manifests'.
This application will serve segement manifests and the actual segment data.

If the m3u8 is available on-disk, it's served.  Otherwise, it's created and saved

it will provide an m3u8 'child' playlist of segments like so:

    #EXTM3U
    #EXT-X-TARGETDURATION:10
    #EXT-X-ALLOW-CACHE:YES
    #EXT-X-PLAYLIST-TYPE:VOD
    #EXT-X-VERSION:3
    #EXT-X-MEDIA-SEQUENCE:1
    #EXTINF:10.000,
    https://cloudstorage.rfa.org/i/20220324/1251/1_yd2ohzql_1_pnkbhq6w_1.mp4/segment1_0_av.ts
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

Install Dependencies:

 Bento4 https://www.bento4.com/

 Bento4 binary is required.  Specifically the `mp42hls` command.
 
 At this time it's recommended compile and use a special version of mp42hls: https://github.com/axiomatic-systems/Bento4/pull/696
 
 Follow these instrctions to clone the specific branch / Pull Request
   
    git clone git@github.com:axiomatic-systems/Bento4.git
    cd Bento4
    git fetch origin pull/696/head
    git checkout -b iss693 FETCH_HEAD
   
 Then complle:
   
    mkdir cmakebuild
    cd cmakebuild/
    cmake -DCMAKE_BUILD_TYPE=Release ..
    make
   
 And copy the binary mp42hls to your fainal binary install directory
 
    cp mp42hls /usr/bin/mp42hls  
    
    
Installation:

This is totally in development and doesn't have a python setup yet.  Please contribute.

1. download / clone this repo
2. install a python virtual environment for it:

   `python3 -m venv .`

3. install python dependencies

   `./bin/pip install flask tinydb`
4. configure this application
   
   `cp config_example.ini config.ini`

   `vi config.ini`
   
5. run the application

   `./bin/python -m flask run`
   

Testing

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
