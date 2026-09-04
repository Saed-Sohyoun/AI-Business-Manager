"""Controlled tool access for agents.

Agents request typed operations through :class:`ToolGateway`.
Unrestricted shell / arbitrary HTTP / SQL are not exposed.
"""

from app.tools.gateway import ToolGateway

__all__ = ["ToolGateway"]
