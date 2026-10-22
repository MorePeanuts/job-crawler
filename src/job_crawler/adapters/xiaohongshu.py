"""Xiaohongshu's public 2027 campus job catalog."""

import json

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


class Xiaohongshu2027(Adapter):
    name = "xiaohongshu-2027"
    host = "job.xiaohongshu.com"
    path = "/campus/position"
    endpoint = "/websiterecruit/position/pageQueryPosition"
    ready_endpoints = (endpoint,)
    scope_description = "小红书官网 2027 校园招聘在招全目录，不含实习和社招"

    async def harvest(self) -> None:
        observed = await self.session.observed(self.endpoint)
        payload = json.loads(observed["post_data"])
        check(
            payload
            == {
                "positionName": "",
                "pageNum": 1,
                "pageSize": 10,
                "recruitType": "campus",
                "jobProjects": ["campus_autumn_27"],
            },
            "小红书校园目录的入口筛选或分页参数改变",
        )
        scope = Scope(name="campus-autumn-27")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = await self.session.request(
                observed["url"], payload={**payload, "pageNum": page}
            )
            check(
                response.get("success") is True and response.get("statusCode") == 200,
                "小红书职位接口失败",
            )
            data = response["data"]
            count = int(data["total"])
            pages = int(data["totalPage"])
            check(count > 0 and pages == (count + 9) // 10, "小红书校园目录总数无效")
            check(int(data["pageNum"]) == page and int(data["pageSize"]) == 10, "小红书页码错配")
            if scope.expected is None:
                scope.expected = count
            check(scope.expected == count, "小红书职位总数在分页期间变化")
            rows = self.add_page(scope, data["list"], seen, lambda row: str(row["positionId"]))
            check(0 < len(rows) <= 10, "小红书职位页提前为空或超出页长")
            for row in rows:
                check(row.get("jobProjectName") == "2027 校园招聘", "小红书目录混入其他项目")
                check(row.get("recruitStatus") == "in_recruitment", "小红书目录混入非在招岗位")
                title = text(row.get("positionName"))
                duties = text(row.get("duty"))
                requirements = text(row.get("qualification"))
                check(bool(title and duties and requirements), "小红书岗位标题或正文缺失")
                key = str(row["positionId"])
                listed = self.job(
                    key,
                    title=title,
                    source_url=f"https://{self.host}{self.path}/{key}",
                    location=text(row.get("workplace")),
                    category_raw=text(row.get("subDirectionName") or row.get("directionName")),
                    duties=duties,
                    requirements=requirements,
                    published=text(row.get("publishTime")),
                    batch="2027 校园招聘",
                    work_type="实习" if "实习" in title else "校招",
                    field_sources={
                        "duties": "pageQueryPosition.data.list[].duty",
                        "requirements": "pageQueryPosition.data.list[].qualification",
                        "published": "pageQueryPosition.data.list[].publishTime",
                        "location": "pageQueryPosition.data.list[].workplace",
                    },
                )
                reused = self.before_detail(f"job:{key}", row, scope, listed)
                if reused is None:
                    self.result.jobs.append(listed)
                    scope.details += 1
                    self.remember(f"job:{key}", row, [listed])
                else:
                    self.result.jobs.extend(reused)
            if scope.unique >= count:
                scope.terminal = True
                break
            check(page < pages, "小红书校园目录末页前缺记录")
            page += 1
