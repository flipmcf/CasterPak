#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import pytest
from vodhls.csmil import CsmilDescriptor

def test_parse_basic_csmil_string():
    """Test parsing a flat file with no directory."""
    csmil_str = "test-video_,720,480,.mp4"
    desc = CsmilDescriptor.from_string(csmil_str)

    assert desc.dirname == ""
    assert desc.basename == "test-video_"
    assert desc.ext == ".mp4"
    assert desc.bitrates == ["480", "720"]  # Sorted automatically

def test_parse_deep_path():
    """Test parsing deep paths, stripping .csmil"""
    csmil_str = "foodir/bardir/movie,1080,720,.mp4.csmil"
    desc = CsmilDescriptor.from_string(csmil_str)

    assert desc.dirname == "foodir/bardir" # The @ was stripped
    assert desc.ext == ".mp4"
    assert desc.basename == "movie"
    assert desc.bitrates == ["1080", "720"]

def test_rendition_filenames_generation():
    """Test that it generates the exact list of physical files."""
    desc = CsmilDescriptor(
        dirname="cache",
        basename="movie_",
        ext=".mp4",
        bitrates=["720", "480"]
    )

    expected_files = [
        "movie_480.mp4",
        "movie_720.mp4"
    ]
    assert desc.rendition_filenames == expected_files

def test_rendition_filenames_single_unlabeled_bitrate():
    """A CsmilDescriptor with one unlabeled ('') bitrate represents a plain,
    single-bitrate stream -- it must resolve to the bare source filename,
    with no '_<bitrate>' suffix inserted."""
    desc = CsmilDescriptor(
        dirname="",
        basename="movie",
        ext=".mp4",
        bitrates=['']
    )

    assert desc.rendition_filenames == ["movie.mp4"]

def test_create_csmil_string():
    """Test that after building a CsmilDescriptor, we can re-create the string"""
    desc = CsmilDescriptor(
        dirname="cache",
        basename="movie",
        ext=".mp4",
        bitrates=["720p", "480p"]
    )

    assert desc.csmil_string == "cache/movie,480p,720p,.mp4"

def test_csmil_round_trip():
    """
    a csmil string as input should match it's output - 
    ASSUMING THE BITRATES ARE IN ORDER
    """
      
    input = "foodirxrar/badfardir/mofdafdasdddcvie,1080,200,720,.mp4.csmil"

    desc = CsmilDescriptor.from_string(input)

    output = desc.csmil_string
    assert output == input

# --- "Bring your own transcodes" ------------------------------------------
# Renditions that were NOT produced by /abr/ can use any naming scheme. The
# CSMIL grammar is plain concatenation - prefix + label + suffix - so whatever
# separator the files use has to come from the URL itself, never from the
# parser.

BYO_CASES = [
    pytest.param(
        "bbb_,360p,480p,720p,.avi",
        ["bbb_360p.avi", "bbb_480p.avi", "bbb_720p.avi"],
        id="underscore-in-prefix",
    ),
    pytest.param(
        "bbb-,360p,480p,720p,.avi",
        ["bbb-360p.avi", "bbb-480p.avi", "bbb-720p.avi"],
        id="dash-in-prefix",
    ),
    pytest.param(
        "bbb.,360p,480p,720p,.avi",
        ["bbb.360p.avi", "bbb.480p.avi", "bbb.720p.avi"],
        id="dot-in-prefix",
    ),
    pytest.param(
        "bbb,360p,480p,720p,.avi",
        ["bbb360p.avi", "bbb480p.avi", "bbb720p.avi"],
        id="no-separator-at-all",
    ),
    pytest.param(
        "example2a_,300000,500000,800000,_event1.mp4",
        ["example2a_300000_event1.mp4",
         "example2a_500000_event1.mp4",
         "example2a_800000_event1.mp4"],
        id="akamai-doc-example-suffix-carries-content",
    ),
]


@pytest.mark.parametrize("csmil_str, expected", BYO_CASES)
def test_byo_rendition_filenames_are_pure_concatenation(csmil_str, expected):
    """The parser must never add a delimiter between prefix, label and suffix."""
    desc = CsmilDescriptor.from_string(csmil_str)

    assert desc.rendition_filenames == expected


@pytest.mark.parametrize("csmil_str, expected", BYO_CASES)
def test_byo_from_string_does_not_mutate_prefix(csmil_str, expected):
    """Everything before the first comma is the prefix, verbatim - trailing
    separator characters included."""
    desc = CsmilDescriptor.from_string(csmil_str)

    assert desc.basename == csmil_str.split(",")[0]


def test_byo_transcodes_directory_layout():
    """The layout from the bring-your-own use case:

        bbb.avi.transcodes/
            bbb_360p.avi  bbb_480p.avi  bbb_720p.avi
    """
    desc = CsmilDescriptor.from_string(
        "bbb.avi.transcodes/bbb_,360p,480p,720p,.avi.csmil"
    )

    assert desc.dirname == "bbb.avi.transcodes"
    assert desc.rendition_filenames == [
        "bbb_360p.avi", "bbb_480p.avi", "bbb_720p.avi"
    ]


def test_byo_url_round_trips_unchanged():
    """Parsing then rebuilding must hand back the exact URL segment, with the
    prefix's trailing '_' intact."""
    url = "bbb.avi.transcodes/bbb_,360p,480p,720p,.avi.csmil"

    assert CsmilDescriptor.from_string(url).csmil_string == url
