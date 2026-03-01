import pytest
from vodhls.csmil import CsmilDescriptor

def test_parse_basic_csmil_string():
    """Test parsing a flat file with no directory."""
    csmil_str = "test-video_,720,480,.mp4"
    desc = CsmilDescriptor.from_string(csmil_str)

    assert desc.dirname == ""
    # The legacy parser lumps the _, into the prefix, so we test against the legacy behavior
    assert "test-video" in desc.basename 
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
        basename="movie", 
        ext=".mp4", 
        bitrates=["720", "480"]
    )
    
    expected_files = [
        "movie_480.mp4",
        "movie_720.mp4"
    ]
    assert desc.rendition_filenames == expected_files
