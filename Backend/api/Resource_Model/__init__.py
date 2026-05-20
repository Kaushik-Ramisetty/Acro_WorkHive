"""Resource-management module.

Exposes three routers:
  - bench_router  : admin endpoints under /admin/* for bench page
  - admin_router  : admin endpoints under /admin/* for projects + assign flows
  - manager_router: manager endpoints under /manager/* for team view + actions
"""
from api.Resource_Model.bench import router as bench_router
from api.Resource_Model.router import admin_router, manager_router

__all__ = ["bench_router", "admin_router", "manager_router"]
