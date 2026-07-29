"""Emit-time size reduction.

Comments were a third of some sources. Rather than write terse, unmaintainable
templates, sources keep their reasoning and this removes it on the way out.

Deliberately NOT a minifier: comments and leading indentation only. No selector
rewriting, no whitespace collapsing inside declarations, no identifier
mangling. Each of those risks changing behaviour on a page whose failure mode
is silent, to save bytes we do not need.

Must run AFTER parse_sections(): the <!--@SLOT--> markers are HTML comments and
this would delete them.
"""

from __future__ import annotations

import re

# HTML first: an unbalanced '/*' inside an HTML comment would otherwise let the
# CSS pass consume through the '-->', after which this pass eats forward to the
# next '-->' in the file and deletes live markup.
#
# Non-greedy, so a comment containing '--' does not swallow to the last '-->'.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def strip_output(text: str) -> str:
    """Remove comments and leading indentation. Nothing else."""
    text = _HTML_COMMENT.sub("", text)
    text = _CSS_COMMENT.sub("", text)
    # Only lines that are nothing but a // comment. A blanket `//.*$` would cut
    # `http://www.w3.org/2000/svg` out of a logo data URI and break it silently.
    lines = [ln for ln in text.split("\n") if not ln.lstrip().startswith("//")]
    return "\n".join(ln.lstrip() for ln in lines if ln.strip())
