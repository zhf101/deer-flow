"""ORM model registration entry point.

Importing this module ensures all ORM models are registered with
``Base.metadata`` so Alembic autogenerate detects every table.

The actual ORM classes have moved to entity-specific subpackages:
- ``deerflow.persistence.thread_meta``
- ``deerflow.persistence.run``
- ``deerflow.persistence.feedback``
- ``deerflow.persistence.user``

``RunEventRow`` remains in ``deerflow.persistence.models.run_event`` because
its storage implementation lives in ``deerflow.runtime.events.store.db`` and
there is no matching entity directory.
"""

from deerflow.persistence.feedback.model import FeedbackRow
from deerflow.persistence.models.run_event import RunEventRow
from deerflow.persistence.run.model import RunRow
from deerflow.persistence.thread_meta.model import ThreadMetaRow
from deerflow.persistence.user.model import UserRow

try:
    from app.gdp.datagen.config.base.repository import (
        DataFactoryConfigAuditRow,
        DataFactoryDatasourceRow,
        DataFactoryEnvironmentRow,
        DataFactoryIdentifierReferenceRow,
        DataFactoryServiceEndpointRow,
        DataFactorySystemRow,
    )
    from app.gdp.datagen.config.httpsource.repository import DataFactoryHttpSourceRow
    from app.gdp.datagen.config.scene.repository import (
        DataFactorySceneRow,
        DataFactorySceneStepHttpConfigRow,
        DataFactorySceneStepRow,
        DataFactorySceneStepSqlConfigRow,
        DataFactorySceneVersionRow,
    )
    from app.gdp.datagen.config.sqlsource.repository import DataFactorySqlSourceRow

    DataFactorySqlTemplateRow = None
    DataFactoryTaskRow = None
    DataFactoryTaskVersionRow = None
except ImportError:
    DataFactoryConfigAuditRow = None
    DataFactoryDatasourceRow = None
    DataFactoryEnvironmentRow = None
    DataFactoryHttpSourceRow = None
    DataFactoryIdentifierReferenceRow = None
    DataFactorySceneRow = None
    DataFactorySceneStepHttpConfigRow = None
    DataFactorySceneStepRow = None
    DataFactorySceneStepSqlConfigRow = None
    DataFactorySceneVersionRow = None
    DataFactoryServiceEndpointRow = None
    DataFactorySqlSourceRow = None
    DataFactorySqlTemplateRow = None
    DataFactorySystemRow = None
    DataFactoryTaskRow = None
    DataFactoryTaskVersionRow = None
else:
    try:
        from app.gdp.persistence.model import (
            DataFactorySceneRow as _DataFactorySceneRow,
            DataFactorySceneVersionRow as _DataFactorySceneVersionRow,
            DataFactorySqlTemplateRow as _DataFactorySqlTemplateRow,
            DataFactoryTaskRow as _DataFactoryTaskRow,
            DataFactoryTaskVersionRow as _DataFactoryTaskVersionRow,
        )
    except ImportError:
        pass
    else:
        DataFactorySceneRow = _DataFactorySceneRow
        DataFactorySceneVersionRow = _DataFactorySceneVersionRow
        DataFactorySqlTemplateRow = _DataFactorySqlTemplateRow
        DataFactoryTaskRow = _DataFactoryTaskRow
        DataFactoryTaskVersionRow = _DataFactoryTaskVersionRow

__all__ = [
    "FeedbackRow",
    "RunEventRow",
    "RunRow",
    "ThreadMetaRow",
    "UserRow",
    "DataFactoryConfigAuditRow",
    "DataFactoryDatasourceRow",
    "DataFactoryEnvironmentRow",
    "DataFactoryHttpSourceRow",
    "DataFactoryIdentifierReferenceRow",
    "DataFactorySceneRow",
    "DataFactorySceneStepHttpConfigRow",
    "DataFactorySceneStepRow",
    "DataFactorySceneStepSqlConfigRow",
    "DataFactorySceneVersionRow",
    "DataFactoryServiceEndpointRow",
    "DataFactorySqlSourceRow",
    "DataFactorySqlTemplateRow",
    "DataFactorySystemRow",
    "DataFactoryTaskRow",
    "DataFactoryTaskVersionRow",
]
