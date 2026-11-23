from datetime import datetime
from typing import Dict

from pydantic import BaseModel, ConfigDict, Field


class UploadUrlRequest(BaseModel):
    filename: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=255)


class UploadUrlResponse(BaseModel):
    document_id: str
    key: str
    url: str
    fields: Dict[str, str]


class VerifyUploadRequest(BaseModel):
    key: str = Field(min_length=1, max_length=512)


class UpdatePasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=255)


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    s3_key: str
    original_filename: str | None
    content_type: str
    size_bytes: int | None
    status: str
    error_message: str | None
    password_valid: bool | None
    created_at: datetime
    verified_at: datetime | None
