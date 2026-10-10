"""Synthetic contract tests. Live acceptance is recorded separately."""

import json
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.platforms import CCB, CNPC, Alibaba, Pingan
from job_crawler.models import Source
from job_crawler.transport import CrawlError


class Replay:
    last_evidence = "tests:synthetic-contract"

    def __init__(
        self,
        platform: str,
        *,
        empty: bool = False,
        repeat: bool = False,
        fail_detail: bool = False,
        changed_total: bool = False,
    ):
        self.platform = platform
        self.empty = empty
        self.repeat = repeat
        self.fail_detail = fail_detail
        self.changed_total = changed_total
        self.calls: list[tuple[str, dict[str, Any] | None, bool]] = []
        self.opened: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.opened.append(url)

    async def observed(self, needle: str) -> dict[str, Any]:
        if needle == "queryPositionPage":
            return {
                "url": "https://campus.pingan.com/api",
                "post_data": json.dumps({"positionType": "1", "PageNum": 1}),
            }
        if needle == "TXCODE=NHR104":
            return {"url": "https://job2.ccb.cn/api?TXCODE=NHR104&planType=XY"}
        if needle == "TXCODE=NHR107":
            return {"url": "https://job2.ccb.cn/api?TXCODE=NHR107"}
        if needle == "/recruitInfo/listN":
            return {"url": "https://zhaopin.cnpc.com.cn/recruitInfo/listN?max=1&type=1&offset=0"}
        if needle == "/recruitInfo/showN":
            return {"url": "https://zhaopin.cnpc.com.cn/recruitInfo/showN?recruitId=1"}
        if needle == "/searchCondition/listBatch?":
            return {
                "body": json.dumps(
                    {"content": {"graduate": [{"id": "campus"}, {"id": "new-batch"}]}}
                )
            }
        if "default.json" in needle:
            return {"body": json.dumps({"common": {"btnUrl": "/campus/position?alistar=true"}})}
        if needle == "/position/search?":
            return {
                "url": "https://campus-talent.alibaba.com/position/search?",
                "post_data": json.dumps(
                    {"batchId": "campus", "star": "alistar=true" in self.opened[-1]}
                ),
            }
        raise AssertionError(f"Unexpected observation: {needle}")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        self.calls.append((url, payload, detail))
        values = parse_qs(urlsplit(url).query)
        if self.platform == "pingan":
            assert payload is not None
            page = int(payload["PageNum"])
            return {
                "responseCode": "10001",
                "data": {
                    "totalCount": 0 if self.empty else 3 if self.changed_total and page == 2 else 2,
                    "totalPage": 0 if self.empty else 2,
                    "list": []
                    if self.empty
                    else [
                        {
                            "idPosition": "1" if self.repeat else str(page),
                            "positionName": "工程师",
                            "duty": "开发",
                            "qualification": "本科",
                        }
                    ],
                },
            }
        if self.platform == "ccb":
            if values.get("TXCODE") == ["NHR104"]:
                page = int(values["PAGE_JUMP"][0])
                return {
                    "SUCCESS": "true",
                    "TOTAL_REC": 0 if self.empty else 2,
                    "TOTAL_PAGE": 0 if self.empty else 2,
                    "planPostList": []
                    if self.empty
                    else [
                        {
                            "planId": "plan",
                            "planPost": "same-job",
                            "orgId": "parent",
                            "secondOrgId": f"unit-{page}",
                            "planType": "XY",
                            "planPostName": "岗位",
                        }
                    ],
                }
            assert detail
            unit = values["orgId"][0]
            if self.fail_detail and unit == "unit-2":
                raise CrawlError("http_error", "HTTP 503")
            assert unit in {"unit-1", "unit-2"}
            return {
                "SUCCESS": "true",
                "planPost": "same-job",
                "planPostName": unit,
                "orgName": unit,
                "endTime": "2026-10-08",
                "PostRequest": "岗位要求",
                "postDesc": "岗位职责",
            }
        if self.platform == "cnpc":
            if "listN" in url:
                return {
                    "totals": 0 if self.empty else 1,
                    "recruitInfo": [] if self.empty else [{"id": "notice"}],
                }
            return {
                "recruitInfoObj": {
                    "id": "notice",
                    "recruitTitle": "应届生",
                    "qualificationDemand": "公告统一条件",
                },
                "post": [
                    {"id": "A", "postToString": "岗位A", "remark": "要求A"},
                    {"id": "B", "postToString": "岗位B", "remark": "要求B"},
                ],
                "time1": "2026-10-01",
                "time2": "2026-10-31",
            }
        assert payload is not None
        if payload.get("star"):
            return {
                "success": True,
                "content": {
                    "totalCount": 1,
                    "pageSize": 100,
                    "datas": [{"id": "1", "name": "阿里星"}],
                },
            }
        page = int(payload["pageIndex"])
        return {
            "success": True,
            "content": {
                "totalCount": 2,
                "pageSize": 1,
                "datas": [
                    {
                        "id": str(page),
                        "name": f"工程师{page}",
                        "description": "开发",
                        "requirement": "本科",
                        "degree": None,
                        "publishTime": None,
                    }
                ],
            },
        }


def source(host: str) -> Source:
    return Source(source_id="TEST", company_id="CO", company="测试企业", url=f"https://{host}")


async def test_pingan_all_pages(now: datetime) -> None:
    session = Replay("pingan")
    result = await Pingan(source(Pingan.host), session, now).collect()
    assert len(result.jobs) == 2
    assert not result.coverage_issues()
    assert len(session.calls) == 2


async def test_repeated_page_keeps_partial_data(now: datetime) -> None:
    result = await Pingan(source(Pingan.host), Replay("pingan", repeat=True), now).collect()
    assert len(result.jobs) == 1
    assert result.issues[0].code == "duplicate_page"
    assert result.coverage_issues()


async def test_source_total_change_is_partial(now: datetime) -> None:
    result = await Pingan(source(Pingan.host), Replay("pingan", changed_total=True), now).collect()
    assert len(result.jobs) == 1 and result.issues[0].code == "source_changed"


async def test_verified_zero_never_requests_first_detail(now: datetime) -> None:
    for adapter in (CCB, CNPC, Pingan):
        session = Replay(adapter.name, empty=True)
        result = await adapter(source(adapter.host), session, now).collect()
        assert not result.jobs and not result.coverage_issues()
        assert len(session.opened) == 1


async def test_ccb_composite_identity_and_correlated_org(now: datetime) -> None:
    result = await CCB(source(CCB.host), Replay("ccb"), now).collect()
    assert [job.title for job in result.jobs] == ["unit-1", "unit-2"]
    assert len({job.key for job in result.jobs}) == 2
    assert not result.coverage_issues()


async def test_detail_failure_preserves_success_and_fails_coverage(now: datetime) -> None:
    result = await CCB(source(CCB.host), Replay("ccb", fail_detail=True), now).collect()
    assert len(result.jobs) == 1
    assert result.scopes[0].listed == 2 and result.scopes[0].details == 1
    assert result.coverage_issues()


async def test_ccb_skips_only_proven_expired_details(now: datetime) -> None:
    class ExpiredReplay(Replay):
        async def request(
            self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
        ) -> dict[str, Any]:
            response = await super().request(url, payload=payload, detail=detail)
            for row in response.get("planPostList", []):
                row["endDate"] = "2026-10-09"
            return response

    session = ExpiredReplay("ccb")
    result = await CCB(source(CCB.host), session, now).collect()
    assert not any(detail for _, _, detail in session.calls)
    assert result.scopes[0].skipped_expired == 2
    assert result.scopes[0].details == 0
    assert len(result.jobs) == 2 and not result.coverage_issues()
    assert all(job.deadline == "2026-10-09" for job in result.jobs)


async def test_cnpc_announcements_expand_into_distinct_jobs(now: datetime) -> None:
    result = await CNPC(source(CNPC.host), Replay("cnpc"), now).collect()
    assert len(result.jobs) == 2
    assert result.scopes[0].expected == 1 and result.scopes[0].unit == "招聘启事"
    assert result.jobs[0].requirements == "要求A\n公告统一条件"
    assert result.jobs[1].requirements == "要求B\n公告统一条件"
    assert not result.coverage_issues()


async def test_alibaba_all_batches_and_alistar_subset(now: datetime) -> None:
    result = await Alibaba(source(Alibaba.host), Replay("alibaba"), now).collect()
    assert len(result.jobs) == 4  # ID can recur across batches without being incorrectly dropped.
    assert len({job.key for job in result.jobs}) == 4
    assert result.jobs[0].published == ""  # modifyTime must not substitute for publishTime.
    assert len(result.scopes) == 4
    assert not result.coverage_issues()
