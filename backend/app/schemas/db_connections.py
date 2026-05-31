from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

class DBConnectionBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    db_type: Literal["postgres", "mysql", "sqlite"]
    host: str
    port: int
    database: str
    username: str

class DBConnectionCreate(DBConnectionBase):
    password: str

class DBConnectionOut(DBConnectionBase):
    id: str
    user_id: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class TestConnectionRequest(BaseModel):
    db_type: Literal["postgres", "mysql", "sqlite"]
    host: str
    port: int
    database: str
    username: str
    password: str

class TestConnectionResponse(BaseModel):
    success: bool
    message: str

class ImportRequest(BaseModel):
    mode: Literal["table", "query"]
    name: Optional[str] = None
    schema_name: Optional[str] = Field(None, alias="schema")
    table: Optional[str] = None
    sql: Optional[str] = None
    row_limit: Optional[int] = None
    
class ImportResponse(BaseModel):
    dataset_id: str
    storage_path: str
    row_count: int
    background_job_id: Optional[str] = None

class TableInfo(BaseModel):
    schema_name: Optional[str] = Field(None, alias="schema")
    name: str
    type: str

class ColumnInfo(BaseModel):
    name: str
    type: str

class DBConnectionDetailOut(DBConnectionOut):
    tables: list[TableInfo]
