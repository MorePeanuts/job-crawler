"""Yitu's public campus list with full job descriptions."""

import json
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.adapters.platforms import check
from job_crawler.description import split_sections
from job_crawler.models import Scope


class Yitu2027(Adapter):
    name = "yitu-2027"
    host = "www.yitutech.com"
    path = "/cn/career?mode=campus"
    endpoint = "api.mokahr.com/v1/jobs/yitu-inc"
    ready_endpoints = (endpoint,)
    scope_description = "依图官网校园招聘公开目录；排除接口中实习性质或标题的岗位"

    async def harvest(self) -> None:
        observed = await self.session.observed(self.endpoint)
        values = parse_qs(urlsplit(observed["url"]).query)
        check(
            values == {"mode": ["campus"], "limit": ["1000"], "offset": ["0"]},
            "依图公开目录带有未知筛选或分页参数",
        )
        scope = Scope(name="yitu-campus")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        offset = 0
        while True:
            response = (
                json.loads(observed["body"])
                if offset == 0
                else await self.session.request(query(observed["url"], offset=offset))
            )
            check(response.get("code") == 0, "依图校园目录业务失败")
            expected = int(response["total"])
            check(expected > 0, "依图校园目录为空或总数无效")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "依图校园目录总数在分页期间变化")
            rows = self.add_page(scope, response["jobs"], seen, lambda row: str(row["id"]))
            check(bool(rows) and len(rows) <= 1000, "依图校园目录分页提前为空或超长")
            for row in rows:
                check(row.get("orgId") == "yitu-inc", "依图目录混入其他组织")
                check(row.get("status") == "open", "依图目录混入已关闭岗位")
                title = text(row.get("title"))
                check(bool(title), "依图职位标题为空")
                if "实习" in title or row.get("commitment") == "实习":
                    scope.skipped_out_of_scope += 1
                    continue
                check(
                    "2027届校招" in title and row.get("commitment") == "全职",
                    "依图正式校招项目不符",
                )
                key = str(row["id"])
                duties, requirements = split_sections(text(row.get("description")))
                check(bool(duties and requirements), "依图职位正文无法区分职责和要求")
                locations = row.get("locations") or []
                check(isinstance(locations, list) and bool(locations), "依图职位地点缺失")
                cities = list(dict.fromkeys(text(item.get("province")) for item in locations))
                addresses = list(dict.fromkeys(text(item.get("address")) for item in locations))
                job = self.job(
                    key,
                    title=title,
                    source_url=f"https://app.mokahr.com/campus_apply/yitu-inc/#/job/{key}/apply?pure=1",
                    batch="2027届校招",
                    unit=text((row.get("department") or {}).get("name")),
                    category_raw=text((row.get("zhineng") or {}).get("name")),
                    location="、".join(city for city in cities if city),
                    address="、".join(address for address in addresses if address),
                    duties=duties,
                    requirements=requirements,
                    published=text(row.get("publishedAt")),
                    deadline=text(row.get("closedAt")),
                    field_sources={
                        "duties": "v1/jobs.description:岗位职责",
                        "requirements": "v1/jobs.description:任职资格",
                        "published": "v1/jobs.publishedAt",
                        "location": "v1/jobs.locations[].province",
                        "address": "v1/jobs.locations[].address",
                    },
                )
                reused = self.before_detail(f"job:{key}", row, scope, job)
                if reused is None:
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(f"job:{key}", row, [job])
                else:
                    self.result.jobs.extend(reused)
            if scope.unique >= expected:
                scope.terminal = True
                break
            check(len(rows) == 1000, "依图校园目录末页前记录数不足")
            offset += len(rows)
