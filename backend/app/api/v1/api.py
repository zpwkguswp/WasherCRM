from fastapi import APIRouter
from app.api.v1.endpoints import branches, restaurants, requests, payments, notifications, audit

api_router = APIRouter()
api_router.include_router(branches.router, prefix="/branches", tags=["Branches"])
api_router.include_router(restaurants.router, prefix="/restaurants", tags=["Restaurants"])
api_router.include_router(requests.router, prefix="/requests", tags=["Service Requests"])
api_router.include_router(payments.router, prefix="/payments", tags=["Payments"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(audit.router, prefix="/audit-logs", tags=["Audit Logs"])
