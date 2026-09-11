# Volumes:
what data you have, 
which disk each kind lives on, 
and how big each disk is relative to how fast that data grows.

## Source videos
config: videoParentPath. 

This is the customer's library. 
It grows as they add videos.
It's the one thing that's precious, and for the install model it's often the only thing you'd ever want to preserve or back up.  Durability matters here. 

## Cache
Rendition + segment cache,
   videoCachePath for BYOS setups
   Transcoding Cache for those who don't bring transcoded vids.
   segment cache. 
   
   This is generated, disposable data. It can always be rebuilt by re-encoding. It grows fast under traffic and gets evicted by your TTL/size limits. Durability does not matter, if you lost it, CasterPak regenerates it. 
   But it needs room to breathe, because your cache size limits are promises about disk you have to actually own.

   It also needs to survive container restarts.

## Application 
 OS + application + Docker images. 
 
 The root volume. This should be boring, stable, and never at risk of filling from user activity.




