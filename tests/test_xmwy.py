"""Replay Xiamen Tungsten's parent-company and branch public SDK catalog."""

from datetime import datetime
from typing import Any

from job_crawler.adapters.xmwy import COMPANY, COMPANY_ID, TENANT, XiamenTungsten2027
from job_crawler.models import Source


class Page:
    def __init__(self, replay: "Replay") -> None:
        self.replay = replay

    async def content(self) -> str:
        return (
            '<div class="kind-list">'
            + "".join(
                f'<div class="item">{name}</div>'
                for name in (
                    "厦钨股份",
                    "钨钼产业",
                    "新能源产业",
                    "稀土产业",
                    "电机产业",
                    "矿业产业",
                )
            )
            + '</div><div class="company-list"><div class="clist">'
            + '<div class="iem" rel="01">总部</div><div class="iem" rel="05">海沧分公司</div>'
            + "</div></div>"
        )

    async def evaluate(self, script: str, arg: object = None) -> Any:
        if "getJobList" in script:
            assert arg in {"01", "05"}
            code = str(arg)
            rows = self.replay.rows[code]
            return {"status": "1", "resultbody": {"totalnum": str(len(rows)), "joblist": rows}}
        assert "getJobDetail" in script
        job_id = str(arg)
        row = next(r for rows in self.replay.rows.values() for r in rows if r["jobid"] == job_id)
        detail = {
            **row,
            "issuedate": row["issuedate"] + " 08:45:15",
            "jobinfo": "岗位职责：<br>负责设备运行<br><br>任职要求：<br>本科及以上学历",
        }
        if job_id == self.replay.bad_id:
            detail["poscode"] = "wrong"
        return {"status": "1", "resultbody": detail}


class Replay:
    last_evidence = "entry.json"

    def __init__(self) -> None:
        self.page = Page(self)
        self.bad_id: str | None = None
        self.rows: dict[str, list[dict[str, str]]] = {}
        for code, total in (("01", 4), ("05", 8)):
            rows = []
            for i in range(total):
                actual_code = code if i < total - 2 else ("1601" if i == total - 2 else "1701")
                rows.append(
                    {
                        "jobid": f"17{code}{i:04d}",
                        "jobname": f"岗位{code}-{i}",
                        "ctmid": TENANT,
                        "coid": COMPANY_ID,
                        "coname": COMPANY,
                        "poscode": actual_code,
                        "issuedate": "2026-10-13",
                        "term": "全职",
                        "workyearname": "在校生/应届生",
                        "funtype": "工程师",
                        "workareaname": "厦门",
                        "address": "福建省厦门市海沧区",
                        "degreefrom": "本科",
                    }
                )
            self.rows[code] = rows

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://campus.51job.com/cxtc2027/job.html"

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError(f"unexpected observed API: {needle}")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError(f"unexpected direct request: {url}")

    def snapshot(self, label: str, html: str) -> str:
        assert html
        self.last_evidence = label + ".json"
        return self.last_evidence


def source() -> Source:
    return Source(
        source_id="COM0334",
        company_id="COM0334",
        company=COMPANY,
        url="https://campus.51job.com/cxtc2027/job.html",
    )


async def test_xmwy_two_units_with_cross_unit_cards(now: datetime) -> None:
    replay = Replay()
    result = await XiamenTungsten2027(source(), replay, now).collect()
    assert result.coverage_issues() == []
    assert [(s.expected, s.details, s.skipped_out_of_scope) for s in result.scopes] == [
        (4, 2, 2),
        (8, 6, 2),
    ]
    assert len(result.jobs) == 8
    assert {j.unit for j in result.jobs} == {"总部", "海沧分公司"}
    assert all(j.duties and j.requirements and j.published == "2026-10-13" for j in result.jobs)


async def test_xmwy_identity_failure_keeps_others(now: datetime) -> None:
    replay = Replay()
    replay.bad_id = replay.rows["05"][0]["jobid"]
    result = await XiamenTungsten2027(source(), replay, now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 7


async def test_xmwy_rejects_duplicate_job_id(now: datetime) -> None:
    replay = Replay()
    replay.rows["05"][1]["jobid"] = replay.rows["01"][0]["jobid"]
    result = await XiamenTungsten2027(source(), replay, now).collect()
    assert result.coverage_issues()
