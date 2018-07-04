"""
Utility functions for reading and writing data files.

For simplicity, each file stores a single JSON object. Admittedly this isn't
great if the files get large, since we need to read the whole thing to get at
any part of it (or to modify any part of it). But in that case, you should
probably just create a bunch of smaller files anyway.

Each script is supposed to have its own subdirectory where it keeps data files.
Therefore, the read/write functions explicitly take in a parameter for the
subdirectory, so you can't accidentally write your files in the base data/
directory.
"""

import json
import os

DATAFILE_DIR="data"



###############################################################################
# Public API

def readFile(subdir, name, errorOnNonexistent=False, default=None):
    """
    Read the data structure stored in the specified file.

    If the file does not exist (or isn't readable)...
        If errorOnNonexistent then throw an error.
        Else return default.

    If the file exists but can't be parsed, throw an error. If you want to
    catch this case, see tryReadFile.
    """

    fname = _getFilename(subdir, name)
    # Note: this would probably look more natural as:
    #     if not os.path.exists(fname):
    #         # ... file does not exist ...
    #     else:
    #         try:
    #             with open(fname) as f:
    #                 # ... read file ...
    #         except:
    #             # ... assume file was malformed ...
    # but there's technically a race condition in the above: the file could be
    # removed after the os.path.exists() check and before the open(fname). This
    # isn't going to matter in practice, but on principle I've coded it in a
    # different way which I _think_ avoids that race condition.
    #
    # Technically fileExists is really more like "file is a regular file and we
    # have permission to read it", but the point is that if we can't read it
    # and errorOnNonexistent is False, then we want to return the default value
    # rather than error.
    fileExists = False
    try:
        with open(fname, "r") as f:
            fileExists = True
            return json.load(f)
    except:
        if not fileExists and not errorOnNonexistent:
            return default
        else:
            raise

def tryReadFile(*args, **kwargs):
    """
    Same as readFile, except that this function returns a pair:
        (success, value)
    Where readFile would succeed, success is True and value is the value
    readFile would return. Where readFile would fail, success is False.
    """

    try:
        value = readFile(*args, **kwargs)
        return (True, value)
    except:
        return (False, None)

def writeFile(subdir, name, value):
    """
    Write the specified value into the specified file. This overwrites the file
    if it already exists. Can fail if we are unable to encode value or if for
    some reason we don't have permission to write the file.
    """

    fname = _getFilename(subdir, name)
    with open(fname, "w") as f:
        json.dump(value, f, indent=4, separators=(",", ": "))

def tryWriteFile(*args, **kwargs):
    """
    Same as writeFile, except that this function returns True on success and
    Falase on failure, rather than throwing an error.
    """

    try:
        writeFile(*args, **kwargs)
        return True
    except:
        return False

def fileExists(subdir, name):
    fname = _getFilename(subdir, name)
    return os.path.exists(fname)



###############################################################################
# Internal helper

def _getFilename(subdir, name):
    return os.path.join(DATAFILE_DIR, subdir, name)

