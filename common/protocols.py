"""
Compatibility module for the protocol constants.

The application uses common.protocol as its canonical module; this alias keeps
the filename common/protocols.py usable for integrations that use that name.
"""

from common.protocol import *  # noqa: F401,F403
