"""Li Auto's public formal campus catalog."""

import json
import math
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import CrawlError

LIST_PATH = "/osd-hr-recruitment-website/v1/recruit/school/job-page"
DETAIL_PATH = "/osd-hr-recruitment-website/v1/recruit/job/detail"
API_ORIGIN = "https://api-web.lixiang.com"


class LiAutoCampus(Adapter):
    name = "li-auto-campus"
    host = "www.lixiang.com"
    path = "/employ/campus/list.html?fromJob=1"
    ready_endpoints = (f"{API_ORIGIN}{LIST_PATH}",)
    scope_description = "理想汽车校园招聘与实习页面中 job_mode=1 的全部正式校招岗位；排除实习"

    def detail_page(self, row: dict[str, Any]) -> str:
        return f"https://{self.host}/employ/detail/{row['id']}.html?" + urlencode(
            {"jobCode": row["code"], "fromJob": 1}
        )

    async def harvest(self) -> None:
        observed = await self.session.observed(LIST_PATH)
        parsed = urlsplit(observed["url"])
        check(
            parsed.scheme == "https"
            and parsed.netloc == "api-web.lixiang.com"
            and parsed.path == LIST_PATH,
            "理想汽车列表接口来源改变",
        )
        params = parse_qs(parsed.query)
        check(params == {"page": ["1"], "page_size": ["10"]}, "理想汽车初始目录带有未知筛选")
        scope = Scope(name="formal-campus-job-mode-1")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        listings: list[tuple[dict[str, Any], str]] = []
        page = 1
        size = 100
        pages = 0
        try:
            while True:
                result = await self.session.request(
                    query(observed["url"], page=page, page_size=size, job_mode=1)
                )
                check(result.get("code") == 0, "理想汽车校园列表业务失败")
                data = result["data"]
                expected = int(data["total_count"])
                returned_pages = int(data["total_pages"])
                check(expected >= 0, "理想汽车校园目录总数无效")
                check(
                    int(data["page"]) == page and int(data["page_size"]) == size,
                    "理想汽车返回错误页码",
                )
                check(returned_pages == math.ceil(expected / size), "理想汽车页数与总数不一致")
                if scope.expected is None:
                    scope.expected = expected
                    pages = returned_pages
                check(
                    expected == scope.expected and returned_pages == pages, "理想汽车目录总数变化"
                )
                rows = self.add_page(scope, data["items"], seen, lambda row: str(row["id"]))
                evidence = self.session.last_evidence
                check(len(rows) <= size, "理想汽车单页超出容量")
                for row in rows:
                    check(
                        int(row.get("hire_mode", -1)) == 2
                        and text(row.get("job_mode_name")) == "正式",
                        "理想汽车正式校园目录混入其他招聘类型",
                    )
                    check(
                        bool(row.get("code")) and bool(row.get("title")), "理想汽车列表缺岗位身份"
                    )
                    listings.append((row, evidence))
                if page >= pages:
                    check(scope.unique == expected, "理想汽车末页岗位数与源总数不一致")
                    scope.terminal = True
                    break
                check(bool(rows), "理想汽车分页提前为空")
                page += 1
        except Exception as exc:
            self.error(exc, f"page:{page}")

        detail_url = ""
        first_detail: dict[str, Any] | None = None
        first_detail_id = ""
        for row, list_evidence in listings:
            job_id = str(row["id"])
            try:
                listing = self.job(
                    job_id,
                    title=text(row["title"]),
                    source_url=self.detail_page(row),
                    location=text(row.get("location_title")),
                    category_raw=text(row.get("second_job_function_title")),
                )
                listing.evidence = [list_evidence] if list_evidence else []
                reused = self.before_detail(
                    f"job:{job_id}", row, scope, listing, evidence=list_evidence
                )
                if reused is not None:
                    self.result.jobs.extend(reused)
                    continue
                if not detail_url:
                    await self.session.open(
                        self.detail_page(row), ready_endpoints=(f"{API_ORIGIN}{DETAIL_PATH}",)
                    )
                    observed_detail = await self.session.observed(f"{DETAIL_PATH}?")
                    detail_params = parse_qs(urlsplit(observed_detail["url"]).query)
                    check(detail_params == {"job_id": [job_id]}, "理想汽车首条详情 ID 与列表不对应")
                    detail_url = observed_detail["url"]
                    first_detail = json.loads(observed_detail["body"])
                    first_detail_id = job_id
                    detail_evidence = self.session.last_evidence
                else:
                    first_detail = None
                    detail_evidence = ""
                result_detail = (
                    first_detail
                    if first_detail is not None and first_detail_id == job_id
                    else await self.session.request(query(detail_url, job_id=job_id), detail=True)
                )
                check(result_detail.get("code") == 0, "理想汽车详情业务失败")
                item = result_detail["data"]
                check(str(item["id"]) == job_id, "理想汽车详情与列表 ID 不一致")
                check(str(item["code"]) == str(row["code"]), "理想汽车详情岗位代码不一致")
                check(
                    int(item.get("hire_mode", -1)) == 2
                    and text(item.get("job_mode_name")) == "正式"
                    and text(item.get("subject_name"))
                    in {"2026校园招聘", "2027校园招聘", "2027“理想+”", "实习生招聘"},
                    "理想汽车详情不是正式校园招聘",
                )
                check("description" in item and "requirements" in item, "理想汽车详情正文结构改变")
                job = self.job(
                    job_id,
                    title=text(item["title"]),
                    work_type=(
                        "实习" if text(item.get("subject_name")) == "实习生招聘" else "校招"
                    ),
                    source_url=self.detail_page(row),
                    unit=text(item.get("department_title")),
                    batch=text(item.get("subject_name")),
                    location=text(item.get("location_title")),
                    category_raw=text(item.get("second_job_function_title")),
                    duties=text(item["description"]),
                    requirements=text(item["requirements"]),
                    field_sources={
                        "duties": "recruit/job/detail.data.description",
                        "requirements": "recruit/job/detail.data.requirements",
                        "location": "recruit/job/detail.data.location_title",
                        "published": "源站未提供，留空",
                    },
                )
                job.evidence = [
                    e for e in (list_evidence, detail_evidence or self.session.last_evidence) if e
                ]
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{job_id}", row, [job])
            except Exception as exc:
                self.error(exc, job_id)
                if isinstance(exc, CrawlError) and exc.code in {
                    "access_denied",
                    "request_budget",
                    "time_budget",
                }:
                    raise
