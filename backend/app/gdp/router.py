"""GDP 造数工厂 FastAPI 路由聚合层。

将所有 datagen 子模块的路由统一挂载在 ``/api/v1/data-factory`` 前缀下。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.gdp.datagen.baseconfig.api import router as baseconfig_router
from app.gdp.datagen.httpsource.api import router as httpsource_router
from app.gdp.datagen.scene.api import router as scene_router
from app.gdp.datagen.sqlsource.api import router as sqlsource_router
from app.gdp.datagen.task.api import router as task_router

router = APIRouter(prefix="/api/v1/data-factory", tags=["data-factory"])

router.include_router(baseconfig_router)
router.include_router(httpsource_router)
router.include_router(sqlsource_router)
router.include_router(scene_router)
router.include_router(task_router)
