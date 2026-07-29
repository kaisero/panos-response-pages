"""GlobalProtect portal pages.

A separate family from the block pages. The two imports are not documents: the
login page is a body fragment PAN-OS concatenates onto its own prefix, and the
home page is a bare script embedded mid-<head>. Neither carries the block
pages' fact rows or actions, and neither is bounded by the same byte limit.
"""
