from __future__ import annotations

from pydantic import BaseModel, Field


class CertIngestRequest(BaseModel):
    dry_run: bool = False
    limit: int = Field(0, ge=0)
    prune_missing: bool = False
    dedupe: bool = False


class CertIngestError(BaseModel):
    filename: str
    reason: str | None = None
    exception: str | None = None


class CertIngestResponse(BaseModel):
    inserted: int
    updated: int
    failed: int
    total: int
    pruned: int = 0
    deduped: int = 0
    errors: list[CertIngestError]
