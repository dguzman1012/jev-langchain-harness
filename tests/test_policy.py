from pr_risk.classify import classify_files
from pr_risk.policy import decide
from pr_risk.types import ChangedFile, Signal


def test_high_when_query_signal_fires() -> None:
    result = decide(
        [
            Signal("src/billing/invoices.py", "changes_db_query", 0.92, 0.84, "data"),
            Signal("src/billing/invoices.py", "changes_api_endpoint", 0.08, 0.84, "moderate"),
        ]
    )
    assert result.tier == "high"
    assert result.bumped_for_low_confidence is False
    assert result.reasons[0].signal == "changes_db_query"
    assert result.reasons[0].file == "src/billing/invoices.py"


def test_moderate_when_endpoint_signal_fires() -> None:
    result = decide(
        [
            Signal("src/api/routes/accounts.py", "changes_db_query", 0.06, 0.88, "data"),
            Signal(
                "src/api/routes/accounts.py",
                "changes_api_endpoint",
                0.88,
                0.76,
                "moderate",
            ),
        ]
    )
    assert result.tier == "moderate"
    assert result.bumped_for_low_confidence is False
    assert result.reasons[0].signal == "changes_api_endpoint"


def test_low_when_only_ui_and_no_raise() -> None:
    result = decide(
        [
            Signal("web/styles/button.css", "changes_db_query", 0.04, 0.92, "data"),
            Signal("web/styles/button.css", "changes_api_endpoint", 0.05, 0.90, "moderate"),
            Signal("web/styles/button.css", "only_ui_style_or_copy", 0.91, 0.82, "low"),
        ]
    )
    assert result.tier == "low"
    assert result.bumped_for_low_confidence is False


def test_low_confidence_on_deciding_question_bumps_one_tier() -> None:
    # 0.48 is below the high threshold; derived confidence is 0.04.
    result = decide(
        [
            Signal("src/services/fees.py", "changes_db_query", 0.48, 0.04, "data"),
            Signal("src/services/fees.py", "changes_api_endpoint", 0.10, 0.80, "moderate"),
        ]
    )
    assert result.tier == "moderate"
    assert result.bumped_for_low_confidence is True
    assert result.reasons[0].signal == "changes_db_query"
    assert result.reasons[0].probability == 0.48


def test_path_rule_alone_is_high_without_jev() -> None:
    files = [
        ChangedFile(
            path="db/migrations/0001_init.sql",
            status="added",
            additions=12,
            deletions=0,
            patch="-- create table invoices\n",
            language="sql",
        )
    ]
    result = classify_files(files, ask=lambda _state: [])
    assert result.tier == "high"
    assert result.reasons[0].signal == "path:migrations"
