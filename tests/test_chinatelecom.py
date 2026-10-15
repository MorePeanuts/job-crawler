"""中国电信集团单位树、分页和详情身份回放。"""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.chinatelecom import DETAIL, LIST, TREE, ChinaTelecomCampus
from job_crawler.models import Source


class Replay:
    last_evidence = "telecom-evidence.json"

    def __init__(self, *, mismatch: bool = False):
        self.mismatch = mismatch
        self.pages: list[tuple[str, int]] = []
        self.details: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://job.chinatelecom.com.cn/wt/TELE/web/index?brandCode=1"
        assert ready_endpoints == (TREE,)

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle == "/getShowRecruitOrg?"
        return {
            "url": TREE,
            "body": json.dumps(
                {
                    "code": "00",
                    "data": [
                        {"uniqueKey": 581617, "cnExternalName": "中国电信北京公司"},
                        {"uniqueKey": 581635, "cnExternalName": "中国电信上海公司"},
                    ],
                }
            ),
        }

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
        detail: bool = False,
    ) -> dict[str, Any]:
        assert payload is None and form is not None
        assert form.get("recruitType") == "1"
        if url == LIST:
            assert not detail
            root = form["org"]
            page = int(form["rowIndex"])
            assert form["rowSize"] == "50" and not form["postName"]
            self.pages.append((root, page))
            total = 51 if root == "581617" else 1
            first = (page - 1) * 50
            return {
                "code": "00",
                "data": {
                    "rowCount": total,
                    "details": [
                        {
                            "PostId": (1000 if root == "581617" else 2000) + index,
                            "PostName": f"校招岗位{root}-{index}",
                            "WorkPlace": "北京" if root == "581617" else "上海",
                            "PostType": "研发",
                            "RecruitType": 1,
                            "ReleaseTime": "2026-09-04",
                        }
                        for index in range(first, min(first + 50, total))
                    ],
                },
            }
        assert url == DETAIL and detail
        post_id = int(form["postId"])
        self.details.append(post_id)
        root = "581617" if post_id < 2000 else "581635"
        index = post_id - (1000 if root == "581617" else 2000)
        return {
            "code": "00",
            "data": {
                "name": "错配岗位"
                if self.mismatch and post_id == 1050
                else f"校招岗位{root}-{index}",
                "orgCode": f"0/{root}/999",
                "SecondOrgName": "中国电信北京公司" if root == "581617" else "中国电信上海公司",
                "OrgName": "省本部",
                "quickRecruitType": None if post_id == 1000 else 21,
                "ReleaseTime": "2026-09-04",
                "workPlace": "北京市" if root == "581617" else "上海市",
                "EducationName": "本科及以上",
                "Subject": "计算机类",
                "PostType": "研发",
                "projectName": "2027年度校园招聘",
                "workConcet": "负责研发",
                "serviceCondition": "本科及以上",
            },
        }


def source() -> Source:
    return Source(
        source_id="COM0038",
        company_id="COM0038",
        company="中国电信集团有限公司",
        url="https://job.chinatelecom.com.cn/wt/TELE/web/index?brandCode=1",
    )


async def test_telecom_all_units_pages_and_details(now: datetime) -> None:
    replay = Replay()
    result = await ChinaTelecomCampus(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert replay.pages == [("581617", 1), ("581617", 2), ("581635", 1)]
    assert len(replay.details) == len(result.jobs) == 52
    assert [scope.expected for scope in result.scopes] == [51, 1]
    assert all(scope.terminal for scope in result.scopes)
    assert result.jobs[-1].unit == "中国电信上海公司 / 省本部"
    assert "招聘专业：计算机类" in result.jobs[-1].requirements


async def test_telecom_detail_mismatch_keeps_other_unit(now: datetime) -> None:
    result = await ChinaTelecomCampus(source(), Replay(mismatch=True), now).collect()
    assert result.coverage_issues()
    assert result.scopes[0].terminal is False
    assert result.scopes[1].terminal is True
    assert len(result.jobs) == 51
