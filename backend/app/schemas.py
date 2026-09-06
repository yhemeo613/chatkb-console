# -*- coding: utf-8 -*-
"""Pydantic 请求/响应 Schema"""
from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    nickname: str = Field(default="", max_length=64)


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class KbCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    type: str = "docs"  # docs / persona
    embed_model: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None


class KbUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class SearchIn(BaseModel):
    query: str = Field(min_length=1)
    kb_ids: list[str] = []
    top_k: int | None = Field(default=None, ge=1, le=50)


class ReplyIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    person: str = ""
    history: str = ""
    model: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)
    temperature: float | None = Field(default=None, ge=0, le=2)


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    person: str = ""
    content: str = ""


class ProfileUpdate(BaseModel):
    content: str
