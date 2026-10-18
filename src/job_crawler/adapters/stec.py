"""STEC's public campus unit tree and inline job bodies."""

import json
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

ROOT = "https://zhaopin.stec.net"
PORTAL = "33063664-e982-4f2f-8621-63ad81a31700"
TREE = f"{ROOT}/api/OpenCustomization/GetJobAdCustomTypeList?portalId={PORTAL}"
CATALOG = f"{ROOT}/api/JobAd/GetJobAdPageList?portalId={PORTAL}"
CATEGORIES = {
    "城市建设类",
    "城市设计类",
    "金融投资类",
    "能源与环境类",
    "智能数字化类",
    "城市运营类",
    "其它类",
    "集团总部",
}
DISPLAY = [
    "Category",
    "Kind",
    "LocId",
    "PostDate",
    "WorkWeChatQrCode",
    "HeadCount",
    "Salary",
    "Org",
    "ClassificationTwo",
]


def public_units(response: dict[str, Any]) -> list[tuple[int, str]]:
    check(response.get("Code") == 200, "隧道单位目录业务失败")
    tree = response["Data"]["Type"]
    check(tree.get("TypeCode") == 2, "隧道单位分类类型变化")
    groups = tree["Items"]
    check(isinstance(groups, list) and len(groups) == len(CATEGORIES), "隧道分类缺失或新增")
    check({g["Text"] for g in groups} == CATEGORIES, "隧道公开分类变化")
    units: list[tuple[int, str]] = []
    seen: set[int] = set()
    for group in groups:
        check(bool(group["Items"]), "隧道分类没有公开单位，不是零岗位")
        for unit in group["Items"]:
            value, name = unit["Value"], text(unit["Text"])
            check(
                isinstance(value, int) and value > 0 and value not in seen and bool(name),
                "隧道单位身份为空或重复",
            )
            for child in unit["Items"]:
                check(
                    "内招专用" in child["Text"] or "内部招聘" in child["Text"],
                    "隧道出现新的公开三级范围，需核对",
                )
            seen.add(value)
            units.append((value, name))
    return units


def recruitment_type(row: dict[str, Any]) -> str:
    title, requirements = text(row["JobAdName"]), text(row["Require"])
    check(row.get("Kind") in {"全职", "实习"}, "隧道岗位工作性质未知")
    if row["Kind"] == "实习" or "实习生" in title:
        return "实习"
    if "社招" in title and not re.search("校招|应届", title):
        return "社招"
    if not re.search("应届|校招", title + requirements):
        for line in re.split(r"[\n；;。]", requirements):
            if "优先" not in line and re.search(r"\d+\s*年(?:及)?以上[^\n；;。]{0,70}经验", line):
                return "社招"
    return "校招"


def checked_date(row: dict[str, Any], field: str, millis: str) -> str:
    value = text(row.get(field))
    stamp = row.get(millis)
    if field == "EndTime" and value.startswith("0001-01-01"):
        check(stamp == 0, "隧道未知截止哨兵冲突")
        return ""
    check(bool(value) and isinstance(stamp, int) and stamp > 0, "隧道业务日期缺失")
    if not isinstance(stamp, int):
        raise ValueError("隧道日期时间戳类型变化")
    parsed = datetime.fromisoformat(value).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    check(abs(parsed.timestamp() * 1000 - stamp) < 1000, "隧道日期与源时间戳冲突")
    return value


class StecCampus(Adapter):
    name = "stec-campus"
    host = "zhaopin.stec.net"
    path = "/"
    ready_endpoints = ("/api/OpenCustomization/GetJobAdCustomTypeList",)
    scope_description = "隧道股份校园八类全部公开二级单位；排除内招、实习及明确社招"

    async def harvest(self) -> None:
        observed = await self.session.observed(self.ready_endpoints[0])
        check(
            observed["url"] == TREE and json.loads(observed["post_data"]) == {"TypeCode": 2},
            "隧道单位入口/分类请求变化",
        )
        tree = await self.session.request(TREE, payload={"TypeCode": 2})
        units = public_units(tree)
        tree_evidence = self.session.last_evidence
        all_ids: set[str] = set()
        all_numbers: set[int] = set()
        for value, unit in units:
            scope = Scope(name=f"stec-unit-{value}:{unit}", evidence=[tree_evidence])
            self.result.scopes.append(scope)
            try:
                response = await self.session.request(
                    CATALOG,
                    payload={
                        "PageIndex": 0,
                        "PageSize": 1000,
                        "ClassificationOne": [],
                        "Category": ["2"],
                        "KeyWords": "",
                        "SpecialType": 0,
                        "PortalId": "",
                        "DisplayFields": DISPLAY,
                        "LocId": [],
                        "ClassificationTwo": [value],
                    },
                )
                check(response.get("Code") == 200, "隧道单位岗位业务失败")
                count, rows = response.get("Count"), response.get("Data")
                check(
                    isinstance(count, int) and 0 <= count <= 1000,
                    "隧道单位总数无效或超过已验证上限",
                )
                scope.expected = count
                check(isinstance(rows, list) and len(rows) == count, "隧道单位目录不完整")
                if not isinstance(rows, list):
                    raise ValueError("隧道岗位目录不是数组")
                fresh = self.add_page(scope, rows, set(), lambda r: str(r["Id"]))
                for row in fresh:
                    key, number = text(row["Id"]), row["JobAdId"]
                    check(
                        key not in all_ids
                        and isinstance(number, int)
                        and number > 0
                        and number not in all_numbers,
                        "隧道跨单位岗位重复或ID无效",
                    )
                    check(
                        str(row["CategoryId"]) == "2" and row["Status"] == 1,
                        "隧道岗位类别或展示状态变化",
                    )
                    check(row["ClassificationTwo"] == unit, "隧道岗位与单位目录错配")
                    check(
                        bool(text(row["JobAdName"]))
                        and bool(text(row["Duty"]))
                        and bool(text(row["Require"])),
                        "隧道完整岗位正文缺失",
                    )
                    for field in ("Duty", "Require"):
                        check(
                            not BeautifulSoup(row[field], "html.parser").find(
                                ["a", "img", "iframe", "object", "video"]
                            ),
                            "隧道正文含未展开附件或媒体",
                        )
                    job = self.job(
                        key,
                        title=text(row["JobAdName"]),
                        unit=unit,
                        source_url=ROOT + "/",
                        work_type=recruitment_type(row),
                        location=text(row.get("LocNames")),
                        address=text(row.get("DetailAddress")),
                        education=text(row.get("Degree")),
                        duties=text(row["Duty"]),
                        requirements=text(row["Require"]),
                        published=checked_date(row, "PostDate", "PostDateInt"),
                        deadline=checked_date(row, "EndTime", "EndTimeInt"),
                        field_sources={
                            "duties": "GetJobAdPageList.Duty",
                            "requirements": "GetJobAdPageList.Require",
                            "published": "PostDate/PostDateInt一致",
                            "deadline": "EndTime；0001/0为未知",
                            "work_type": "校园Category2、Kind、标题及资格排除明确社招",
                        },
                    )
                    all_ids.add(key)
                    all_numbers.add(number)
                    self.result.jobs.append(job)
                    scope.details += 1
                scope.terminal = True
            except Exception as exc:
                self.error(exc, f"unit:{value}")
