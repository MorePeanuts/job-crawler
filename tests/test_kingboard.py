"""Official inline document boundaries, distinct sections, and excluded programme."""

from pathlib import Path
from typing import cast

import pytest

from job_crawler.adapters.kingboard import CAREERS, STUDENTS, UNIT, KingboardCareers, catalog
from job_crawler.models import Source
from job_crawler.transport import Session

FIX = Path(__file__).parent / "fixtures/kingboard"


class Replay:
    last_evidence = "initial"

    def __init__(self, fault=""):
        self.fault = fault
        self.calls = []

    async def open(self, url, *, ready_endpoints=()):
        assert url == CAREERS

    async def request_html(self, url):
        self.calls.append(url)
        assert url in {CAREERS, STUDENTS}
        self.last_evidence = url
        name = "careers" if url == CAREERS else "students"
        text = (FIX / f"{name}.html").read_text()
        if name == "careers":
            changes = {
                "unit": (UNIT, "另一家企业"),
                "missing_title": ("计划招用的岗位：维修电工", "维修电工"),
                "empty_title": ("计划招用的岗位：维修电工", "计划招用的岗位："),
                "requirements": ("岗位需求：", "未知章节："),
                "footer": ("公司地址：", "办公地点："),
                "contact": ("@kingboard.com", "@other.test"),
                "media": ("岗位需求：", '<img src="requirements.png">岗位需求：'),
                "extra_section": ("岗位需求：", "<div>额外岗位</div>岗位需求："),
                "pager": ("<main>", '<main><a rel="next" href="?page=2">下一页</a>'),
                "column": ("报名表格", "博士招聘"),
            }
            if self.fault in changes:
                a, b = changes[self.fault]
                text = text.replace(a, b, 1)
        if name == "students":
            if self.fault == "student_request":
                raise TimeoutError("student page unavailable")
            changes = {
                "student_scope": ("大學生實習計劃", "正式招聘"),
                "student_open": ("截止報名 (已以電郵通知入選者)", "报名中"),
                "student_attachment": ("202110111432321055.xlsx", "new-jobs.xlsx"),
                "student_graduate": ("20個實習職位", "20個實習職位，另招應屆畢業生"),
            }
            if self.fault in changes:
                a, b = changes[self.fault]
                text = text.replace(a, b)
        return text


def adapter(replay, now):
    return KingboardCareers(
        Source(source_id="COM0361", company_id="COM0361", company="建滔集团有限公司", url=CAREERS),
        cast(Session, replay),
        now,
    )


@pytest.mark.asyncio
async def test_complete_inline_catalog_and_closed_internship(now):
    replay = Replay()
    result = await adapter(replay, now).collect()
    assert not result.coverage_issues()
    assert replay.calls == [CAREERS, STUDENTS]
    assert len(result.jobs) == 14
    assert len({job.key for job in result.jobs}) == 14
    assert result.scopes[0].expected == result.scopes[0].details == 14
    assert result.scopes[1].unique == result.scopes[1].skipped_out_of_scope == 1
    grads = [job for job in result.jobs if job.work_type == "校招"]
    assert [job.title for job in grads] == ["工艺工程师"]
    job = grads[0]
    assert job.company == "建滔集团有限公司" and job.unit == UNIT
    assert "大专以上化工相关专业毕业（应届毕业生亦可）" in job.requirements
    assert "7000+" in job.requirements
    assert not any(
        (job.duties, job.education, job.published, job.deadline, job.location, job.address)
    )
    assert job.evidence == [CAREERS]
    assert next(j for j in result.jobs if j.title == "数控铣工").work_type == "未明确校招"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "unit",
        "missing_title",
        "empty_title",
        "requirements",
        "footer",
        "contact",
        "media",
        "extra_section",
        "pager",
        "column",
        "student_request",
        "student_scope",
        "student_open",
        "student_attachment",
        "student_graduate",
    ],
)
async def test_unverified_document_changes_are_partial(now, fault):
    result = await adapter(Replay(fault), now).collect()
    assert result.issues and result.coverage_issues()
    if fault.startswith("student_"):
        assert len(result.jobs) == 14
        assert result.scopes[0].terminal and not result.scopes[1].terminal


def test_same_title_sections_keep_distinct_identities():
    text = (FIX / "careers.html").read_text()
    rows = catalog(text.replace("计划招用的岗位：普工2", "计划招用的岗位：普工1"))
    same = [row for row in rows if row["title"] == "普工1"]
    assert len(same) == 2 and same[0]["id"] != same[1]["id"]
    assert same[0]["requirements"] != same[1]["requirements"]
