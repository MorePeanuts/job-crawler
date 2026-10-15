import json
from datetime import datetime
from pathlib import Path
from typing import Any

from job_crawler.adapters.cib import Cib2027
from job_crawler.config import CrawlConfig
from job_crawler.models import Source


class Page:
    def __init__(self, session: "Session"):
        self.session = session
        self.action = ""

    def locator(self, selector: str) -> "Page":
        self.action = selector
        return self

    def get_by_text(self, label: str, *, exact: bool) -> "Page":
        assert exact
        self.action = "size" if label == "40 条/页" else label
        return self

    async def click(self) -> None:
        if self.action == "size":
            self.session.add_page(1)
        elif self.action == ".ant-pagination-next":
            raise AssertionError("fixtures contain one page per institution")
        elif self.action == "总行(40)":
            self.session.add_page(1, "B0000")
        elif self.action == "兴业国际信托有限公司(1)":
            self.session.add_page(1, "C1000")
        else:
            assert self.action == ".ant-pagination-options-size-changer"


class Session:
    last_evidence = "fixture"

    def __init__(self, output: Path, *, wrong_count: bool = False):
        self.output = output
        self.page = Page(self)
        self.config = CrawlConfig(delay=0)
        self.pending: set[Any] = set()
        self.responses: list[dict[str, Any]] = []
        self.wrong_count = wrong_count

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url.endswith("recruitType=CR")

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError(f"unexpected observation: {needle}")

    async def observed_path(self, path: str) -> dict[str, Any]:
        assert path.endswith("queryOrgPositionNum")
        return {
            "post_data": json.dumps({"recruitType": "CR"}),
            "body": json.dumps(
                {
                    "code": "0000",
                    "data": [
                        {"businessUnit": "B0000", "businessUnitDesc": "总行", "positionCount": 40},
                        {
                            "businessUnit": "C1000",
                            "businessUnitDesc": "兴业国际信托有限公司",
                            "positionCount": 2 if self.wrong_count else 1,
                        },
                        {
                            "businessUnit": "C2000",
                            "businessUnitDesc": "兴业金融租赁有限责任公司",
                            "positionCount": 0,
                        },
                        {
                            "businessUnit": "C3000",
                            "businessUnitDesc": "兴业消费金融股份公司",
                            "positionCount": 0,
                        },
                        {
                            "businessUnit": "C4000",
                            "businessUnitDesc": "兴银理财有限责任公司",
                            "positionCount": 0,
                        },
                    ],
                }
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError(f"unexpected request: {url}")

    def consume_request(self) -> None:
        pass

    def add_page(self, page: int, root_code: str | None = None) -> None:
        start = 41 if root_code == "C1000" else 1
        stop = 42 if root_code == "C1000" else 41
        rows = []
        for number in range(start, stop):
            subsidiary = number == 41
            rows.append(
                {
                    "positionId": str(number),
                    "positionName": f"岗位{number}",
                    "businessUnit": "C1000" if subsidiary else "B0000",
                    "businessUnitDesc": "兴业国际信托有限公司" if subsidiary else "总行",
                    "firstBusinessUnit": "C1000" if subsidiary else "B0000",
                    "firstBusinessUnitDesc": "兴业国际信托有限公司" if subsidiary else "总行",
                    "recruitType": "CR",
                    "visibilityFlag": "Y",
                    "positionStatus": "P",
                    "positionType": "G",
                    "positionAddr": "福州",
                    "jobDuty": "处理银行业务",
                    "positionRequirment": "本科及以上学历",
                    "publishTime": "2026-10-01 00:00:00",
                    "expiryDate": "2026-11-01 00:00:00",
                }
            )
        self.responses.append(
            {
                "url": "https://job.cib.com.cn/ersApi/recruitposition/portalPage?_timestamp=x",
                "post_data": json.dumps(
                    {
                        "recruitType": "CR",
                        "visibilityFlag": "Y",
                        "positionStatus": "P",
                        **({"firstBusinessUnit": root_code} if root_code else {}),
                        "pagination": {"pageIndex": page, "pageSize": 40},
                    }
                ),
                "body": json.dumps(
                    {
                        "code": "0000",
                        "data": {
                            "total": 1 if root_code == "C1000" else 40 if root_code else 41,
                            "list": rows,
                        },
                    }
                ),
            }
        )


def source() -> Source:
    return Source(
        source_id="COM0071",
        company_id="COM0071",
        company="兴业银行股份有限公司",
        url="https://job.cib.com.cn/portal/#/recruit/814456498578608128?recruitType=CR",
    )


async def test_cib_2027_all_bank_branches_and_subsidiary_exclusion(
    tmp_path: Path, now: datetime
) -> None:
    result = await Cib2027(source(), Session(tmp_path), now).collect()
    assert not result.coverage_issues()
    assert sum(scope.expected or 0 for scope in result.scopes) == 41
    assert result.scopes[0].expected == result.scopes[0].listed == result.scopes[0].unique == 40
    assert result.scopes[0].details == len(result.jobs) == 40
    assert result.scopes[1].skipped_out_of_scope == 1
    assert all(job.unit == "总行" for job in result.jobs)
    assert result.jobs[0].published == "2026-10-01 00:00:00"


async def test_cib_2027_org_count_drift_blocks_coverage(tmp_path: Path, now: datetime) -> None:
    result = await Cib2027(source(), Session(tmp_path, wrong_count=True), now).collect()
    assert result.coverage_issues()
    assert not result.scopes
