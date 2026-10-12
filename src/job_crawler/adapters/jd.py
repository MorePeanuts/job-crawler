"""JD's public graduate catalog with project and page-count verification."""

import json
from typing import Any

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


def graduate_plans(payload: dict[str, Any]) -> dict[int, str]:
    check(payload.get("success") is True, "京东项目树业务失败")
    result: dict[int, str] = {}
    for category in payload["body"]["projectList"]:
        if category.get("code") != "present":
            continue
        for group in category.get("groupList", []):
            for plan in group.get("planMapList", []):
                result[int(plan["id"])] = text(plan["planName"])
    check(bool(result), "京东应届生项目树为空")
    return result


class JD(Adapter):
    name = "jd-campus"
    host = "campus.jd.com"
    path = "/#/jobs"
    ready_endpoints = ("/api/wx/position/page?type=present",)
    scope_description = "京东公开应届生 present 项目全目录；TGT 专项和实习不在范围内"

    async def harvest(self) -> None:
        observed = await self.session.observed("/api/wx/position/page?type=present")
        check(
            observed["url"].endswith("/api/wx/position/page?type=present"), "京东岗位接口类型改变"
        )
        payload = json.loads(observed["post_data"])
        check(payload.get("pageIndex") == 0, "京东目录不是第一页")
        check(
            set(payload) == {"pageIndex", "pageSize", "parameter"},
            "京东岗位查询出现未知顶层筛选",
        )
        params = payload["parameter"]
        check(
            set(params)
            == {
                "positionName",
                "planIdList",
                "jobDirectionCodeList",
                "workCityCodeList",
                "positionDeptList",
            }
            and not any(params.values()),
            "京东岗位目录仍有筛选",
        )
        size = int(payload["pageSize"])
        check(0 < size <= 100, "京东分页大小无效")
        tree = await self.session.observed("/api/wx/position/getProjectList")
        plans = graduate_plans(json.loads(tree["body"]))
        tree_evidence = self.session.last_evidence
        scope = Scope(name="graduate-present")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 0
        while True:
            data = await self.session.request(
                observed["url"], payload={**payload, "pageIndex": page}
            )
            check(data.get("success") is True, "京东岗位列表业务失败")
            body = data["body"]
            expected = int(body["totalNumber"])
            pages = (expected + size - 1) // size
            check(expected >= 0 and int(body["pageCount"]) in {0, pages}, "京东总数或页数无效")
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "京东翻页期间总数变化")
            rows = self.add_page(scope, body["items"], seen, lambda row: str(row["publishId"]))
            evidence = self.session.last_evidence
            for row in rows:
                plan_id = int(row["planId"])
                check(plan_id in plans, "京东应届生目录混入其他招聘项目")
                key = str(row["publishId"])
                title = text(row.get("positionName"))
                duties = text(row.get("workContent"))
                check(bool(title) and bool(duties), "京东岗位标题或职责缺失")
                requirements = text(row.get("qualification"))
                locations = [
                    text(item.get("workCity"))
                    for item in row.get("requirementVoList") or []
                    if item.get("workCity")
                ]
                location = "、".join(dict.fromkeys(locations))
                detail_url = f"https://{self.host}/#/details?id={key}"
                job = self.job(
                    key,
                    title=title,
                    source_url=detail_url,
                    apply_url=detail_url,
                    unit=text(row.get("positionDept")),
                    batch=plans[plan_id],
                    category_raw=text(row.get("jobCategory") or row.get("jobDirection")),
                    location=location,
                    education=text(row.get("education")),
                    duties=duties,
                    requirements=requirements,
                    published=text(row.get("publishTime")),
                    field_sources={
                        "batch": "getProjectList.present.planMapList[].planName",
                        "location": "position/page.body.items[].requirementVoList[].workCity",
                        "duties": "position/page.body.items[].workContent",
                        "requirements": "position/page.body.items[].qualification",
                        "published": "position/page.body.items[].publishTime",
                        "deadline": "source_missing",
                    },
                )
                job.evidence = [evidence, tree_evidence]
                resolved = self.before_detail(f"job:{key}", row, scope, job, evidence=evidence)
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", row, [job])
            if page + 1 >= pages:
                check(scope.unique == expected, "京东岗位唯一数与总数不符")
                scope.terminal = True
                break
            check(bool(rows), "京东分页提前为空")
            page += 1
