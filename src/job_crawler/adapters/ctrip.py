"""Trip.com Group's official, unfiltered graduate position catalog."""

import json
import re

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.description import split_sections
from job_crawler.models import Scope


def split_ctrip_body(html: str) -> tuple[str, str]:
    body = text(html)
    duties, requirements = split_sections(body)
    if requirements:
        return duties, requirements
    start = re.search(r"你将会负责\s*[:：]?", body)
    end = re.search(r"我们期望你\s*[:：]?", body)
    if start and end and start.end() < end.start():
        preamble = body[: start.start()].strip()
        return body[start.end() : end.start()].strip(), "\n".join(
            part for part in (preamble, body[end.end() :].strip()) if part
        )
    return duties, requirements


class CtripCampus(Adapter):
    name = "ctrip-2027-campus"
    host = "careers.ctrip.com"
    path = "/#/campus/jobList?kind=1"
    endpoint = "/api/hrrecruit/getJobAd"
    ready_endpoints = (endpoint,)
    scope_description = "携程集团2027届应届校招生 category=2、kind=1 无筛选全目录"

    async def harvest(self) -> None:
        observed = await self.session.observed(self.endpoint)
        payload = json.loads(observed["post_data"])
        condition = payload["condition"]
        check(
            condition.get("category") == 2
            and condition.get("kind") == ["1"]
            and not condition.get("keyword"),
            "携程目录不是应届校招",
        )
        for key in (
            "fromId",
            "country",
            "city",
            "bucode",
            "jobFamilyCode",
            "jobFamilyGroupCode",
        ):
            check(not condition.get(key), f"携程目录含局部筛选 {key}")
        check(
            set(condition)
            <= {
                "category",
                "kind",
                "keyword",
                "fromId",
                "country",
                "city",
                "bucode",
                "jobFamilyCode",
                "jobFamilyGroupCode",
            },
            "携程出现未知筛选条件",
        )
        page_size = int(payload["pager"]["size"])
        check(0 < page_size <= 100 and str(payload["pager"]["index"]) == "1", "携程初始分页异常")
        scope = Scope(name="graduate-category-2-kind-1")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = await self.session.request(
                observed["url"],
                payload={**payload, "pager": {**payload["pager"], "index": str(page)}},
            )
            check(str(response.get("retCode")) == "201", "携程岗位目录业务失败")
            data = response["retValue"]
            expected = int(data["total"])
            check(expected >= 0, "携程岗位总数无效")
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "携程翻页期间总数变化")
            rows = self.add_page(scope, data["recruitJobAdList"], seen, lambda row: str(row["id"]))
            check(len(rows) <= page_size, "携程单页超出分页大小")
            evidence = self.session.last_evidence
            for row in rows:
                check(
                    str(row.get("category")) == "2"
                    and str(row.get("kind")) == "1"
                    and text(row.get("kindName")) == "应届校招生",
                    "携程目录混入非正式校招岗位",
                )
                key = str(row["id"])
                from_id = text(row.get("fromId"))
                title = text(row.get("jobTitle"))
                check(
                    bool(from_id) and bool(title) and bool(row.get("requirements")),
                    "携程岗位身份或正文缺失",
                )
                duties, requirements = split_ctrip_body(str(row["requirements"]))
                if row.get("duty"):
                    duties = text(row["duty"])
                job = self.job(
                    key,
                    title=title,
                    source_url=f"https://{self.host}/#/campus/job-detail/{from_id}",
                    work_type="校招",
                    unit=text(row.get("buName")),
                    category_raw=text(row.get("jobFamilyGroupName")),
                    location=text(row.get("cityName")),
                    duties=duties,
                    requirements=requirements,
                    published=text(row.get("publishDate")),
                    field_sources={
                        "unit": "getJobAd.recruitJobAdList[].buName",
                        "duties": "getJobAd.recruitJobAdList[].requirements/duty",
                        "requirements": "getJobAd.recruitJobAdList[].requirements",
                        "published": "getJobAd.recruitJobAdList[].publishDate",
                        "deadline": "source_missing",
                    },
                )
                job.evidence = [evidence]
                resolved = self.before_detail(f"job:{key}", row, scope, job, evidence=evidence)
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", row, [job])
            if scope.unique >= expected:
                scope.terminal = True
                break
            check(bool(rows), "携程分页提前为空")
            page += 1
