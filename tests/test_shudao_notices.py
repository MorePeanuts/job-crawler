import pytest

from job_crawler.adapters.shudao_notices import announcement_deadline
from job_crawler.transport import CrawlError


@pytest.mark.parametrize(
    "body,expected",
    [
        (
            "毕业时间2027年8月31日\n报名时间：自公告发布之日起至2026年10月22日17:00止。",
            "2026-10-22 17:00:00",
        ),
        ("报名时间：2026.09.01—2026.10.20。", "2026-10-20"),
        ("报名截止时间为2026-10-31。\n年龄要求35岁", "2026-10-31"),
    ],
)
def test_only_explicit_application_end_is_used(body: str, expected: str) -> None:
    assert announcement_deadline(body) == expected


@pytest.mark.parametrize(
    "body",
    [
        "报名时间：10月22日截止。",
        "报名时间：2026年10月12日。",
        "报名时间2026-10-22至2026-10-12",
        "报名截止时间2026年10月22日\n另一项目报名截止时间2026年11月01日",
    ],
)
def test_ambiguous_missing_year_or_start_only_is_a_gap(body: str) -> None:
    with pytest.raises(CrawlError):
        announcement_deadline(body)


def test_announcement_without_application_deadline_preserves_missing() -> None:
    assert announcement_deadline("招聘流程：在线投递简历、面试、签约") == ""
    assert announcement_deadline("毕业时间为2027年8月31日，年龄以报名截止时间为准。") == ""
