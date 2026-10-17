"""iSoftStone's public campus list and identity-linked details."""

import json
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Job, Scope


class ISoftStoneCampus(Adapter):
    name = "isoftstone-campus"
    host = "career.isoftstone.com"
    path = "/talent/htmls/xiaoyuanzhaopin/index.html"
    ready_endpoints = ("/campus/all",)
    scope_description = "软通动力官方校园目录全部城市及类型；排除 API 明确标记的实习岗位"

    def detail_page(self, identity: str) -> str:
        return f"https://{self.host}/talent/htmls/xiaozhaozhiweixiangqing/index.html?" + urlencode(
            {"id": identity, "recruitType": 1}
        )

    def listed_job(self, row: dict[str, Any]) -> Job:
        return self.job(
            str(row["id"]),
            title=text(row["name"]),
            source_url=self.detail_page(str(row["id"])),
            published=text(row.get("publish_date")),
            education=text(row.get("educational_name")),
            location=text(row.get("address_detail")),
        )

    async def harvest(self) -> None:
        observed = await self.session.observed("/campus/all")
        payload = json.loads(observed["post_data"])
        check(
            payload == {"workCity": "", "jobTypeId": "0", "keyWord": "", "maxcount": 6, "page": 1},
            "软通动力初始目录带筛选或分页契约改变",
        )
        scope = Scope(name="isoftstone-campus-all")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        detail_api = ""
        while True:
            data = await self.session.request(observed["url"], payload={**payload, "page": page})
            count = int(data["count"])
            check(count >= 0, "软通动力目录总数无效")
            if scope.expected is None:
                scope.expected = count
            check(count == scope.expected, "软通动力分页期间总数变化")
            rows = self.add_page(scope, data["results"], seen, lambda row: str(row["id"]))
            evidence = self.session.last_evidence
            for row in rows:
                identity = str(row["id"])
                try:
                    kind = text(row["hiretype_name"])
                    check(kind in {"全职", "实习"}, "软通动力未知招聘类型")
                    if kind == "实习":
                        scope.skipped_out_of_scope += 1
                        continue
                    listing = self.listed_job(row)
                    listing.evidence = [evidence]
                    cached = self.before_detail(identity, row, scope, listing, evidence=evidence)
                    if cached is not None:
                        self.result.jobs.extend(cached)
                        continue
                    if not detail_api:
                        await self.session.open(
                            self.detail_page(identity), ready_endpoints=("/campus/detail",)
                        )
                        detail_api = (await self.session.observed("/campus/detail"))["url"]
                    response = await self.session.request(
                        detail_api, payload={"id": identity}, detail=True
                    )
                    check(response.get("success") == "true", "软通动力详情业务失败")
                    detail = response["data"]
                    check(str(detail["id"]) == identity, "软通动力详情 ID 与列表不符")
                    check(detail["name"] == row["name"], "软通动力详情标题与列表不符")
                    check(detail["hiretype_name"] == "全职", "软通动力详情招聘类型改变")
                    check(
                        "describe" in detail and "jobrequirements" in detail,
                        "软通动力详情缺正文字段",
                    )
                    job = self.listed_job(detail)
                    job.duties = text(detail["describe"])
                    job.requirements = text(detail["jobrequirements"])
                    job.field_sources.update(
                        duties="campus/detail.data.describe",
                        requirements="campus/detail.data.jobrequirements",
                        education="campus/detail.data.educational_name",
                        location="campus/detail.data.address_detail：省市，不是详细地址",
                        published="campus/detail.data.publish_date",
                        deadline="source_missing",
                    )
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(identity, row, [job])
                except Exception as exc:
                    self.error(exc, identity)
            if data["next"] is None:
                check(scope.unique == count, "软通动力分页提前结束")
                scope.terminal = True
                break
            check(bool(rows) and scope.unique < count, "软通动力分页终态与总数不符")
            cursor = parse_qs(urlsplit(data["next"]).query)
            check(
                cursor.get("page") == [str(page + 1)] and cursor.get("maxcount") == ["6"],
                "软通动力 next 页码改变",
            )
            page += 1
