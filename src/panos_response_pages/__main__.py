"""`python -m panos_response_pages`.

Present so the package can be driven without relying on the console script
being on PATH -- which is exactly the situation tests run in.
"""

from panos_response_pages.cli import app

app()
