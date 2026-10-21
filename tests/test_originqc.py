"""Origin Quantum campus category and rendered detail identity replay."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.originqc import OriginQCCampus
from job_crawler.models import Source


class Page:
    def __init__(self, session: "Session") -> None:
        self.session = session

    async def evaluate(self, script: str) -> dict[str, str]:
        assert "document.body.innerText" in script
        key = self.session.current.rsplit("=", 1)[-1]
        title = f"工程师{key}"
        if key == "11" and not self.session.mismatch:
            title = "工程师 (密码方向)"
        if self.session.mismatch and key == "11":
            title = "错配详情"
        return {
            "url": self.session.current,
            "text": f"首页\n{title}\n工作地点：安徽合肥\n岗位职责：\n研发{key}\n任职资格：\n本科\n投递简历",
        }


class Session:
    last_evidence = "list.json"

    def __init__(self, mismatch: bool = False) -> None:
        self.mismatch = mismatch
        self.current = ""
        self.pages: list[int] = []
        self.page = Page(self)

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.current = url
        self.last_evidence = url

    async def observed(self, needle: str) -> dict[str, Any]:
        return {
            "url": "https://originqc.com.cn/api/recruit/recruitList",
            "post_data": json.dumps(
                {"categoryId": 1, "positionId": "", "addressId": "", "pageNum": 1, "pageSize": 10}
            ),
        }

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        assert payload is not None and payload["categoryId"] == 1
        num = payload["pageNum"]
        self.pages.append(num)
        self.last_evidence = f"page-{num}.json"
        ids = range(1, 11) if num == 1 else range(11, 12)
        return {
            "success": True,
            "code": 1,
            "obj": {
                "pageNum": num,
                "totalRecords": 11,
                "totalPages": 2,
                "entityList": [
                    {
                        "id": key,
                        "positionname": ("工程师\n(密码方向)" if key == 11 else f"工程师{key}"),
                        "categoryName": "校园招聘",
                        "positionCategoryName": "研发",
                        "cityName": "安徽合肥",
                        "publishTime": 1788424663000,
                    }
                    for key in ids
                ],
            },
        }


def source() -> Source:
    return Source(
        source_id="COM0752",
        company_id="COM0752",
        company="本源量子",
        url="https://originqc.com.cn/zh/recruit?type=1",
    )


async def test_originqc_full_category_and_details(now: datetime) -> None:
    session = Session()
    result = await OriginQCCampus(source(), session, now).collect()
    assert not result.coverage_issues()
    assert session.pages == [1, 2]
    assert result.scopes[0].expected == result.scopes[0].unique == 11
    assert result.scopes[0].terminal
    assert len(result.jobs) == 11
    assert result.jobs[-1].duties == "研发11"
    assert result.jobs[-1].requirements == "本科"
    assert result.jobs[-1].published.startswith("2026-09-03")


async def test_originqc_rejects_detail_title_mismatch(now: datetime) -> None:
    result = await OriginQCCampus(source(), Session(mismatch=True), now).collect()
    assert len(result.jobs) == 10
    assert result.coverage_issues()
    assert "标题" in result.issues[0].message
