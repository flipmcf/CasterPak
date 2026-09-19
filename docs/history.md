# How CasterPak Happened

Short version: a vendor pulled a product, I looked at what it had actually
been doing, and it turned out to be Bento4 and a URL.

## The Plone years

Radio Free Asia ran Plone.  We needed video.

We went with Kaltura.  I wrote the Plone-Kaltura plugin, and then wrote
kaltura2 when we moved to Python 3.

Kaltura had a NetStorage backend, and served `.csmil` endpoints using Akamai
MSOD - Media Services On Demand.  That is where the URL format in this
project comes from.  I didn't design it.  I inherited it.  The MSOD Stream
Packaging user guide is still sitting in this directory if you want to read
the original spec.

It worked.  For years, it worked.

## Then Akamai pulled the plug

Akamai end-of-lifed MSOD.

Kaltura's answer was that we should migrate all of our content onto their
storage platform, which was S3.

So I went and looked at what we would be paying for.  MSOD had been taking
pre-encoded renditions and packaging them into HLS on request.  That's
Bento4 and a URL.

The part nobody was talking about was caching.  Package on every request and
you burn CPU forever.  Package once and keep it forever and you've
reinvented static packaging, which is the thing we were trying to get away
from.  The whole problem lives in the middle - what you keep, how long you
keep it, and what you throw away.  That's the part worth writing.

So I wrote it.  Two weeks.  Nobody asked me to.

## "That's our answer"

Then John Pennovich, RFA's CTO, asked the question out loud.  What should we
do?  We need to deliver videos.

I said I have this thing I've been working on.  CasterPak.

John said "that's our answer."

CasterPak ran RFA's video content for three or four years.

## Then it stopped

RFA moved off Plone to ArcXP, which has its own video media center baked in.
CasterPak wasn't needed anymore.

It went silent.

Then RFA furloughed 90% of its workforce.

I picked CasterPak back up.  It's my unemployment story.

## Why the software looks like this

All of the above is load-bearing:

- **The URL format is Akamai's** because that is what our content already
  used.  Rewriting every URL in a CMS is not a migration anyone should be
  asked to perform.  See `why_csmil.md` for why the comma-separated URL beat
  an XML file on disk.
- **Caching is a first-class concern**, not an optimization bolted on later.
  It's the reason this exists at all.  It's in the name.
- **"No migration" is not marketing copy.**  It's the specific thing that
  was being asked of us, that I did not want to do.

It ran a newsroom's video for years.  It's been quiet for a while.  Now I'm
trying to put it in front of people who need it.
