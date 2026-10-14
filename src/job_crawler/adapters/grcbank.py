"""Guangzhou Rural Commercial Bank's published campus category catalog."""

import json
from typing import Any, Protocol, cast

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

COMPANY = "广州农村商业银行股份有限公司"
CATEGORY_API = "/api/zp/user/getPostSchoolCategory"
PAGE_API = "/api/zp/user/getPageSchool"
CATEGORY_TYPE = "BD241031112855lxqk9m"
EXCLUDED = "博士后研究人员"


class BankSession(Protocol):
    last_evidence: str

    async def observed(self, needle: str) -> dict[str, Any]: ...


def _response(observed: dict[str, Any], label: str) -> dict[str, Any]:
    try:
        result = json.loads(observed["body"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError(f"广州农商银行{label}响应不是 JSON") from exc
    check(
        isinstance(result, dict)
        and result.get("statusCode") == "2000"
        and result.get("status") == "success",
        f"广州农商银行{label}接口失败",
    )
    assert isinstance(result, dict)
    return result


class GuangzhouRuralBankCampus(Adapter):
    name = "grcbank-campus"
    host = "cdms.grcbank.com"
    path = ":8083/yp/school"
    scope_description = "广州农商银行公开校招岗位类别；排除博士后及其他公司导航"
    ready_endpoints = (PAGE_API, CATEGORY_API)

    async def harvest(self) -> None:
        session = cast(BankSession, self.session)
        page_observed = await session.observed(PAGE_API)
        page = _response(page_observed, "页面")
        page_data = page.get("data")
        check(
            isinstance(page_data, dict)
            and page_data.get("state") == 1
            and page_data.get("stateName") == "已发布",
            "广州农商银行校招页面未发布",
        )
        page_evidence = session.last_evidence
        category_observed = await session.observed(CATEGORY_API)
        try:
            payload = json.loads(category_observed["post_data"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("广州农商银行校招目录请求参数缺失") from exc
        check(
            payload == {"params": {"type": CATEGORY_TYPE}, "source": 0},
            "广州农商银行校招目录请求条件变化",
        )
        response = _response(category_observed, "岗位类别")
        rows = response.get("data")
        check(isinstance(rows, list) and bool(rows), "广州农商银行校招岗位类别为空")
        assert isinstance(rows, list)
        scope = Scope(name="published-campus-categories", expected=len(rows))
        scope.evidence.extend([page_evidence, session.last_evidence])
        self.result.scopes.append(scope)
        seen: set[str] = set()
        for row in rows:
            check(isinstance(row, dict), "广州农商银行校招岗位卡片结构变化")
            assert isinstance(row, dict)
            job_id = row.get("id")
            check(
                isinstance(job_id, str)
                and bool(job_id)
                and job_id not in seen
                and row.get("pkPostCategory") == job_id
                and row.get("type") == 1
                and row.get("children") == [],
                "广州农商银行校招岗位 ID 重复或层级变化",
            )
            seen.add(job_id)
            scope.listed += 1
            scope.unique += 1
            title = text(row.get("title"))
            check(bool(title) and title == text(row.get("name")), "广州农商银行岗位标题缺失")
            if title == EXCLUDED:
                scope.skipped_out_of_scope += 1
                continue
            duties = text(row.get("duty"))
            requirements = text(row.get("qualification"))
            check(bool(duties and requirements), "广州农商银行岗位职责或资格缺失")
            job = self.job(
                job_id,
                title=title,
                unit=COMPANY,
                batch="校园招聘",
                duties=duties,
                requirements=requirements,
                source_url=self.source.url,
                field_sources={
                    "unit": "广州农村商业银行官方招聘页本行校园招聘栏目",
                    "title": "getPostSchoolCategory.title / name",
                    "duties": "getPostSchoolCategory.duty",
                    "requirements": "getPostSchoolCategory.qualification",
                    "location": "岗位类别未提供地点，保留空值",
                    "published": "岗位类别未提供发布日期，保留空值",
                    "deadline": "岗位类别未提供截止日，保留空值",
                },
            )
            job.evidence = list(scope.evidence)
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
