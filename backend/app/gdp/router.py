"""GDP 造数模块路由聚合。"""

from __future__ import annotations

from fastapi import APIRouter

from app.gdp.datagen.config.base.api import router as base_router
from app.gdp.datagen.config.httpsource.api import router as httpsource_router
from app.gdp.datagen.config.sqlsource.api import router as sqlsource_router

router = APIRouter(prefix="/api/v1/datagen", tags=["datagen"])
router.include_router(base_router)
router.include_router(httpsource_router)
router.include_router(sqlsource_router)
