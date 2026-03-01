import os
import re

# valid characters in a filename
filenameRE = re.compile(r'[^.a-zA-Z\d_-]')
# valid characters in a directory path:
dirnameRE = re.compile(r'[^.a-zA-Z\d_/-]')

class CsmilDescriptor:
    """ constructs and deconstructs csmil strings"""
    def __init__(self, dirname: str, basename: str, ext: str, bitrates: list):
        self.dirname = dirname
        self.basename = basename
        self.ext = ext

        # The magic rule: bitrates are ALWAYS sorted immediately upon creation
        # This guarantees mathematical determinism everywhere in the app.
        self.bitrates = sorted([str(b) for b in bitrates])

    ## TODO fix type hint to "-> Self" for python 3.11+
    @classmethod
    def from_string(cls, csmil_str: str) -> 'CsmilDescriptor':
        """
        Parses a raw string like '/foodir/bardir/test-video_,720,480,360,.mp4'
        and returns a fully populated, sorted CsmilDescriptor object.
        """
        # Strip '.csmil' if the route accidentally passed it in
        if csmil_str.endswith('.csmil'):
            csmil_str = csmil_str[:-6]

        csmil_chunks = csmil_str.split('/')
        dirs = csmil_chunks[:-1]
        files = csmil_chunks[-1]
        file_chunks = files.split(',')

        dirs = [filenameRE.sub('', d) for d in dirs]
        basename = filenameRE.sub('', file_chunks[0])
        bitrates = [filenameRE.sub('', f) for f in file_chunks[1:-1]]
        ext = common_filename_suffix = filenameRE.sub('', file_chunks[-1])

        dirname = os.path.join(*dirs) if dirs else ''
        filenames = [basename+'_'+bitrate+common_filename_suffix for bitrate in bitrates]
        files = [os.path.join(dirname, filename) for filename in filenames]
        
        return cls(dirname, basename, ext, bitrates)   
        
    @property
    def csmil_string(self) -> str:
        """
        Builds the mathematically deterministic CSMIL string.
        e.g., 'test-video_,360,480,720,.mp4'
        """
        labels = ",".join(self.bitrates)
        return f"{self.basename}_,{labels},{self.ext}"

    @property
    def rendition_filenames(self) -> list:
        """
        Generates the exact list of physical .mp4 files this CSMIL represents.
        This completely removes the file-guessing logic from routes.py!
        """
        return [f"{self.basename}_{b}{self.ext}" for b in self.bitrates]