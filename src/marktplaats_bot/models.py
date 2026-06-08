from datetime import datetime
from typing import Optional
import json

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Search(Base):
    __tablename__ = "searches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_text: Mapped[str] = mapped_column(String(500), nullable=False)
    nl_keywords: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    en_keywords: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    max_budget: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    radius_km: Mapped[int] = mapped_column(Integer, default=25)
    postcode: Mapped[str] = mapped_column(String(10), default="3027CM")
    max_age_years: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    _required_specs: Mapped[Optional[str]] = mapped_column("required_specs", Text, nullable=True, default="[]")
    _required_brands: Mapped[Optional[str]] = mapped_column("required_brands", Text, nullable=True, default="[]")
    _excluded_brands: Mapped[Optional[str]] = mapped_column("excluded_brands", Text, nullable=True, default="[]")
    exclude_business: Mapped[bool] = mapped_column(Boolean, default=False)
    relevance_threshold: Mapped[int] = mapped_column(Integer, default=60)
    ranking_mode: Mapped[str] = mapped_column(String(50), default="precise_fit")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    results: Mapped[list["Result"]] = relationship("Result", back_populates="search", cascade="all, delete-orphan")
    feedbacks: Mapped[list["Feedback"]] = relationship("Feedback", back_populates="search", cascade="all, delete-orphan")

    @property
    def required_specs(self) -> list:
        return json.loads(self._required_specs or "[]")

    @required_specs.setter
    def required_specs(self, value: list):
        self._required_specs = json.dumps(value)

    @property
    def required_brands(self) -> list:
        return json.loads(self._required_brands or "[]")

    @required_brands.setter
    def required_brands(self, value: list):
        self._required_brands = json.dumps(value)

    @property
    def excluded_brands(self) -> list:
        return json.loads(self._excluded_brands or "[]")

    @excluded_brands.setter
    def excluded_brands(self, value: list):
        self._excluded_brands = json.dumps(value)


class Result(Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_id: Mapped[int] = mapped_column(Integer, ForeignKey("searches.id"), nullable=False)
    listing_id: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    distance_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    photo_count: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seller_type: Mapped[str] = mapped_column(String(20), default="unknown")
    relevance_score: Mapped[int] = mapped_column(Integer, default=0)
    deal_score: Mapped[int] = mapped_column(Integer, default=0)
    quality_score: Mapped[int] = mapped_column(Integer, default=0)
    ai_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ai_flags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    seen: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    search: Mapped["Search"] = relationship("Search", back_populates="results")


class Feedback(Base):
    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_id: Mapped[int] = mapped_column(Integer, ForeignKey("searches.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    _parsed_changes: Mapped[Optional[str]] = mapped_column("parsed_changes", Text, nullable=True, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    search: Mapped["Search"] = relationship("Search", back_populates="feedbacks")

    @property
    def parsed_changes(self) -> dict:
        return json.loads(self._parsed_changes or "{}")

    @parsed_changes.setter
    def parsed_changes(self, value: dict):
        self._parsed_changes = json.dumps(value)
