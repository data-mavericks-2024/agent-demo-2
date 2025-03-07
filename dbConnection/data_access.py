from cachetools import cached, TTLCache
from snowflake.snowpark import Session
from snowflake.snowpark.exceptions import SnowparkSQLException
import logging


logger = logging.getLogger(__name__)

class dbResult:
    def __init__(self, columns, status, output, error=None, schema_errors=None):
        self.columns = columns
        self.status = status
        self.output = output
        self.error = error

    def to_dict(self):
        return {
            "columns": self.columns,
            "status": self.status,
            "output": self.output,
            "error": self.error,
        }


class DataAccess:
    def __init__(self, snowpark_session: Session):
        self.session = snowpark_session
        self.cache = TTLCache(maxsize=100, ttl=300)
        self.logger = logging.getLogger(f"{__name__}.DataAccess")
        

    def execute_query(self, sql_query, parameters=None):
        try:
            if parameters:
                formatted_query = sql_query
                self.logger.info("Into DataAccess.execute_query --> " + sql_query)
                if isinstance(parameters, dict):
                    for key, value in parameters.items():
                        formatted_query = formatted_query.replace(f":{key}", repr(value) if isinstance(value, str) else str(value))
                df = self.session.sql(formatted_query)
            else:
                df = self.session.sql(sql_query)
            results = df.collect()
            columns = df.columns
            output_rows = []
            for row in results:
                 output_rows.append(tuple(row))
            return dbResult(columns, "Success", output_rows)
        except SnowparkSQLException as e:
            return dbResult(None, "Failure", None, error=f"A Snowflake error occurred: {e}")
        except Exception as e:
            return dbResult(None, "Failure", None, error=f"An error occurred: {e}")