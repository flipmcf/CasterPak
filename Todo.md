# TODO: 

Z-Mixing automation - generate master manifests by folder contents.

transcoding.   Automatically seeing that no renditions are available and auto-transcoding on play.

setting up other input methods (s3, ftp, etc)

Asking a user to wait 2 minutes while a 1080p transcode starts is a "churn" event. The Solution: Segment-Level Lazy Loading Instead of transcoding the whole file, CasterPak should transcode only the first 10 seconds immediately.

    User hits Play.

    CasterPak fires an "Emergency Transcode" for the first segment (0−10s).

    The player starts within seconds.

    CasterPak then fires the "Background Transcode" to keep the buffer ahead of the playhead.


Once 'on the fly' transcoding is done, "Priority Queue" skeleton that could handle that "First 10 Seconds" emergency transcode while keeping the rest of the queue in check?

the 'single bitrate' route - is it really useful?   It only works if the file is already encoded in a way that bento4 likes.  I have examples of iPhone videos that don't work when dropped right into bento4.  We should inspect files to make sure that bento4 likes them first, and encode if it doesn't.


Risks:
CPU Spikes	Queue Management: Limit concurrent transcodes to N (where N=CPU Cores−1).

Storage Bloat	TTL Caching: Delete transcoded segments if they haven't been touched in 24 hours.

DDoS Attacks	Rate Limiting: Use Nginx to limit how many new transcode requests a single IP can trigger per minute.