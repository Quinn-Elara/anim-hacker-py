"""Anim Hacker: edit Second Life .anim files. A Qt port of the original WinForms tool."""



def __getattr__(name):
    """__version__ follows the git commit the program was built from, like the footer of the main
    window (see buildinfo.py); it is worked out on first use, not at import."""
    if name == "__version__":
        from . import buildinfo
        return buildinfo.version()
    raise AttributeError("module %r has no attribute %r" % (__name__, name))
