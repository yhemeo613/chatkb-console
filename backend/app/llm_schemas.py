# -*- coding: utf-8 -*-
"""模型中心 Schema"""
from pydantic import BaseModel, Field


class ProviderIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    vendor: str
    base_url: str = ""
    api_key: str = ""
    enabled: bool = True
    extra_models: list[str] = []


class ProviderUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    enabled: bool | None = None
    extra_models: list[str] | None = None
