"""Live database connector service for Postgres, MySQL, and SQLite.

Enforces strict security rules:
- Read-only queries only.
- SSRF protection against private IP ranges.
- Safe chunked exporting to avoid memory bloat.
"""

import io
import ipaddress
import logging
import re
import socket
from contextlib import contextmanager
from typing import Any, Dict, List

import sqlalchemy
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.event import listens_for

from ..config import Settings

log = logging.getLogger(__name__)

# Destructive keywords (case-insensitive) we block in custom queries.
_DESTRUCTIVE_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", 
    "CREATE", "GRANT", "REVOKE", "CALL", "EXEC"
}

class DBConnectorError(Exception):
    """Base error for DB connection issues."""
    pass

class SSRFBlockedError(DBConnectorError):
    """Raised when the host resolves to a private IP."""
    pass

def _resolve_and_check_ssrf(host: str, settings: Settings) -> None:
    """Resolve the host and check if it points to a private/local IP."""
    # Skip SSRF check for SQLite, which is file-based
    if not host or host == ":memory:":
        return

    if settings.dev_allow_private_db_hosts:
        return

    try:
        ip_addr = socket.gethostbyname(host)
    except socket.gaierror as e:
        raise DBConnectorError(f"Could not resolve host '{host}': {e}") from e

    try:
        ip = ipaddress.ip_address(ip_addr)
    except ValueError as e:
        raise DBConnectorError(f"Invalid IP resolved for host '{host}': {e}") from e

    if ip.is_private or ip.is_loopback or ip.is_link_local:
        raise SSRFBlockedError(f"Connection to private host '{host}' ({ip_addr}) is blocked.")

def make_engine(conn_info: dict[str, Any], settings: Settings) -> Engine:
    """Create a SQLAlchemy engine tailored for read-only access."""
    db_type = conn_info.get("db_type")
    
    if db_type == "sqlite":
        # SQLite uses the database field as the path.
        path = conn_info.get("database", ":memory:")
        uri = f"sqlite:///file:{path}?mode=ro&uri=true" if path != ":memory:" else "sqlite:///:memory:"
        return create_engine(uri)
    
    host = conn_info.get("host", "")
    _resolve_and_check_ssrf(host, settings)

    port = conn_info.get("port")
    user = conn_info.get("username", "")
    password = conn_info.get("password", "")
    db = conn_info.get("database", "")

    if db_type == "postgres":
        uri = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
        return create_engine(
            uri,
            pool_pre_ping=True,
            connect_args={"options": "-c default_transaction_read_only=on"},
        )
    elif db_type == "mysql":
        uri = f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}"
        engine = create_engine(uri, pool_pre_ping=True)
        
        # Enforce read-only for MySQL via event listener on connect
        @listens_for(engine, "connect")
        def set_read_only(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.close()
            
        return engine
    else:
        raise DBConnectorError(f"Unsupported db_type: {db_type}")

def test_connection(conn_info: dict[str, Any], settings: Settings) -> None:
    """Test the connection by creating an engine and running SELECT 1."""
    try:
        engine = make_engine(conn_info, settings)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SSRFBlockedError:
        raise
    except Exception as e:
        raise DBConnectorError(f"Connection failed: {e}") from e

def list_tables(engine: Engine) -> List[Dict[str, str]]:
    """List tables and views in the database."""
    inspector = inspect(engine)
    results = []
    
    # Standardize handling of schemas across dialects
    schemas = inspector.get_schema_names() if engine.dialect.name == "postgresql" else [None]
    
    for schema in schemas:
        if schema in ("information_schema", "pg_catalog", "pg_toast"):
            continue
            
        for table_name in inspector.get_table_names(schema=schema):
            results.append({"schema": schema, "name": table_name, "type": "table"})
            
        for view_name in inspector.get_view_names(schema=schema):
            results.append({"schema": schema, "name": view_name, "type": "view"})
            
    return results

def describe_table(engine: Engine, schema: str | None, table_name: str) -> List[Dict[str, str]]:
    """Get columns and types for a specific table."""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name, schema=schema)
    return [{"name": col["name"], "type": str(col["type"])} for col in columns]

def validate_query(sql: str) -> None:
    """Validate that the query is safe (read-only, no destructive operations)."""
    if not sql or not sql.strip():
        raise DBConnectorError("Query is empty")
        
    sql = sql.strip()
    
    # 1. Must start with SELECT or WITH
    upper_sql = sql.upper()
    if not (upper_sql.startswith("SELECT ") or upper_sql.startswith("WITH ")):
        raise DBConnectorError("Query must begin with SELECT or WITH")
        
    # 2. Block multiple statements (no semicolons followed by other commands)
    # A simple but conservative check: no semicolons allowed unless they are at the very end
    parts = sql.split(";")
    if len(parts) > 2 or (len(parts) == 2 and parts[1].strip() != ""):
        raise DBConnectorError("Multiple SQL statements are not allowed")
        
    # 3. Block destructive keywords
    tokens = re.findall(r'\b[A-Za-z]+\b', upper_sql)
    for token in tokens:
        if token in _DESTRUCTIVE_KEYWORDS:
            raise DBConnectorError(f"Destructive keyword '{token}' is not allowed")

async def _export_query_to_storage(
    engine: Engine, 
    query: str, 
    sb_client, 
    storage_path: str, 
    limit: int | None, 
    settings: Settings
) -> int:
    """Execute query, chunk results into a CSV, and upload to storage."""
    import pandas as pd
    
    max_rows = settings.db_import_max_rows
    if limit is not None:
        max_rows = min(limit, max_rows)
        
    # Apply limit to the query if possible (simple approach)
    # SQLAlchemy's text() execution with chunksize from pandas handles the stream
    
    row_count = 0
    chunks = []
    
    with engine.connect().execution_options(stream_results=True) as conn:
        # Pandas read_sql supports chunksize to stream results
        try:
            for chunk in pd.read_sql(text(query), conn, chunksize=10000):
                remaining = max_rows - row_count
                if remaining <= 0:
                    break
                    
                if len(chunk) > remaining:
                    chunk = chunk.head(remaining)
                    
                chunks.append(chunk)
                row_count += len(chunk)
                
                if row_count >= max_rows:
                    break
        except Exception as e:
            raise DBConnectorError(f"Failed to execute query: {e}") from e

    if not chunks:
        raise DBConnectorError("Query returned no rows")

    # Combine chunks and write to CSV
    # For very large datasets, we'd stream directly to the bucket, 
    # but the current architecture uploads full byte strings.
    # The limit (e.g. 1M rows) ensures this fits in memory.
    final_df = pd.concat(chunks, ignore_index=True)
    
    csv_buf = io.BytesIO()
    final_df.to_csv(csv_buf, index=False)
    csv_bytes = csv_buf.getvalue()
    
    await sb_client.storage_upload("datasets", storage_path, csv_bytes, content_type="text/csv")
    
    return row_count

async def import_table(
    engine: Engine,
    schema: str | None,
    table_name: str,
    limit: int | None,
    sb_client,
    storage_path: str,
    settings: Settings
) -> int:
    """Stream a table directly to Supabase storage."""
    # Properly quote identifiers
    if engine.dialect.name in ("postgresql", "sqlite"):
        quote = '"'
    elif engine.dialect.name == "mysql":
        quote = '`'
    else:
        quote = ''
        
    q_table = f"{quote}{table_name}{quote}"
    q_schema = f"{quote}{schema}{quote}." if schema else ""
    
    query = f"SELECT * FROM {q_schema}{q_table}"
    
    return await _export_query_to_storage(engine, query, sb_client, storage_path, limit, settings)

async def import_query(
    engine: Engine,
    sql: str,
    limit: int | None,
    sb_client,
    storage_path: str,
    settings: Settings
) -> int:
    """Stream a validated custom query to Supabase storage."""
    validate_query(sql)
    return await _export_query_to_storage(engine, sql, sb_client, storage_path, limit, settings)
