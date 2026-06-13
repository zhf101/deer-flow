"""GDP 造数模块路由聚合。"""

from __future__ import annotations

from fastapi import APIRouter

from app.gdp.agent_runtime.api import router as agent_runtime_router
from app.gdp.datagen.agent_catalog.api import router as agent_catalog_router
from app.gdp.datagen.agent_memory.api import router as agent_memory_router
from app.gdp.datagen.config.base.api import router as base_router
from app.gdp.datagen.config.httpsource.api import router as httpsource_router
from app.gdp.datagen.config.scene.api import router as scene_router
from app.gdp.datagen.config.sqlsource.api import router as sqlsource_router
from app.gdp.datagen.config.task.api import router as task_router
from app.gdp.datagen.config.task.subtask_api import router as task_subtask_router

router = APIRouter(prefix="/api/v1/datagen", tags=["datagen"])
router.include_router(base_router)
router.include_router(httpsource_router)
router.include_router(sqlsource_router)
router.include_router(scene_router)
router.include_router(task_router)
router.include_router(task_subtask_router)
router.include_router(agent_catalog_router)
router.include_router(agent_memory_router)
router.include_router(agent_runtime_router)
