import base64
import datetime as dt
import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from ..config import Settings, get_settings
from ..deps import CurrentUser, get_current_user
from ..schemas.db_connections import (
    DBConnectionCreate,
    DBConnectionDetailOut,
    DBConnectionOut,
    ImportRequest,
    ImportResponse,
    TableInfo,
    TestConnectionRequest,
    TestConnectionResponse,
)
from ..services.crypto import decrypt, encrypt
from ..services.db_connectors import (
    DBConnectorError,
    SSRFBlockedError,
    describe_table,
    import_query,
    import_table,
    list_tables,
    make_engine,
    test_connection,
)
from ..supabase_client import SupabaseClient

log = logging.getLogger(__name__)

router = APIRouter(prefix="/db-connections", tags=["db_connections"])

async def _get_client(settings: Settings = Depends(get_settings)) -> SupabaseClient:
    return SupabaseClient(settings)

def _build_conn_info(row: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Reconstruct a dict matching the test/make payload from a DB row."""
    password = ""
    if row.get("encrypted_credentials"):
        # The DB returns bytea as base64 or hex depending on PostgREST settings.
        # But we encode it explicitly, or Supabase returns it as a string starting with \x.
        # Handling PostgREST bytea decoding:
        val = row["encrypted_credentials"]
        if val.startswith("\\x"):
            val = bytes.fromhex(val[2:])
        password = decrypt(val, settings)
        
    return {
        "db_type": row["db_type"],
        "host": row["host"],
        "port": row["port"],
        "database": row["database"],
        "username": row["username"],
        "password": password,
    }

@router.post("", response_model=DBConnectionOut)
async def create_connection(
    req: DBConnectionCreate,
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    sb: SupabaseClient = Depends(_get_client),
):
    try:
        # First, test the connection
        try:
            test_connection(req.model_dump(), settings)
        except SSRFBlockedError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"blocked_host: {e}")
        except DBConnectorError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Connection failed: {e}")

        # Encrypt the password
        encrypted_pass = encrypt(req.password, settings)
        
        # We need to format bytea for PostgREST: \x followed by hex
        encoded_creds = "\\x" + encrypted_pass.hex()
        
        # Save to DB
        created = await sb.table_insert(
            "db_connections",
            {
                "user_id": user.id,
                "name": req.name,
                "db_type": req.db_type,
                "host": req.host,
                "port": req.port,
                "database": req.database,
                "username": req.username,
                "encrypted_credentials": encoded_creds,
            },
        )
        
        row = created[0]
        # Remove the credentials before returning
        row.pop("encrypted_credentials", None)
        return row
    finally:
        await sb.close()

@router.get("", response_model=list[DBConnectionOut])
async def list_connections(
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
):
    try:
        rows = await sb.table_get(
            "db_connections",
            {
                "user_id": f"eq.{user.id}",
                "select": "id,user_id,name,db_type,host,port,database,username,created_at",
                "order": "created_at.desc",
            },
        )
        return rows
    finally:
        await sb.close()

@router.get("/{conn_id}", response_model=DBConnectionDetailOut)
async def get_connection_detail(
    conn_id: str,
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    sb: SupabaseClient = Depends(_get_client),
):
    try:
        rows = await sb.table_get(
            "db_connections",
            {
                "id": f"eq.{conn_id}",
                "user_id": f"eq.{user.id}",
                "select": "*",
            },
        )
        if not rows:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
            
        row = rows[0]
        conn_info = _build_conn_info(row, settings)
        
        # Connect to DB and get tables
        try:
            engine = make_engine(conn_info, settings)
            tables = list_tables(engine)
        except Exception as e:
            log.warning(f"Failed to fetch tables for connection {conn_id}: {e}")
            tables = []
            
        row.pop("encrypted_credentials", None)
        row["tables"] = tables
        return row
    finally:
        await sb.close()

@router.delete("/{conn_id}")
async def delete_connection(
    conn_id: str,
    user: CurrentUser = Depends(get_current_user),
    sb: SupabaseClient = Depends(_get_client),
):
    try:
        await sb.table_delete(
            "db_connections",
            {"id": f"eq.{conn_id}", "user_id": f"eq.{user.id}"},
        )
        return {"success": True}
    finally:
        await sb.close()

@router.post("/test", response_model=TestConnectionResponse)
async def test_new_connection(
    req: TestConnectionRequest,
    settings: Settings = Depends(get_settings),
):
    try:
        test_connection(req.model_dump(), settings)
        return {"success": True, "message": "Connection successful"}
    except SSRFBlockedError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"blocked_host: {e}")
    except DBConnectorError as e:
        return {"success": False, "message": str(e)}

@router.post("/{conn_id}/test", response_model=TestConnectionResponse)
async def test_existing_connection(
    conn_id: str,
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    sb: SupabaseClient = Depends(_get_client),
):
    try:
        rows = await sb.table_get(
            "db_connections",
            {"id": f"eq.{conn_id}", "user_id": f"eq.{user.id}"},
        )
        if not rows:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
            
        conn_info = _build_conn_info(rows[0], settings)
        try:
            test_connection(conn_info, settings)
            return {"success": True, "message": "Connection successful"}
        except SSRFBlockedError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"blocked_host: {e}")
        except DBConnectorError as e:
            return {"success": False, "message": str(e)}
    finally:
        await sb.close()

@router.get("/{conn_id}/describe")
async def describe_db_table(
    conn_id: str,
    table: str,
    schema_name: str | None = None,
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    sb: SupabaseClient = Depends(_get_client),
):
    try:
        rows = await sb.table_get(
            "db_connections",
            {"id": f"eq.{conn_id}", "user_id": f"eq.{user.id}"},
        )
        if not rows:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
            
        conn_info = _build_conn_info(rows[0], settings)
        
        try:
            engine = make_engine(conn_info, settings)
            columns = describe_table(engine, schema_name, table)
            return {"columns": columns}
        except Exception as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    finally:
        await sb.close()

@router.post("/{conn_id}/import", response_model=ImportResponse)
async def import_data(
    conn_id: str,
    req: ImportRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    sb: SupabaseClient = Depends(_get_client),
):
    try:
        rows = await sb.table_get(
            "db_connections",
            {"id": f"eq.{conn_id}", "user_id": f"eq.{user.id}"},
        )
        if not rows:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
            
        conn_row = rows[0]
        conn_info = _build_conn_info(conn_row, settings)
        
        # Build safe dataset name
        safe_name = "".join(c if c.isalnum() else "_" for c in (req.name or req.table or "import"))
        import_id = str(uuid.uuid4())
        storage_path = f"{user.id}/{import_id}-{safe_name}.csv"
        
        dataset_name = req.name
        if not dataset_name:
            if req.mode == "table":
                dataset_name = f"{conn_row['name']} - {req.table}"
            else:
                dataset_name = f"{conn_row['name']} - Custom Query"
                
        # For simplicity, we execute synchronously here if we're not exceeding a large limit.
        # But for robustness, we'll run it in background if the limit is large.
        # In a real app we might always run this in the background, but this aligns with phase 1.
        
        # First create the dataset entry
        created_ds = await sb.table_insert(
            "datasets",
            {
                "user_id": user.id,
                "name": dataset_name,
                "source_type": "db_connection",
                "storage_path": storage_path,
                "status": "uploaded", # It will be profiling soon
            },
        )
        dataset_id = created_ds[0]["id"]
        
        # Schedule the background task for the import
        job = await sb.table_insert(
            "analysis_jobs",
            {
                "user_id": user.id,
                "dataset_id": dataset_id,
                "job_type": "db_import",
                "status": "queued",
            },
        )
        job_id = job[0]["id"]
        
        background_tasks.add_task(
            _run_import_job,
            settings=settings,
            job_id=job_id,
            dataset_id=dataset_id,
            user_id=user.id,
            conn_info=conn_info,
            req=req.model_dump(),
            storage_path=storage_path,
        )
        
        return ImportResponse(
            dataset_id=dataset_id,
            storage_path=storage_path,
            row_count=0,
            background_job_id=job_id,
        )
    finally:
        await sb.close()

async def _run_import_job(
    settings: Settings,
    job_id: str,
    dataset_id: str,
    user_id: str,
    conn_info: dict[str, Any],
    req: dict[str, Any],
    storage_path: str,
):
    sb = SupabaseClient(settings)
    now = lambda: dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        await sb.table_update(
            "analysis_jobs",
            {"id": f"eq.{job_id}"},
            {"status": "running", "updated_at": now()},
        )
        
        engine = make_engine(conn_info, settings)
        
        if req["mode"] == "table":
            row_count = await import_table(
                engine, req.get("schema"), req["table"], req.get("row_limit"), sb, storage_path, settings
            )
        else:
            row_count = await import_query(
                engine, req["sql"], req.get("row_limit"), sb, storage_path, settings
            )
            
        # Update the dataset with correct row count and trigger profiling
        await sb.table_update(
            "datasets",
            {"id": f"eq.{dataset_id}"},
            {"row_count": row_count, "status": "uploaded"}
        )
        
        # Trigger profiling background job directly via another job
        prof_job = await sb.table_insert(
            "analysis_jobs",
            {
                "user_id": user_id,
                "dataset_id": dataset_id,
                "job_type": "profile",
                "status": "queued",
            },
        )
        
        # Need to fetch the raw version ID that was auto-created by the DB trigger
        versions = await sb.table_get(
            "dataset_versions",
            {"dataset_id": f"eq.{dataset_id}", "label": "eq.raw"}
        )
        version_id = versions[0]["id"]
        
        from ..routers.datasets import _run_profile_job
        # We can't easily await a background task directly, but we can call the coroutine directly here
        # since we are already in a background context
        await _run_profile_job(
            settings=settings,
            job_id=prof_job[0]["id"],
            dataset_id=dataset_id,
            version_id=version_id,
            storage_path=storage_path,
            source_type="db_connection",
            update_dataset_summary=True,
        )
            
        await sb.table_update(
            "analysis_jobs",
            {"id": f"eq.{job_id}"},
            {"status": "succeeded", "updated_at": now(), "result_json": {"row_count": row_count}},
        )
    except Exception as exc:
        log.exception("db_import job %s failed", job_id)
        try:
            await sb.table_update(
                "analysis_jobs",
                {"id": f"eq.{job_id}"},
                {"status": "failed", "updated_at": now(), "error": str(exc)[:1000]},
            )
            await sb.table_update(
                "datasets",
                {"id": f"eq.{dataset_id}"},
                {"status": "error"}
            )
        except Exception:
            pass
    finally:
        await sb.close()
