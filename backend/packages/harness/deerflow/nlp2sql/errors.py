class Nlp2SqlError(Exception):
    """Base error for the nlp2sql module."""


class DataSourceNotFoundError(Nlp2SqlError):
    """Raised when a data source cannot be found."""


class DataSourceAlreadyExistsError(Nlp2SqlError):
    """Raised when creating a data source with an existing ID."""


class NoDataSourceSelectedError(Nlp2SqlError):
    """Raised when a thread has not selected a data source yet."""


class DataSourceValidationError(Nlp2SqlError):
    """Raised when a data source definition is invalid."""


class DatabaseConnectionError(Nlp2SqlError):
    """Raised when the database connection fails."""


class DatabaseExecutionError(Nlp2SqlError):
    """Raised when query execution fails."""


class QuerySafetyError(Nlp2SqlError):
    """Raised when validation determines that a query is unsafe to run."""


class SchemaLookupError(Nlp2SqlError):
    """Raised when schema metadata cannot be found."""
