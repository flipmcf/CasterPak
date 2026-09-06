from jit.jit_manager import JitManager


def jit_manager_factory(dir_name, input_filepath, output_dir, manifest_path) -> JitManager:
    """
    Factory that returns a JitManager for the given source file / output paths.

    Only one manager type exists today (filesystem-backed JIT encoding), but this
    stays a factory - rather than callers constructing JitManager directly - so
    future JIT strategies (e.g. a remote/S3-backed variant) have somewhere to plug
    in without changing every call site.
    """
    return JitManager(
        dir_name=dir_name,
        input_filepath=input_filepath,
        output_dir=output_dir,
        manifest_path=manifest_path,
    )
