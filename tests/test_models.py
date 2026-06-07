import pytest
from marktplaats_bot.models import Search, Result, Feedback


def test_search_json_fields_default():
    s = Search(query_text="test")
    assert s.required_specs == []
    assert s.required_brands == []
    assert s.excluded_brands == []


def test_search_json_fields_roundtrip():
    s = Search(query_text="test")
    s.required_specs = ["SSD", "16GB RAM"]
    s.required_brands = ["Apple", "Dell"]
    s.excluded_brands = ["Acer"]
    assert s.required_specs == ["SSD", "16GB RAM"]
    assert s.required_brands == ["Apple", "Dell"]
    assert s.excluded_brands == ["Acer"]


def test_feedback_parsed_changes_default():
    f = Feedback(search_id=1, text="hello")
    assert f.parsed_changes == {}


def test_feedback_parsed_changes_roundtrip():
    f = Feedback(search_id=1, text="budget 500")
    f.parsed_changes = {"max_budget": 500.0}
    assert f.parsed_changes == {"max_budget": 500.0}
