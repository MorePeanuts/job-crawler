"""China Minsheng Bank's public campus catalogue and job detail API."""

from collections import Counter
from typing import Any, Protocol, cast
from urllib.parse import urlencode, urlsplit

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

OTHER_ENTITIES = frozenset({"民生金融租赁", "民生加银基金", "民生科技", "民生理财", "民生置业"})
API = "https://career.cmbc.com.cn/portal/rest/careerrecruitment"


class FormSession(Protocol):
    async def request(
        self, url: str, *, form: dict[str, str] | None = None, detail: bool = False
    ) -> dict[str, Any]: ...


def bank_unit(name: str) -> bool:
    return name == "民生银行总行" or name.endswith("分行")


class CmbcCampus(Adapter):
    name = "cmbc-campus"
    host = "career.cmbc.com.cn"
    path = "/#/app/recruitmentlist/campus/"
    ready_endpoints = ("/portal/rest/careerrecruitment/search.view",)
    scope_description = "民生银行 campus 公开全目录；仅总行及分行，排除五家独立子公司"

    async def harvest(self) -> None:
        stamp = int(self.collected_at.timestamp() * 1000)
        tree_response = await self.session.request(
            f"{API}/enterpriseList.view?{urlencode({'random': stamp, 'recruitmentId': 'campus'})}"
        )
        check(tree_response.get("success") is True, "民生银行机构树请求失败")
        tree = tree_response["data"]
        check(isinstance(tree, dict), "民生银行机构树结构变化")
        entities = tree.get("enterprises")
        check(isinstance(entities, list) and bool(entities), "民生银行机构树为空")
        counts: dict[str, int] = {}
        for entity in entities:
            check(isinstance(entity, dict), "民生银行机构节点结构变化")
            name = text(entity.get("name"))
            check(name not in counts, "民生银行机构树重复机构")
            check(bank_unit(name) or name in OTHER_ENTITIES, "民生银行机构树出现未知法人")
            check(text(entity.get("parentId")) == "default-enterprise", "民生银行机构层级变化")
            check(bool(text(entity.get("id"))), "民生银行机构缺少 ID")
            count = entity.get("total")
            check(isinstance(count, int) and count > 0, "民生银行机构岗位数异常")
            counts[name] = count
        total = tree.get("total")
        check(isinstance(total, int) and total > 0, "民生银行校招总数异常")
        check(sum(counts.values()) == total, "民生银行机构树总数不闭合")
        tree_evidence = self.session.last_evidence
        scope = Scope(name="campus-all-enterprises", expected=total, evidence=[tree_evidence])
        self.result.scopes.append(scope)

        listing = await self.session.observed("/careerrecruitment/search.view")
        parts = urlsplit(listing["url"])
        check(
            parts.hostname == self.host
            and parts.path == "/portal/rest/careerrecruitment/search.view",
            "民生银行列表接口变化",
        )
        form = {
            "view": "careerRecruitmentList",
            "pageNo": "1",
            "pageSize": "20",
            "searchRecruitmentIds": "campus",
            "searchEnterpriseId": "",
        }
        seen: set[str] = set()
        distribution: Counter[str] = Counter()
        pages = (total + 19) // 20
        for page in range(1, pages + 1):
            response = await cast(FormSession, self.session).request(
                f"{API}/search.view?random={stamp}", form={**form, "pageNo": str(page)}
            )
            check(response.get("success") is True, "民生银行列表请求失败")
            data = response["data"]
            check(isinstance(data, dict), "民生银行列表结构变化")
            check(
                data.get("totalLine") == total
                and data.get("pageCount") == pages
                and data.get("pageNo") == page
                and data.get("pageSize") == 20,
                "民生银行列表总数或分页变化",
            )
            rows = data.get("items")
            check(isinstance(rows, list), "民生银行列表不是数组")
            check(len(rows) == min(20, total - (page - 1) * 20), "民生银行分页条数变化")
            rows = self.add_page(scope, rows, seen, lambda row: text(row.get("id")))
            listing_evidence = self.session.last_evidence
            for row in rows:
                key = text(row.get("id"))
                unit = text(row.get("careerRecruitment_career_enterprise_name"))
                check(unit in counts, "民生银行列表出现机构树之外的单位")
                distribution[unit] += 1
                if unit in OTHER_ENTITIES:
                    scope.skipped_out_of_scope += 1
                    continue
                reused = self.before_detail(key, row, scope, evidence=listing_evidence)
                if reused is not None:
                    self.result.jobs.extend(reused)
                    continue
                try:
                    detail_url = f"{API}/view/{key}.view?" + urlencode(
                        {"random": stamp, "view": "careerRecruitmentView", "recruitmentId": key}
                    )
                    detail_response = await self.session.request(detail_url, detail=True)
                    check(detail_response.get("success") is True, "民生银行详情请求失败")
                    detail = detail_response["data"]
                    check(isinstance(detail, dict), "民生银行详情结构变化")
                    for list_field, detail_field in (
                        ("id", "id"),
                        ("careerRecruitment_career_name", "careerRecruitment_career_name"),
                        (
                            "careerRecruitment_career_enterprise_name",
                            "careerRecruitment_career_enterprise_name",
                        ),
                        ("careerRecruitment_regions_name", "careerRecruitment_regions_name"),
                        (
                            "careerRecruitment_career_expirationDate",
                            "careerRecruitment_career_expirationDate",
                        ),
                    ):
                        check(
                            text(row.get(list_field)) == text(detail.get(detail_field)),
                            "民生银行详情与列表身份不符",
                        )
                    duties = text(detail.get("careerRecruitment_career_careerDetail_content"))
                    requirements = text(
                        detail.get("careerRecruitment_career_careerDetail_qualifications")
                    )
                    check(bool(duties and requirements), "民生银行岗位正文缺失")
                    job = self.job(
                        key,
                        title=text(row.get("careerRecruitment_career_name")),
                        unit=unit,
                        location=text(row.get("careerRecruitment_regions_name")),
                        published=text(row.get("careerRecruitment_career_publishDate")),
                        deadline=text(row.get("careerRecruitment_career_expirationDate")),
                        duties=duties,
                        requirements=requirements,
                        source_url=f"https://{self.host}/#/app/recruitmentview/{key}",
                        field_sources={
                            "published": "search.view.data.items[].careerRecruitment_career_publishDate",
                            "deadline": "search.view.data.items[].careerRecruitment_career_expirationDate",
                            "duties": "view/{id}.view.data.careerRecruitment_career_careerDetail_content",
                            "requirements": "view/{id}.view.data.careerRecruitment_career_careerDetail_qualifications",
                        },
                    )
                    job.evidence = [listing_evidence, self.session.last_evidence]
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(key, row, [job])
                except Exception as exc:
                    self.error(exc, key)
        check(distribution == counts, "民生银行列表与机构树岗位数不一致")
        scope.terminal = True
