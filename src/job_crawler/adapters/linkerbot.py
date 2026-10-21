"""Linkerbot's public recruitment category tree."""

import json
from typing import Any, cast

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession


class LinkerbotCampus(Adapter):
    name = "linkerbot-campus"
    host = "linkerbot.cn"
    path = "/about/join"
    ready_endpoints = ("/jeecg-boot/lingxin/jobCategory/public/tree",)
    scope_description = "灵心巧手官网完整招聘类别树；仅取已发布校园岗位并排除实习"

    async def harvest(self) -> None:
        response = await self.session.observed("/jeecg-boot/lingxin/jobCategory/public/tree")
        data = json.loads(response["body"])
        check(data.get("success") is True and data.get("code") == 200, "职位树接口失败")
        categories = data["result"]
        check(isinstance(categories, list) and bool(categories), "职位类别树为空")
        session = cast(BrowserSession, self.session)
        evidence = session.output / "linkerbot-public-tree.json"
        write_json(evidence, {"url": response["url"], "data": data})
        session.last_evidence = str(evidence)
        scope = Scope(name="public-recruitment-tree")
        self.result.scopes.append(scope)
        rows: list[dict[str, Any]] = []
        for category in categories:
            check(isinstance(category, dict), "职位类别结构改变")
            positions = category.get("positions")
            check(isinstance(positions, list), "职位类别缺少岗位数组")
            rows.extend(positions)
        scope.expected = len(rows)
        check(scope.expected > 0, "公开岗位总数为零")
        seen: set[str] = set()
        rows = self.add_page(scope, rows, seen, lambda row: str(row["id"]))
        for row in rows:
            key = str(row["id"])
            if row.get("recruitType") != "campus":
                scope.skipped_out_of_scope += 1
                continue
            if row.get("status") != "published":
                scope.skipped_closed += 1
                continue
            title = text(row.get("title"))
            check(bool(title), "校园岗位标题为空")
            duties = self._json_lines(row.get("responsibilities"))
            requirements = self._json_lines(row.get("requirements"))
            check(bool(duties), "校园岗位职责为空")
            location = self._json_lines(row.get("locations"))
            job = self.job(
                key,
                title=title,
                work_type="实习" if "实习" in title else "校招",
                source_url=f"https://{self.host}{self.path}",
                category_raw=text(row.get("category")),
                location=location,
                duties=duties,
                requirements=requirements,
                field_sources={
                    "duties": "jobCategory/public/tree.result[].positions[].responsibilities",
                    "requirements": "jobCategory/public/tree.result[].positions[].requirements",
                    "location": "jobCategory/public/tree.result[].positions[].locations",
                    "published": "source_missing; createTime is not publication date",
                },
            )
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True

    @staticmethod
    def _json_lines(value: object) -> str:
        check(isinstance(value, str), "岗位数组字段不是 JSON 文本")
        assert isinstance(value, str)
        items = json.loads(value)
        check(
            isinstance(items, list) and all(isinstance(item, str) for item in items),
            "岗位数组结构改变",
        )
        return "\n".join(item.strip() for item in items if item.strip())
