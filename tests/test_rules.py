from pathlib import Path

from pr_risk.parse import parse_unified_diff
from pr_risk.rules import matching_rule, path_matches, should_skip
from pr_risk.types import ChangedFile

SAMPLES = {
    "query": "pr_risk/samples/query_change.diff",
    "endpoint": "pr_risk/samples/new_endpoint.diff",
    "css": "pr_risk/samples/css_button.diff",
}


def _file(path: str, patch: str = "x") -> ChangedFile:
    return ChangedFile(path, "modified", 1, 0, patch, "text")


def test_migration_and_sql_raise_data() -> None:
    assert matching_rule("db/migrations/0001_init.sql") == ("migrations", "raise_data")
    assert matching_rule("reports/overdue.sql") == ("sql", "raise_data")
    assert matching_rule("app/models.py") == ("schema_models", "raise_data")


def test_api_path_raises_moderate() -> None:
    assert matching_rule("src/api/routes/accounts.py") == ("api_routes", "raise_moderate")


def test_docs_tests_styles_lower_floor() -> None:
    assert matching_rule("README.md") == ("docs", "lower_floor")
    assert matching_rule("tests/test_policy.py") == ("tests", "lower_floor")
    assert matching_rule("web/styles/button.css") == ("styles", "lower_floor")


def test_unlisted_source_has_no_path_rule() -> None:
    assert matching_rule("src/billing/invoices.py") is None


def test_skip_lockfile_and_binary() -> None:
    assert should_skip(_file("uv.lock"))
    assert should_skip(_file("package-lock.json"))
    assert should_skip(_file("assets/logo.png", patch=""))
    assert not should_skip(_file("src/app.py"))


def test_glob_matches_nested_paths() -> None:
    assert path_matches("backend/alembic/versions/0002.py", "**/alembic/versions/**")
    assert path_matches("web/styles/button.css", "**/*.css")


def test_samples_parse_to_expected_paths() -> None:
    query = parse_unified_diff(Path(SAMPLES["query"]).read_text(encoding="utf-8"))
    endpoint = parse_unified_diff(Path(SAMPLES["endpoint"]).read_text(encoding="utf-8"))
    css = parse_unified_diff(Path(SAMPLES["css"]).read_text(encoding="utf-8"))
    assert [f.path for f in query] == ["src/billing/invoices.py"]
    assert [f.path for f in endpoint] == ["src/api/routes/accounts.py"]
    assert [f.path for f in css] == ["web/styles/button.css"]
    assert query[0].additions > 0
    assert endpoint[0].status == "modified"
