"""The emit stage removes what the browser never needed.

Comments carry the reasoning this project documents everywhere; they must not
cost bytes on a firewall. Stripping runs at EMIT, after parse_sections() has
consumed the <!--@SLOT--> markers -- running it earlier destroys them.
"""

import unittest

import pytest

from panos_response_pages.emit import strip_output

pytestmark = pytest.mark.unit


class TestStripOutput(unittest.TestCase):
    def test_removes_css_and_html_comments(self):
        self.assertEqual(strip_output("a/* gone */b"), "ab")
        self.assertEqual(strip_output("a<!-- gone -->b"), "ab")

    def test_html_comment_removal_is_not_greedy(self):
        """A comment containing '--' must not swallow to the last '-->'."""
        self.assertEqual(strip_output("<!-- a -- b -->keep<!-- c -->"), "keep")

    def test_an_unbalanced_css_comment_inside_html_does_not_cascade(self):
        """If the CSS pass ran first it would consume through the '-->' and the
        HTML pass would then eat forward to the NEXT '-->', deleting live
        markup. HTML comments are removed first for exactly this reason."""
        self.assertEqual(strip_output("<!-- a /* b -->keep"), "keep")

    def test_removes_whole_line_js_comments_only(self):
        """A blanket //.* would cut http://www.w3.org out of a data: URI and
        silently break the logo."""
        self.assertEqual(strip_output("  // dropped\nkept"), "kept")
        self.assertIn("http://www.w3.org", strip_output('u="http://www.w3.org/2000/svg"'))

    def test_strips_leading_indent_and_blank_lines(self):
        self.assertEqual(strip_output("    a\n\n\n    b"), "a\nb")

    def test_leaves_declarations_alone(self):
        """Deliberately not a minifier: no selector rewriting, no whitespace
        collapsing inside declarations, no identifier mangling."""
        self.assertEqual(strip_output("a { color : red }"), "a { color : red }")
