## The SMIL Approach (The XML Headache)

Traditional SMIL (Synchronized Multimedia Integration Language) relies on a physical XML file sitting on the server. If we used SMIL, the workflow would look like this:

    The /abr background worker finishes generating test-video_360.mp4, 480.mp4, etc.

    The worker must then construct an XML document (test-video.smil) listing those files and write it to the disk.

    When a user requests the video, Flask reads the .smil file from the disk, parses the XML, and translates it into an HLS .m3u8 manifest.

The problem: You now have to manage, clean up, and parse XML files. If a rendition gets deleted, the .smil file becomes stale and breaks the stream.


## The .csmil Redirect Approach (The Stateless Win)

CSMIL (Comma Separated Media Integration Language) is essentially "Virtual SMIL". It takes the entire XML configuration and encodes it directly into the URL itself.

By redirecting to the .csmil endpoint, you get massive advantages:

    Zero Disk I/O: You never write a manifest configuration file to disk.

    Zero XML Parsing: You avoid importing XML libraries or writing parsers.

    100% Truthful State: Because the /abr route queries EncodingManager to physically check which .mp4 files exist right now before building the redirect string, the resulting manifest is mathematically guaranteed to be accurate. It can never go stale.

    Code Reuse: the csmil_parent_manifest route is already written, tested, and works perfectly.