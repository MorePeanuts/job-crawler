"""China Telecom's public campus unit tree and per-position detail API."""

import json
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import CrawlError

TREE = (
    "https://job.chinatelecom.com.cn/wt/web/platform/mvc/officialWeb/"
    "getShowRecruitOrg?corpCode=TELE&recruitType=1"
)
LIST = "https://job.chinatelecom.com.cn/wt/TELE/web/mode400/position/list"
DETAIL = "https://job.chinatelecom.com.cn/wt/TELE/web/mode400/position/detail"


class FormRequester(Protocol):
    async def request(
        self, url: str, *, form: dict[str, str], detail: bool = False
    ) -> dict[str, Any]: ...


class ChinaTelecomCampus(Adapter):
    name = "chinatelecom-campus"
    host = "job.chinatelecom.com.cn"
    path = "/wt/TELE/web/index?brandCode=1"
    ready_endpoints = (TREE,)
    scope_description = "中国电信公开校园招聘 recruitType=1 全部根单位及其下辖岗位"

    async def harvest(self) -> None:
        observed = await self.session.observed("/getShowRecruitOrg?")
        check(observed["url"] == TREE, "中国电信招聘单位目录接口改变")
        params = parse_qs(urlsplit(observed["url"]).query)
        check(params == {"corpCode": ["TELE"], "recruitType": ["1"]}, "单位目录筛选改变")
        tree = json.loads(observed["body"])
        check(str(tree.get("code")) == "00", "中国电信单位目录业务失败")
        roots = tree.get("data")
        check(isinstance(roots, list) and bool(roots), "中国电信单位目录为空")
        root_ids = [str(row["uniqueKey"]) for row in roots]
        check(len(set(root_ids)) == len(root_ids), "中国电信根单位 ID 重复")
        check(all(text(row.get("cnExternalName")) for row in roots), "根单位名称缺失")
        tree_evidence = self.session.last_evidence
        requester = cast(FormRequester, self.session)
        all_post_ids: set[str] = set()
        for root in roots:
            root_id = str(root["uniqueKey"])
            root_name = text(root["cnExternalName"])
            scope = Scope(name=f"campus-unit-{root_id}", unit=root_name)
            scope.evidence.append(tree_evidence)
            self.result.scopes.append(scope)
            try:
                await self._unit(requester, root_id, root_name, scope, all_post_ids)
            except Exception as exc:
                self.error(exc, f"unit:{root_id}")
                if isinstance(exc, CrawlError) and exc.code in {
                    "access_denied",
                    "request_budget",
                    "time_budget",
                }:
                    raise

    async def _unit(
        self,
        requester: FormRequester,
        root_id: str,
        root_name: str,
        scope: Scope,
        all_post_ids: set[str],
    ) -> None:
        page = 1
        seen: set[str] = set()
        size = 50
        while True:
            form = {
                "rowSize": str(size),
                "rowIndex": str(page),
                "recruitType": "1",
                "org": root_id,
                "postName": "",
                "workPlace": "",
                "jobCategory": "",
                "recruitProject": "",
                "keyWord": "",
            }
            response = await requester.request(LIST, form=form)
            check(str(response.get("code")) == "00", "中国电信岗位目录业务失败")
            data = response.get("data")
            if not isinstance(data, dict):
                raise CrawlError("schema_changed", "中国电信岗位目录数据缺失")
            expected = int(data["rowCount"])
            check(expected >= 0, "中国电信岗位总数无效")
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "中国电信分页时总数变化")
            rows = self.add_page(scope, data["details"], seen, lambda row: str(row["PostId"]))
            check(len(rows) <= size, "中国电信一页岗位数超限")
            list_evidence = self.session.last_evidence
            for row in rows:
                post_id = str(row["PostId"])
                check(post_id not in all_post_ids, "中国电信岗位跨根单位重复")
                all_post_ids.add(post_id)
                check(int(row.get("RecruitType", -1)) == 1, "岗位混入非校园招聘")
                title = text(row.get("PostName"))
                check(bool(title), "中国电信岗位名称为空")
                source_url = self.source.url
                listing = self.job(
                    post_id,
                    title=title,
                    unit=root_name,
                    location=text(row.get("WorkPlace")),
                    category_raw=text(row.get("PostType")),
                    published=text(row.get("ReleaseTime")),
                    source_url=source_url,
                )
                listing.evidence = [list_evidence]
                reused = self.before_detail(
                    f"job:{post_id}", row, scope, listing, evidence=list_evidence
                )
                if reused is not None:
                    self.result.jobs.extend(reused)
                    continue
                detail_response = await requester.request(
                    DETAIL, form={"postId": post_id, "recruitType": "1"}, detail=True
                )
                check(str(detail_response.get("code")) == "00", "中国电信岗位详情业务失败")
                detail = detail_response.get("data")
                if not isinstance(detail, dict):
                    raise CrawlError("schema_changed", "中国电信岗位详情为空")
                check(text(detail.get("name")) == title, "中国电信详情标题与列表不一致")
                org_code = text(detail.get("orgCode"))
                check(root_id in org_code.split("/"), "中国电信详情根单位与列表不一致")
                quick_type = detail.get("quickRecruitType")
                if quick_type is not None:
                    check(int(quick_type) == 21, "岗位混入非正式校招")
                else:
                    check(
                        "校园招聘" in text(detail.get("projectName")),
                        "缺少正式校招类型及项目证据",
                    )
                check(text(detail.get("ReleaseTime")) == listing.published, "发布日期错配")
                check(
                    bool(text(detail.get("workConcet")))
                    or bool(text(detail.get("serviceCondition"))),
                    "中国电信详情缺少岗位正文",
                )
                unit_names = [text(detail.get("SecondOrgName")), text(detail.get("OrgName"))]
                job = self.job(
                    post_id,
                    title=title,
                    batch=text(detail.get("projectName")),
                    unit=" / ".join(name for name in unit_names if name),
                    location=text(detail.get("workPlace") or row.get("WorkPlace")),
                    education=text(detail.get("EducationName")),
                    category_raw=text(detail.get("PostType")),
                    duties=text(detail.get("workConcet")),
                    requirements=(
                        text(detail.get("serviceCondition"))
                        + (
                            "\n招聘专业：" + text(detail.get("Subject"))
                            if text(detail.get("Subject"))
                            else ""
                        )
                    ),
                    published=listing.published,
                    source_url=source_url,
                    field_sources={
                        "unit": "position/detail.data.SecondOrgName + OrgName",
                        "duties": "position/detail.data.workConcet",
                        "requirements": "position/detail.data.serviceCondition",
                        "major": "position/detail.data.Subject，追加至任职要求并注明来源",
                        "published": "position/list.data.details[].ReleaseTime",
                        "deadline": "source_missing",
                    },
                )
                job.evidence = [list_evidence, self.session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{post_id}", row, [job])
            if scope.unique >= expected:
                check(scope.unique == expected, "中国电信末页唯一岗位数与总数不符")
                scope.terminal = True
                break
            check(len(rows) == size, "中国电信分页提前结束")
            page += 1
