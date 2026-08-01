"""Filesystem-installed Hermes plugin entrypoint."""

# Hermes loads directory plugins under its private ``hermes_plugins`` namespace
# without adding the plugin directory itself to ``sys.path``.  Keep this import
# package-relative so both filesystem installs and packaged copies load under
# that namespace.
from .dataclaw_hermes_bridge import register

__all__ = ["register"]
