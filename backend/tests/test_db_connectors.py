import base64
import os
import sqlite3
import tempfile
from collections.abc import Generator

import pytest
from sqlalchemy import inspect, text

from app.config import Settings
from app.services.crypto import CryptoError, decrypt, encrypt
from app.services.db_connectors import (
    DBConnectorError,
    SSRFBlockedError,
    _resolve_and_check_ssrf,
    describe_table,
    import_query,
    import_table,
    list_tables,
    make_engine,
    test_connection as db_test_connection,
    validate_query,
)

# --- Crypto Tests ---

def test_crypto_round_trip():
    settings = Settings(db_encryption_key=base64.urlsafe_b64encode(os.urandom(32)).decode())
    plaintext = "super-secret-password"
    
    ciphertext = encrypt(plaintext, settings)
    assert ciphertext != plaintext.encode()
    
    decrypted = decrypt(ciphertext, settings)
    assert decrypted == plaintext

def test_crypto_tamper_rejection():
    settings = Settings(db_encryption_key=base64.urlsafe_b64encode(os.urandom(32)).decode())
    plaintext = "super-secret-password"
    
    ciphertext = encrypt(plaintext, settings)
    
    # Tamper with the ciphertext (flip a byte)
    tampered = bytearray(ciphertext)
    tampered[10] = tampered[10] ^ 0xFF
    
    with pytest.raises(CryptoError):
        decrypt(bytes(tampered), settings)

def test_crypto_missing_key():
    settings = Settings(db_encryption_key="")
    with pytest.raises(CryptoError):
        encrypt("test", settings)

# --- SSRF Tests ---

def test_ssrf_guard_blocks_private():
    settings = Settings(dev_allow_private_db_hosts=False)
    
    private_hosts = [
        "127.0.0.1", "localhost", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.0.1"
    ]
    
    for host in private_hosts:
        with pytest.raises(SSRFBlockedError) as exc:
            _resolve_and_check_ssrf(host, settings)
        assert "blocked" in str(exc.value).lower()

def test_ssrf_guard_allows_public(monkeypatch):
    settings = Settings(dev_allow_private_db_hosts=False)
    
    # Mock socket resolution to return a public IP
    import socket
    monkeypatch.setattr(socket, "gethostbyname", lambda h: "8.8.8.8")
    
    # Should not raise
    _resolve_and_check_ssrf("public.database.com", settings)

def test_ssrf_guard_override():
    settings = Settings(dev_allow_private_db_hosts=True)
    # Should not raise even for localhost
    _resolve_and_check_ssrf("127.0.0.1", settings)

# --- SQL Validator Tests ---

def test_sql_validator_accepts_safe():
    validate_query("SELECT * FROM users")
    validate_query("   select id, name from table  ")
    validate_query("WITH cte AS (SELECT * FROM a) SELECT * FROM cte")
    validate_query("SELECT 1")

def test_sql_validator_rejects_destructive():
    destructive_queries = [
        "SELECT * FROM x; DROP TABLE users",
        "SELECT 1; UPDATE users SET name='hacked'",
        "WITH cte AS (SELECT 1) DELETE FROM records WHERE id=1",
        "SELECT * FROM logs; INSERT INTO x VALUES (1)",
        "SELECT 1; ALTER TABLE x ADD COLUMN y INT",
        "SELECT * FROM a; TRUNCATE TABLE logs",
        "SELECT 1; CREATE TABLE oops (id INT)",
        "SELECT 1; GRANT ALL PRIVILEGES ON database.* TO 'user'@'%'",
        "SELECT 1; REVOKE ALL PRIVILEGES",
        "SELECT * FROM t; CALL some_proc()",
        "SELECT 1; EXEC master..xp_cmdshell"
    ]
    
    for q in destructive_queries:
        with pytest.raises(DBConnectorError) as exc:
            validate_query(q)
        assert "not allowed" in str(exc.value)

def test_sql_validator_rejects_multiple_statements():
    with pytest.raises(DBConnectorError) as exc:
        validate_query("SELECT * FROM a; SELECT * FROM b")
    assert "multiple" in str(exc.value).lower()

# --- SQLite Integration Tests ---

@pytest.fixture
def sqlite_db() -> Generator[str, None, None]:
    """Creates a temporary SQLite database with test data."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)")
    cursor.execute("CREATE VIEW adults AS SELECT * FROM users WHERE age >= 18")

    # Insert 10 rows
    for i in range(10):
        cursor.execute("INSERT INTO users (name, age) VALUES (?, ?)", (f"User {i}", 15 + i))

    conn.commit()
    conn.close()

    yield path
    # Windows file-handle cleanup is non-deterministic when a SQLAlchemy engine
    # was opened on the same file — encourage GC, then retry deletion a few
    # times. The temp file is harmless if the OS cleans it up later.
    import gc
    import time
    gc.collect()
    for _ in range(5):
        try:
            os.remove(path)
            break
        except PermissionError:
            time.sleep(0.1)
            gc.collect()

class MockSupabaseClient:
    def __init__(self):
        self.uploads = []
        
    async def storage_upload(self, bucket, path, data, content_type):
        self.uploads.append({"bucket": bucket, "path": path, "data": data})

def test_sqlite_integration(sqlite_db: str):
    import asyncio
    settings = Settings(dev_allow_private_db_hosts=True)
    conn_info = {"db_type": "sqlite", "database": sqlite_db}
    
    # 1. Test connection
    db_test_connection(conn_info, settings)
    
    # 2. Make engine
    engine = make_engine(conn_info, settings)
    
    # 3. List tables
    tables = list_tables(engine)
    assert len(tables) >= 2
    table_names = [t["name"] for t in tables]
    assert "users" in table_names
    assert "adults" in table_names
    
    # 4. Describe table
    cols = describe_table(engine, None, "users")
    assert len(cols) == 3
    assert cols[0]["name"] == "id"
    assert "INTEGER" in cols[0]["type"]
    
    # 5. Import table (with row cap)
    sb_client = MockSupabaseClient()
    row_count = asyncio.run(import_table(
        engine, None, "users", limit=5, sb_client=sb_client, 
        storage_path="test/users.csv", settings=settings
    ))
    
    assert row_count == 5
    assert len(sb_client.uploads) == 1
    assert b"User 0" in sb_client.uploads[0]["data"]
    assert b"User 5" not in sb_client.uploads[0]["data"]
    
    # 6. Import query
    row_count2 = asyncio.run(import_query(
        engine, "SELECT * FROM users WHERE age >= 20", limit=None, 
        sb_client=sb_client, storage_path="test/query.csv", settings=settings
    ))
    
    assert row_count2 == 5  # Users 5-9
    assert len(sb_client.uploads) == 2

    # Dispose engine so SQLite file is released and can be deleted on Windows
    engine.dispose()
