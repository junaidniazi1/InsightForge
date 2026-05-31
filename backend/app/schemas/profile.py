from typing import Any, Literal

from pydantic import BaseModel

# The profile JSON is large and nested; we don't model every leaf as a
# pydantic class — we just hand it through as a dict. Status envelopes
# and job records *are* modelled so the API contract is explicit.


JobStatus = Literal["queued", "running", "succeeded", "failed"]
ProfileStatus = Literal["needs_profiling", "running", "ready", "failed"]


class JobRecord(BaseModel):
    id: str
    status: JobStatus
    created_at: str | None = None
    updated_at: str | None = None
    error: str | None = None


class ProfileEnvelope(BaseModel):
    """What GET /datasets/{id}/profile returns.

    Discriminated by `status`:
      - needs_profiling: no profile yet, no job running. UI should call POST.
      - running:         a profiling job is in flight; `job` carries its state.
      - ready:           `profile` holds the latest profile JSON; `profiled_at`
                         is its timestamp.
      - failed:          the last job failed; `error` explains why.
    """
    status: ProfileStatus
    profile: dict[str, Any] | None = None
    profiled_at: str | None = None
    job: JobRecord | None = None
    error: str | None = None


class ProfileTriggerResponse(BaseModel):
    """What POST /datasets/{id}/profile returns immediately."""
    job: JobRecord
    already_running: bool = False
