#This is documentation for humans who do testing.

## First Test - single bitrate 
Single-bitrate baseline — `master.m3u8` on one file, confirm playback.

configure an input file that is an mp4. call it 'test_video.mp4'
place it in your home directory /home/user/Videos/test_video.mp4

Install casterpak and edit config.ini
  -configure [input][input_type] = filesystem
  -configure [filesystem][videoParentPath] = /home/user/Videos

run casterpak.
  ./run

use curl to make sure the stream plays by hitting the 'single bitrate manifest'
  curl http://127.0.0.1:5000/i/test_video.mp4/master.m3u8
  read the response, follow the index url with curl
  read the response, follow a segment or two and make sure they are 200.

Hit that same URL in VLC media player and confirm it plays.

## Second, TEST CSMIL
Now we must encode a few renditions - see 'manual_encode_cmd' document and get ffmpeg installed.
  (lock down that command here)
  validate that renditions appeared
  (compose the csmil url for testing)
  
