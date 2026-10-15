"""China Electronics Corporation's public group campus catalog."""

import json
import math
from typing import Any, cast

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

ROOT_ID = "464790010986497"


class CecCampus(Adapter):
    name = "cec-campus"
    host = "campus.cec.com.cn"
    path = "/position?positionType=0"
    endpoint = "/student-api/api/position/search"
    ready_endpoints = (endpoint,)
    scope_description = "中国电子集团官网 positionType=0 无筛选校园招聘目录及完整机构树"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        identity = json.loads(
            (await self.session.observed(f"/student-api/api/common/info/{ROOT_ID}"))["body"]
        )
        check(
            identity.get("code") == "000000"
            and str(identity["data"]["orgId"]) == ROOT_ID
            and identity["data"]["title"] == "中国电子信息产业集团有限公司",
            "中国电子集团官网主体改变",
        )
        tree = json.loads((await self.session.observed("/student-api/api/common/listOrg"))["body"])
        check(tree.get("code") == "000000", "中国电子机构树业务失败")
        roots = tree["data"]
        check(isinstance(roots, list) and len(roots) == 1, "中国电子机构树根数量异常")
        root = roots[0]
        check(
            str(root["id"]) == ROOT_ID and root["name"] == "中国电子信息产业集团有限公司",
            "中国电子机构树根改变",
        )
        names: set[str] = set()

        def collect_names(node: dict[str, Any]) -> None:
            name = text(node.get("name"))
            check(bool(name), "中国电子机构树单位名称缺失")
            names.add(name)
            children = node.get("children") or []
            check(isinstance(children, list), "中国电子机构树子节点变化")
            for child in children:
                check(isinstance(child, dict), "中国电子机构树子节点变化")
                collect_names(child)

        collect_names(root)
        observed = await self.session.observed(self.endpoint)
        payload = json.loads(observed["post_data"])
        check(
            payload
            == {
                "page": 1,
                "size": 10,
                "name": "",
                "positionType": "0",
                "degree": None,
                "orgId": [],
            },
            "中国电子校园目录带有局部筛选",
        )
        scope = Scope(name="position-type-0-group-all")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        position_numbers: set[str] = set()
        page = 1
        while True:
            response = await session.request(observed["url"], payload={**payload, "page": page})
            check(response.get("code") == "000000", "中国电子岗位目录业务失败")
            data = response["data"]
            expected = int(data["total"])
            pages = int(data["pages"])
            check(
                expected >= 0
                and pages == max(1, math.ceil(expected / 10))
                and int(data["current"]) == page
                and int(data["size"]) == 10,
                "中国电子分页元数据异常",
            )
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "中国电子翻页期间岗位总数变化")
            rows = self.add_page(scope, data["records"], seen, lambda row: str(row["id"]))
            check(len(rows) <= 10, "中国电子单页超过目录上限")
            evidence = session.last_evidence
            for row in rows:
                check(str(row.get("positionType")) == "0", "中国电子目录混入非校招岗位")
                check(
                    bool(row.get("canDeliver")) and bool(row.get("applyable")),
                    "中国电子目录含无法投递岗位",
                )
                nature = text(row.get("workNature"))
                check(nature in {"全职", "实习生"}, "中国电子岗位性质异常")
                unit = text(row.get("org"))
                check(unit in names, "中国电子岗位单位不在集团机构树中")
                number = text(row.get("positionNo"))
                check(bool(number) and number not in position_numbers, "中国电子岗位编号缺失或重复")
                position_numbers.add(number)
                check(
                    bool(text(row.get("name")))
                    and bool(text(row.get("jobDescription")))
                    and bool(text(row.get("jobRequirements"))),
                    "中国电子岗位标题、职责或要求缺失",
                )
                key = str(row["id"])
                job = self.job(
                    key,
                    title=text(row["name"]),
                    source_url=f"https://{self.host}{self.path}",
                    work_type="实习" if nature == "实习生" else "校招",
                    unit=unit,
                    location=text(row.get("cityName")),
                    duties=text(row["jobDescription"]),
                    requirements=text(row["jobRequirements"]),
                    deadline=text(row.get("closeDate")),
                    field_sources={
                        "unit": "position/search.records[].org + common/listOrg",
                        "location": "position/search.records[].cityName",
                        "duties": "position/search.records[].jobDescription",
                        "requirements": "position/search.records[].jobRequirements",
                        "deadline": "position/search.records[].closeDate",
                        "published": "source_missing",
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
            if page == pages:
                check(scope.unique == expected, "中国电子末页数与岗位总数不符")
                scope.terminal = True
                break
            check(bool(rows) and scope.unique < expected, "中国电子分页提前为空")
            page += 1
