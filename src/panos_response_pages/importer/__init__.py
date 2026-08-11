"""Sending built pages to a management plane.

One backend today (`scm`), with `panos` and `panorama` to follow. The split is
core-versus-backend rather than a module per protocol: the catalogue, the source
loader and the report are the same work regardless of what is being talked to,
and only the Target knows about hosts, scopes and auth.
"""

from __future__ import annotations

from panos_response_pages.importer.catalogue import CATALOGUE, PORTAL, RESPONSE, PageSpec

__all__ = ["CATALOGUE", "PORTAL", "RESPONSE", "PageSpec"]
