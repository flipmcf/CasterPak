Caching Stream Packager
Casterpak

depends on https://www.bento4.com/

Sample file that's delivered to the client from a 3rd party:

    https://cdnapisec.kaltura.com/
    p/1251832/sp/125183200/playManifest/entryId/1_4s1rg2d4/
    flavorIds/1_pj9w1e1t,1_qrt09hao,1_gyghthqk,1_27nugw2i/
    format/applehttp/protocol/https/a.m3u8

https://cdnapisec.kaltura.com/p/1251832/sp/125183200/playManifest/entryId/1_lxeahg4p/flavorIds/1_8zeiqpyv,1_jrew8okq,1_o8uw7xfp/format/applehttp/protocol/https/a.m3u8?referrer=aHR0cHM6Ly93d3cucmZhLm9yZw==&playSessionId=96a6d5c9-0f53-8927-8fcb-76727dd64256&clientTag=html5:v2.92&uiConfId=33053471

Sample contents of that file
    #EXTM3U
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=622044,RESOLUTION=854x480
    https://onprem.rfa.org/i/20220404/1251/1_5q8yua9n_1_q2fzuix0_1.mp4/index_0_av.m3u8
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=741318,RESOLUTION=960x540
    https://this_application/i/20220404/1251/1_5q8yua9n_1_t2rfozqd_1.mp4/index_0_av.m3u8
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=1156684,RESOLUTION=1280x720
    https://this_application/i/20220404/1251/1_5q8yua9n_1_rumb24fg_1.mp4/index_0_av.m3u8

Each one of those url's above will be served by this application.

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

And each one of those .ts files will be available at this application.

Additionally, this package will setup jobs to remove .ts files after they go unaccessed for
A certain amount of time.

----
Future:
We will be able to monitor encoded renditions for access times and remove them also
We should trigger creation of renditions on demand