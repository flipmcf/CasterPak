import os

from pathsafety import validate_filename

class CsmilDescriptor:
    """ constructs and deconstructs csmil strings"""
    def __init__(self, dirname: str, basename: str, ext: str, bitrates: list, append_csmil: bool = False):
        self.dirname = dirname
        self.basename = basename
        self.ext = ext
        self.append_csmil = append_csmil

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
        append_csmil = False
        # Strip '.csmil' if the route accidentally passed it in
        if csmil_str.endswith('.csmil'):
            csmil_str = csmil_str[:-6]
            append_csmil = True

        csmil_chunks = csmil_str.split('/')
        dirs = csmil_chunks[:-1]
        files = csmil_chunks[-1]
        file_chunks = files.split(',')

        dirs = [validate_filename(d) for d in dirs]
        basename = validate_filename(file_chunks[0])
        # An empty bitrate entry is the deliberate "unlabeled single
        # rendition" sentinel (see single_bitrate_manifest's
        # bitrates=['']), which round-trips through csmil_string as a
        # double comma ('basename,,ext') - preserve it as '', but there's
        # nothing to validate since it carries no attacker-controlled content.
        bitrates = [validate_filename(f) if f else f for f in file_chunks[1:-1]]
        ext = common_filename_suffix = validate_filename(file_chunks[-1])

        dirname = os.path.join(*dirs) if dirs else ''
        filenames = [basename+'_'+bitrate+common_filename_suffix for bitrate in bitrates]
        files = [os.path.join(dirname, filename) for filename in filenames]
        
        return cls(dirname, basename, ext, bitrates, append_csmil)   
        
    @property
    def csmil_string(self) -> str:
        """
        Builds the mathematically deterministic CSMIL string.
        e.g., 'test-video,360,480,720,.mp4'

        A flat (no-subdirectory) file has dirname == '' - the separating '/'
        must be omitted in that case, not just the dirname itself. A bare
        leading '/' left in front of basename (e.g. '/test-video,,.mp4')
        gets treated as an absolute path the next time something does
        os.path.join(some_real_dir, that_string) - os.path.join silently
        discards the real directory and resolves to filesystem root instead
        of raising, which is exactly what broke single_bitrate_manifest.
        """
        labels = ",".join(self.bitrates)
        csmil = ".csmil" if self.append_csmil else ""
        prefix = f"{self.dirname}/" if self.dirname else ""
        return f"{prefix}{self.basename},{labels},{self.ext}{csmil}"

    @property
    def rendition_filenames(self) -> list:
        """
        Generates the exact list of physical .mp4 files this CSMIL represents.
        This completely removes the file-guessing logic from routes.py!
        """
        return [
            f"{self.basename}_{b}{self.ext}" if b else f"{self.basename}{self.ext}"
            for b in self.bitrates
        ]