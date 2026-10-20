"""中国煤科国聘校招目录中的天地科技国际分公司。"""

import json
import re
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.moka import sections
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

ROOT_ID = "10685382754151861"
PARENT_ID = "135435436473453420"
UNIT_ID = "10685391416427355"
UNIT = "天地科技股份有限公司国际分公司"
NATURE = ["115xW5oQ", "114Fay7E"]


def tenant(info: dict[str, Any]) -> None:
    data = info.get("data") or {}
    check(
        info.get("code") == 200
        and data.get("key") == "cctegjob"
        and str(data.get("company_id")) == ROOT_ID
        and (data.get("company") or {}).get("name") == "中国煤炭科工集团有限公司",
        "天地科技国聘租户身份改变",
    )


def unit_node(tree: dict[str, Any]) -> dict[str, Any]:
    check(tree.get("code") == 200, "天地科技机构树业务失败")
    data = tree.get("data") or {}
    root = data.get("organization_tree") or {}
    check(
        str(root.get("company_id")) == ROOT_ID and root.get("name") == "中国煤炭科工集团有限公司",
        "天地科技机构树根改变",
    )
    nodes = root.get("children") or []
    parent = next((node for node in nodes if str(node.get("company_id")) == PARENT_ID), None)
    unit = next((node for node in nodes if str(node.get("company_id")) == UNIT_ID), None)
    check(
        parent is not None and parent.get("name") == "天地科技股份有限公司",
        "天地科技上市主体机构缺失",
    )
    check(
        unit is not None
        and unit.get("name") == UNIT
        and int(unit.get("all_job_count", -1)) == 2
        and int(unit.get("job_count", -1)) == 2,
        "天地科技国际分公司岗位数或主体改变",
    )
    assert unit is not None
    return cast(dict[str, Any], unit)


def jobs(response: dict[str, Any], expected: int) -> list[dict[str, Any]]:
    check(response.get("code") == 200, "天地科技岗位列表业务失败")
    data = response.get("data") or {}
    rows = data.get("list")
    check(
        isinstance(rows, list)
        and int(data.get("total", -1)) == expected
        and int(data.get("page", -1)) == 1
        and int(data.get("page_size", -1)) == 20
        and len(rows) == expected,
        "天地科技岗位列表与机构树计数不一致",
    )
    assert isinstance(rows, list)
    ids: set[str] = set()
    departments: set[str] = set()
    for row in rows:
        check(isinstance(row, dict), "天地科技岗位列表行结构改变")
        key = str(row.get("job_id", ""))
        department = text(row.get("department_cn"))
        check(
            key.isdigit()
            and key not in ids
            and bool(department)
            and department not in departments
            and str(row.get("company_id")) == UNIT_ID
            and row.get("company_name") == UNIT
            and row.get("job_name") == "项目助理"
            and row.get("recruitment_type_cn") == "校园招聘"
            and row.get("nature_cn") == "校招"
            and row.get("status") == 1
            and bool(text(row.get("contents"))),
            "天地科技岗位身份、届别或内容改变",
        )
        ids.add(key)
        departments.add(department)
    check(departments == {"技术产业部", "国际合作中心"}, "天地科技两个项目助理部门改变")
    return cast(list[dict[str, Any]], rows)


def split_contents(body: str) -> tuple[str, str]:
    normalized = re.sub(r"【职责描述】", "【岗位职责】", body)
    normalized = re.sub(r"【职责要求】", "【任职要求】", normalized)
    duties, requirements = sections(normalized)
    check(bool(duties) and bool(requirements), "天地科技岗位职责或要求缺失")
    return duties, requirements


class TiandiInternational2027(Adapter):
    name = "tiandi-international-iguopin-2027"
    host = "cctegjob.iguopin.com"
    path = "/campus"
    ready_endpoints = ("https://gp-api.iguopin.com/api/jobs/v1/list",)
    scope_description = "中国煤科国聘 2027 校园目录中天地科技国际分公司全部两岗"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        info_raw = await session.observed_path("/api/activity/exclusive/v1/info")
        check(
            parse_qs(urlsplit(info_raw["url"]).query) == {"domain": ["cctegjob"]},
            "天地科技租户查询参数改变",
        )
        tenant(json.loads(info_raw["body"]))
        info_evidence = session.last_evidence
        tree_raw = await session.observed_path("/api/company/organization/v1/tree")
        query = parse_qs(urlsplit(tree_raw["url"]).query)
        check(
            query
            == {
                "company_id": [ROOT_ID],
                "with_job_count": ["1"],
                "show_all_company": ["1"],
                "nature": [",".join(NATURE)],
            },
            "天地科技机构树筛选改变",
        )
        unit = unit_node(json.loads(tree_raw["body"]))
        tree_evidence = session.last_evidence
        initial = await session.observed_path("/api/jobs/v1/list")
        check(
            json.loads(initial.get("post_data") or "null")
            == {
                "page": 1,
                "page_size": 20,
                "source": "s_job_list",
                "nature": NATURE,
                "company_id_with_sub": ROOT_ID,
                "sort_scene": 1,
            },
            "天地科技官方校园页初始目录筛选改变",
        )
        payload = {
            "page": 1,
            "page_size": 20,
            "source": "s_job_list",
            "nature": NATURE,
            "company_id": [UNIT_ID],
            "sort_scene": 1,
        }
        response = await session.request(initial["url"], payload=payload, credentials="omit")
        rows = jobs(response, int(unit["all_job_count"]))
        list_evidence = session.last_evidence
        scope = Scope(name="ccteg-international-campus", expected=len(rows))
        scope.evidence.extend((info_evidence, tree_evidence, list_evidence))
        self.result.scopes.append(scope)
        for row in self.add_page(scope, rows, set(), lambda item: str(item["job_id"])):
            try:
                body = text(row["contents"])
                duties, requirements = split_contents(body)
                places = row.get("district_list")
                check(isinstance(places, list) and len(places) == 1, "天地科技岗位地点结构改变")
                assert isinstance(places, list)
                location = text(places[0].get("area_cn"))
                check(bool(location), "天地科技岗位地点缺失")
                job = self.job(
                    str(row["job_id"]),
                    title=text(row["job_name"]),
                    work_type="校招",
                    source_url=f"https://www.iguopin.com/job/detail?id={row['job_id']}",
                    unit=f"{UNIT} / {text(row['department_cn'])}",
                    location=location,
                    education=text(row.get("education_cn")),
                    requirements=requirements,
                    duties=duties,
                    deadline=text(row.get("end_time")),
                    field_sources={
                        "unit": "国聘官方机构树及岗位 company_id、部门",
                        "title": "国聘岗位列表 job_id、job_name",
                        "location": "国聘岗位 district_list.area_cn",
                        "education": "国聘岗位 education_cn",
                        "duties": "国聘岗位 contents 职责章节",
                        "requirements": "国聘岗位 contents 要求章节",
                        "deadline": "国聘岗位 end_time",
                        "published": "source_missing:start_time 为招聘开始而非岗位发布时间",
                    },
                )
                job.evidence = [info_evidence, tree_evidence, list_evidence]
                self.result.jobs.append(job)
                scope.details += 1
            except Exception as exc:
                self.error(exc, str(row["job_id"]))
        scope.terminal = True
