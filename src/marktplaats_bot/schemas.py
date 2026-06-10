import json
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class SearchCreate(BaseModel):
    query_text: str = Field(..., min_length=1, max_length=500)
    max_budget: Optional[float] = None
    radius_km: int = Field(default=25, ge=1, le=500)
    postcode: str = Field(default="3027CM", max_length=10)
    max_age_years: Optional[int] = Field(default=None, ge=0, le=50)
    required_specs: list[str] = []
    required_brands: list[str] = []
    excluded_brands: list[str] = []
    exclude_business: bool = False
    relevance_threshold: int = Field(default=60, ge=0, le=100)
    ranking_mode: str = Field(default="precise_fit", pattern="^(precise_fit|mispricing|time_in_market|popularity|distance)$")


class SearchQueryPatch(BaseModel):
    nl_keywords: Optional[str] = None
    en_keywords: Optional[str] = None
    required_brands: Optional[list[str]] = None
    excluded_brands: Optional[list[str]] = None
    required_specs: Optional[list[str]] = None
    relevance_threshold: Optional[int] = Field(default=None, ge=0, le=100)


class SearchResponse(BaseModel):
    id: int
    query_text: str
    nl_keywords: Optional[str]
    en_keywords: Optional[str]
    max_budget: Optional[float]
    radius_km: int
    postcode: str
    max_age_years: Optional[int]
    required_specs: list[str]
    required_brands: list[str]
    excluded_brands: list[str]
    exclude_business: bool
    relevance_threshold: int
    ranking_mode: str
    active: bool
    query_enhanced: bool
    created_at: datetime
    last_run_at: Optional[datetime]
    last_analyzed_at: Optional[datetime]
    result_count: int = 0
    new_count: int = 0
    irrelevant_count: int = 0
    feedback_count: int = 0
    last_feedback_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ResultResponse(BaseModel):
    id: int
    search_id: int
    listing_id: str
    title: str
    price: Optional[float]
    distance_km: Optional[float]
    posted_at: Optional[datetime]
    url: str
    photo_count: int
    description: Optional[str]
    seller_type: str
    relevance_score: int
    deal_score: int
    quality_score: int
    ai_score: Optional[int]
    ai_flags: Optional[list[str]]
    ai_reason: Optional[str]
    image_urls: Optional[list[str]]
    is_bidding: bool
    notified: bool
    seen: bool
    favorited: bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("ai_flags", mode="before")
    @classmethod
    def parse_ai_flags(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("image_urls", mode="before")
    @classmethod
    def parse_image_urls(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v


class VerdictCreate(BaseModel):
    ai_score: int = Field(..., ge=0, le=10)
    ai_flags: list[str] = []
    ai_reason: Optional[str] = None


class ParsedChanges(BaseModel):
    max_budget: Optional[float] = None
    radius_km: Optional[int] = None
    max_age_years: Optional[int] = None
    exclude_business: Optional[bool] = None
    relevance_threshold: Optional[int] = None
    add_required_brands: Optional[list[str]] = None
    add_excluded_brands: Optional[list[str]] = None
    add_required_specs: Optional[list[str]] = None
    remove_keywords: Optional[list[str]] = None
    add_keywords: Optional[list[str]] = None


class FeedbackCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class FeedbackPatch(BaseModel):
    text: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    parsed_changes: Optional[dict] = None


class FeedbackResponse(BaseModel):
    id: int
    search_id: int
    text: str
    parsed_changes: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    status: str
