"""Class-based views for FastAPI routers.

A maintained, FastAPI 0.137+ compatible drop-in replacement for
``fastapi_utils.cbv``. Only the plain ``@cbv(router)`` form is supported.
"""

from fastapi_cbv_router.cbv import CBV_CLASS_KEY, cbv

__all__ = ["CBV_CLASS_KEY", "cbv"]
