"""China Eastern Airlines' public campus list with legal-unit boundaries."""

import base64
import json
import re
from datetime import datetime
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urlencode
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.description import split_sections, strip_heading
from job_crawler.models import Scope

ROOT = "https://job.ceair.com"
ALLOWED_GROUPS = {"东航股份分公司", "业务运营单位"}
OTHER_GROUPS = {"东航股份子公司", "中国东航直属子企业"}
MIXED_IDS = {104, 110, 111}
DATE = re.compile(r"/Date\(([0-9]+)\)/")


class CeairSession(Protocol):
    last_evidence: str

    async def observed(self, needle: str) -> dict[str, Any]: ...

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None: ...

    async def request(
        self, url: str, *, form: dict[str, str], detail: bool = False
    ) -> dict[str, Any]: ...


def _date(value: object) -> str:
    check(isinstance(value, str), "东航公开日期字段缺失")
    assert isinstance(value, str)
    match = DATE.fullmatch(value)
    check(match is not None, "东航公开日期格式变化")
    assert match is not None
    return (
        datetime.fromtimestamp(int(match.group(1)) / 1000, ZoneInfo("Asia/Shanghai"))
        .date()
        .isoformat()
    )


def _detail_page(position_id: int) -> str:
    return (
        ROOT
        + "/JobDetail.html?"
        + urlencode(
            {
                "positionId": base64.b64encode(str(position_id).encode()).decode(),
                "cateId": base64.b64encode(b"4000").decode(),
            }
        )
    )


def _body(html: str) -> tuple[str, str]:
    body = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    check(bool(body), "东航岗位详情正文为空")
    if "【招聘条件】" in body:
        duties, requirements = body.split("【招聘条件】", 1)
        return strip_heading(duties.strip(), "duties"), requirements.strip()
    return split_sections(body)


def _education(requirements: str) -> str:
    for degree in ("大专", "本科", "硕士", "博士"):
        if re.search(rf"{degree}(?:研究生)?(?:学历)?(?:及以上|以上)", requirements):
            return degree
    return ""


class Ceair2027(Adapter):
    name = "ceair-2027"
    host = "job.ceair.com"
    path = "/campus/campusJobList.html"
    scope_description = "东航股份2027校园目录；仅分公司和本公司业务运营单位"
    ready_endpoints = ("/Ashx/Campus.ashx?active=GetPositionListByParams",)

    async def harvest(self) -> None:
        session = cast(CeairSession, self.session)
        scope = Scope(name="campus-2027")
        self.result.scopes.append(scope)
        observed = await session.observed("active=GetPositionListByParams")
        original = observed.get("post_data")
        check(isinstance(original, str), "东航初始目录请求缺失")
        assert isinstance(original, str)
        payload = parse_qs(original, keep_blank_values=True)
        check(
            payload
            == {
                "pageIndex": ["1"],
                "pageSize": ["6"],
                "positionName": [""],
                "workCity": [""],
                "cateId": [""],
                "deptId": [""],
                "banKuaiId": ["4000"],
            },
            "东航初始校园目录包含未知筛选或页码变化",
        )
        tree_observed = await session.observed("active=GetDeptList")
        tree = json.loads(tree_observed["body"])
        check(tree.get("msg") == "ok" and isinstance(tree.get("data"), list), "东航单位树失败")
        units: dict[int, tuple[str, str]] = {}
        for item in tree["data"]:
            department_key = item.get("PD_DEPTID")
            key = department_key if isinstance(department_key, int) else item.get("PD_PDID")
            name = item.get("PD_Name")
            group = item.get("PD_GroupName")
            check(
                isinstance(key, int)
                and isinstance(name, str)
                and isinstance(group, str)
                and key not in units,
                "东航单位树结构或 ID 变化",
            )
            units[key] = (name, group)
        tree_evidence = session.last_evidence
        check(any(group == "东航股份分公司" for _, group in units.values()), "东航分公司树缺失")
        check(any(group == "东航股份子公司" for _, group in units.values()), "东航子公司边界缺失")
        scope.evidence.append(tree_evidence)

        page = 1
        seen: set[int] = set()
        detail_api = ""
        while True:
            listing = await session.request(
                observed["url"],
                form={
                    "pageIndex": str(page),
                    "pageSize": "6",
                    "positionName": "",
                    "workCity": "",
                    "cateId": "",
                    "deptId": "",
                    "banKuaiId": "4000",
                },
            )
            rows = listing.get("data")
            total = listing.get("total")
            check(
                isinstance(rows, list) and isinstance(total, int) and total > 0, "东航目录响应异常"
            )
            assert isinstance(rows, list) and isinstance(total, int)
            if scope.expected is None:
                scope.expected = total
            check(
                total == scope.expected and len(rows) <= 6 and bool(rows),
                "东航分页总数变化或提前为空",
            )
            list_evidence = session.last_evidence
            scope.evidence.append(list_evidence)
            for row in rows:
                scope.listed += 1
                position_id = row.get("zp_ActiveInfoID")
                check(
                    isinstance(position_id, int) and position_id not in seen,
                    "东航岗位 ID 重复或缺失",
                )
                seen.add(position_id)
                scope.unique += 1
                department_id = row.get("News_DeptID")
                check(isinstance(department_id, int), "东航岗位单位 ID 缺失")
                if department_id in MIXED_IDS:
                    scope.skipped_out_of_scope += 1
                    continue
                check(department_id in units, "东航岗位出现未知单位")
                name, group = units[department_id]
                check(row.get("PD_Name") == name, "东航岗位单位与单位树不符")
                if group in OTHER_GROUPS:
                    scope.skipped_out_of_scope += 1
                    continue
                check(group in ALLOWED_GROUPS, "东航单位组归属不明确")
                check(
                    row.get("News_CategoryId") == 4000
                    and row.get("Active_Status") == 2
                    and "27年度秋招" in text(row.get("Active_Name")),
                    "东航本级岗位招聘类别、状态或年份变化",
                )
                try:
                    if not detail_api:
                        await session.open(
                            _detail_page(position_id),
                            ready_endpoints=(
                                "/Ashx/Campus.ashx?active=GetPositionDetailListByPosID",
                            ),
                        )
                        first = await session.observed("active=GetPositionDetailListByPosID")
                        detail_api = first["url"]
                        detail = json.loads(first["body"])
                        detail_evidence = session.last_evidence
                    else:
                        detail = await session.request(
                            detail_api, form={"positionId": str(position_id)}, detail=True
                        )
                        detail_evidence = session.last_evidence
                    item = detail.get("data")
                    check(
                        detail.get("msg") == "ok"
                        and isinstance(item, dict)
                        and item.get("zp_ActiveInfoID") == position_id
                        and item.get("PD_Name") == name
                        and item.get("Active_Name") == row.get("Active_Name")
                        and item.get("zp_NewsInfoID") == row.get("zp_NewsInfoID")
                        and item.get("News_CategoryId") == 4000,
                        "东航岗位详情身份与列表不符",
                    )
                    assert isinstance(item, dict)
                    html = item.get("Active_PosDesc")
                    check(isinstance(html, str), "东航岗位详情正文缺失")
                    assert isinstance(html, str)
                    duties, requirements = _body(html)
                    job = self.job(
                        str(position_id),
                        title=text(item["Active_Name"]),
                        unit=name,
                        batch="2027全球校园招聘",
                        category_raw=text(row.get("PC_Name")),
                        location=text(item.get("Active_WorkAddress")),
                        education=_education(requirements),
                        duties=duties,
                        requirements=requirements,
                        published=_date(item.get("News_CreateDate")),
                        deadline=_date(item.get("Active_EndTime")),
                        source_url=_detail_page(position_id),
                        field_sources={
                            "unit": "GetDeptList + GetPositionDetailListByPosID.PD_Name",
                            "duties": "GetPositionDetailListByPosID.Active_PosDesc 职位描述",
                            "requirements": "GetPositionDetailListByPosID.Active_PosDesc 招聘条件",
                            "published": "GetPositionDetailListByPosID.News_CreateDate 公告发布日期",
                            "deadline": "GetPositionDetailListByPosID.Active_EndTime",
                            "location": "GetPositionDetailListByPosID.Active_WorkAddress",
                        },
                    )
                    job.evidence = [list_evidence, tree_evidence, detail_evidence]
                    self.result.jobs.append(job)
                    scope.details += 1
                except Exception as exc:
                    self.error(exc, str(position_id))
            if scope.unique == total:
                scope.terminal = True
                break
            check(scope.unique < total and len(rows) == 6, "东航目录末页与总数不符")
            page += 1
