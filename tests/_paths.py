"""Where the tests look for data and for build output.

One definition, imported by every test module. The data directory moved into
the package and the output directory moved out of `dist/`; without a shared
constant that was 31 edits scattered across seven files, and the next move
would be 31 more.
"""

import pathlib

from panos_response_pages import datadir

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The shipped data, not a user override -- tests assert on what this repository
# contains, so they must not follow ~/.panos_response_pages if a developer has one.
DATA = datadir.PACKAGED

OUT = ROOT / "out"
DEPLOY = OUT / "deploy"
PREVIEW = OUT / "preview"
