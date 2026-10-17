import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from job_crawler.adapters import swhy
from job_crawler.adapters.moka import Moka
from job_crawler.config import IncrementalConfig
from job_crawler.incremental import IncrementalSource
from job_crawler.models import Collection, Scope, Source
from job_crawler.storage import Store


def source(host: str = "app.mokahr.com") -> Source:
    return Source(
        source_id="COM0419",
        company_id="COM0419",
        company="申万宏源集团股份有限公司",
        url=f"https://{host}/",
    )


class Replay:
    last_evidence = "fixture"

    def __init__(self, html: str = "", output: Path = Path("fixture")):
        self.html = html
        self.page = self
        self.output = output
        self.url = ""
        self.pages: dict[str, str] = {}

    async def content(self) -> str:
        return self.pages.get(self.url, self.html)

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.url = url
        self.last_evidence = str(self.output / "observed.json")

    async def evaluate(self, expression: str) -> str:
        return "https://app.mokahr.com/campus-recruitment/swhysc-job/166086#/job/test"

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError(needle)

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
        credentials: str = "include",
    ) -> dict[str, Any]:
        raise AssertionError(url)


def card(title: str, requirements: str) -> str:
    return f'<div class="tr"><div class="td"><table><tr><td>{title}</td><td>上海</td><td>若干</td><td>硕士</td></tr></table></div><div class="details" style="display:none"><b>职位描述：</b><p>开发和维护客户</p><b>职位要求：</b><p>{requirements}</p><b>联系方式：</b><p>邮箱：公开招聘邮箱</p></div></div>'


async def test_futures_hidden_fulltext_and_actual_cohort(now: datetime) -> None:
    html = (
        '申银万国期货有限公司 申万宏源证券子公司<div class="jobListBox">'
        + card("管培生", "2025年5月至2026年7月应届毕业生")
        + card("销售", "熟悉期货业务")
        + "</div>"
    )
    result = await swhy.Futures(source("www.sywgqh.com.cn"), Replay(html), now).collect()
    assert not result.coverage_issues() and len(result.jobs) == 1
    assert result.scopes[0].skipped_out_of_scope == 1
    assert result.jobs[0].source_key == "futures:管培生"
    assert "2026年7月" in result.jobs[0].requirements
    assert not result.jobs[0].published and not result.jobs[0].deadline


@pytest.mark.parametrize("change", ["attachment", "duplicate", "missing"])
async def test_futures_incomplete_details_fail(now: datetime, change: str) -> None:
    c = card("管培生", "应届毕业生")
    if change == "attachment":
        c = c.replace("</p>", '<img src="jobs.png"></p>', 1)
    if change == "duplicate":
        c += c
    if change == "missing":
        c = c.replace("职位要求：", "其他：")
    result = await swhy.Futures(
        source("www.sywgqh.com.cn"),
        Replay('申银万国期货有限公司 申万宏源证券子公司<div class="jobListBox">' + c + "</div>"),
        now,
    ).collect()
    assert result.coverage_issues()


async def test_securities_deadline_uses_public_year_and_faq_time(
    now: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    replay = Replay()
    replay.pages["https://app.mokahr.com/campus-recruitment/swhysc-job/166086#/job/test"] = (
        "申万宏源证券有限公司 2027届秋招允许2026年08月25日至2026年10月25日内投递1次"
    )
    replay.pages["https://app.mokahr.com/campus-recruitment/swhysc-job/148689"] = (
        "2027届校招 网申及测评完成时间最晚截至10月25日23:59"
    )

    async def harvest(self: Moka) -> None:
        assert isinstance(self, swhy.Securities) and self.deadline == "2026-10-25 23:59:00"
        self.result.scopes.append(Scope(name="fixture", expected=0, terminal=True))

    monkeypatch.setattr(Moka, "harvest", harvest)
    result = await swhy.Securities(source(), replay, now).collect()
    assert not result.coverage_issues()
    replay.pages["https://app.mokahr.com/campus-recruitment/swhysc-job/148689"] = (
        "2027届校招 网申及测评完成时间最晚截至10月24日23:59"
    )
    result = await swhy.Securities(source(), replay, now).collect()
    assert result.coverage_issues()


def navigation() -> str:
    links = dict(swhy.LINKS)
    links.update(
        {
            name: "https://app.mokahr.com/campus-recruitment/swhysc-job/166086#/jobs?zhineng=x"
            for name in ["总部岗位", "集团", "分支机构"]
        }
    )
    links.update(
        {
            name: "https://example.com"
            for name in ["【部门大揭秘】", "【小贴士、QA】", "长图文", "双选会行程", "云宣讲"]
        }
    )
    return "".join(f'<a title="{name}" href="{url}"></a>' for name, url in links.items())


async def test_five_branches_failure_isolation_and_evidence_namespace(
    now: datetime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = []

    async def harvest(self: swhy.Branch) -> None:
        opened.append(self.prefix)
        assert isinstance(self.session, Replay)
        assert self.session.output == tmp_path / self.prefix
        if self.prefix == "research":
            raise ValueError("blocked")
        self.result.scopes.append(
            Scope(name="same", expected=1, listed=1, unique=1, details=1, terminal=True)
        )
        self.result.jobs.append(self.job("same-id", title="岗位", source_url=self.source.url))

    for adapter in swhy.BRANCHES:
        monkeypatch.setattr(adapter, "harvest", harvest)
    replay = Replay(navigation(), tmp_path)
    result = await swhy.SwhyCampus(source(), replay, now).collect()
    assert len(opened) == 5 and len(result.jobs) == 4 and result.coverage_issues()
    assert len({job.source_key for job in result.jobs}) == 4
    assert len({job.evidence[0] for job in result.jobs}) == 4
    assert replay.output == tmp_path


async def test_missing_or_extra_subsidiary_fails_before_collection(now: datetime) -> None:
    for doc in [
        navigation().replace("宏源期货", "其他"),
        navigation() + '<a title="新子公司" href="https://example.com"></a>',
    ]:
        result = await swhy.SwhyCampus(source(), Replay(doc), now).collect()
        assert result.coverage_issues() and not result.jobs


class GuopinReplay(Replay):
    def __init__(self, mismatch: bool = False):
        super().__init__()
        self.mismatch = mismatch

    async def observed(self, needle: str) -> dict[str, Any]:
        company = swhy.Hongyuan.company_id
        if "index/v1/home?" in needle:
            data = {
                "company_info": {
                    "id": company,
                    "name": "宏源期货有限公司",
                    "group_name": "申万宏源集团股份有限公司",
                }
            }
        elif "/count?" in needle:
            data = {"company_job_count": 2, "lower_job_count": 1}
        elif "children-list?" in needle:
            data = [{"company_id": "child", "company_name": "分公司", "jobs_num": 1}]
        else:
            payload = {"page": 1, "page_size": 20}
            if "/sub/" in self.url:
                payload.update(
                    company_id_only_sub=company, order=[{"field": "update_time", "sort": "desc"}]
                )
            else:
                payload["company_id"] = [company]
            return {
                "url": "https://gp-api.iguopin.com/api/jobs/v1/home-job",
                "post_data": json.dumps(payload),
            }
        return {"body": json.dumps({"code": 200, "data": data})}

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
        credentials: str = "include",
    ) -> dict[str, Any]:
        assert credentials == "omit" and payload is not None and payload["page_size"] == 20
        child = "company_id_only_sub" in payload
        unit = "child" if child else swhy.Hongyuan.company_id
        names = ["intern-child"] if child else ["campus", "intern"]
        rows = [
            {
                "job_id": name,
                "job_name": name,
                "company_id": unit,
                "company_name": "分公司" if child else "宏源期货有限公司",
                "status": 1,
                "nature_cn": "校招" if name == "campus" else "实习",
                "recruitment_type_cn": "校园招聘",
                "contents": "岗位职责：\n研究业务\n任职资格：\n硕士应届毕业生",
                "education_cn": "硕士",
                "major_cn": "金融",
                "experience_cn": "应届生",
                "district_list": [{"area_cn": "上海"}],
                "end_time": "2026-10-25 23:59:59",
            }
            for name in names
        ]
        return {
            "code": 200,
            "data": {
                "page": 1,
                "page_size": 20,
                "total": len(rows) + (1 if self.mismatch else 0),
                "list": rows,
            },
        }


async def test_guopin_root_and_children_complete_and_interns_excluded(now: datetime) -> None:
    result = await swhy.Hongyuan(source("www.iguopin.com"), GuopinReplay(), now).collect()
    assert not result.coverage_issues() and len(result.jobs) == 1
    assert sum(s.skipped_out_of_scope for s in result.scopes) == 2
    assert result.jobs[0].deadline == "2026-10-25 23:59:59"
    assert not result.jobs[0].published
    result = await swhy.Hongyuan(source("www.iguopin.com"), GuopinReplay(True), now).collect()
    assert result.coverage_issues()


def test_incremental_keys_and_deadline_fingerprint_are_isolated(
    now: datetime, tmp_path: Path
) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}")
    replay = Replay()
    replay.last_evidence = str(evidence)
    store = Store(tmp_path / "state.sqlite")
    try:
        initial = IncrementalSource(store, "swhy", "all", now, now, IncrementalConfig())
        jobs = []
        for cls in (swhy.Securities, swhy.Swsmu):
            adapter = cls(source(cls.host), replay, now, incremental=initial)
            adapter.deadline = "2026-10-25 23:59:00"
            job = adapter.job(
                "same",
                title="岗位",
                source_url=adapter.source.url,
                deadline=adapter.deadline,
                published=now.isoformat(),
            )
            adapter.remember("job:same", {"id": "same"}, [job])
            jobs.append(job)
        initial.finish(
            Collection(
                jobs=jobs,
                scopes=[
                    Scope(name="all", expected=2, listed=2, unique=2, details=2, terminal=True)
                ],
            )
        )
        later = now + timedelta(hours=1)
        state = IncrementalSource(store, "swhy", "day", later, later, IncrementalConfig())
        adapter = swhy.Securities(source(), replay, later, incremental=state)
        adapter.deadline = "2026-10-25 23:59:00"
        scope = Scope(name="securities")
        cached = adapter.before_detail("job:same", {"id": "same"}, scope, jobs[0])
        assert cached is not None and cached[0].source_key == "securities:same"
        adapter.deadline = "2026-10-26 23:59:00"
        assert (
            adapter.before_detail("job:same", {"id": "same"}, Scope(name="changed"), jobs[0])
            is None
        )
    finally:
        store.close()
