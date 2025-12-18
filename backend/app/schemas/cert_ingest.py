from pydantic import BaseModel, Field


class CertIngestRequest(BaseModel):
    dry_run: bool = False
    limit: int = Field(0, ge=0)


class CertIngestResponse(BaseModel):
    inserted: int
    updated: int
    failed: int
    total: int
    errors: list[str]
