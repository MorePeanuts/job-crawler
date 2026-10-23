"""Public Moka campus pages and their documented-in-page response format."""

import base64
import json
import re
from typing import Any, Protocol, cast

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.description import split_sections
from job_crawler.filtering import select
from job_crawler.models import Issue, Job, Scope
from job_crawler.transport import CrawlError


class Page(Protocol):
    async def evaluate(self, script: str) -> Any: ...


class PageSession(Protocol):
    page: Page


class ExactObserver(Protocol):
    async def observed_path(self, path: str) -> dict[str, Any]: ...


def decode(response: dict[str, Any], iv: str) -> dict[str, Any]:
    if "necromancer" not in response:
        result = response
    else:
        key = response["necromancer"]
        data = response.get("data")
        check(isinstance(iv, str) and len(iv.encode()) == 16, "Moka 页面缺少有效解密 IV")
        check(isinstance(key, str) and len(key.encode()) in {16, 24, 32}, "Moka 响应密钥无效")
        if not isinstance(data, str):
            raise CrawlError("schema_changed", "Moka 加密响应结构改变")
        try:
            cipher = Cipher(algorithms.AES(key.encode()), modes.CBC(iv.encode()))
            decryptor = cipher.decryptor()
            padded = decryptor.update(base64.b64decode(data, validate=True)) + decryptor.finalize()
            unpadder = PKCS7(128).unpadder()
            result = json.loads((unpadder.update(padded) + unpadder.finalize()).decode())
        except (ValueError, UnicodeDecodeError, KeyError) as exc:
            raise CrawlError("decode_failed", "Moka 公共响应解码失败；页面版本可能改变") from exc
    check(isinstance(result, dict) and result.get("code") == 0, "Moka 业务响应失败")
    return result


def sections(html: str) -> tuple[str, str]:
    body = re.sub(r"(?m)^[ \t]*[:：][ \t]*$", "", text(html))
    return split_sections(body)


def location_text(rows: object) -> tuple[str, str]:
    if not isinstance(rows, list):
        raise CrawlError("schema_changed", "Moka 地点不是数组")
    names: list[str] = []
    paths: list[str] = []
    for item in rows:
        if not isinstance(item, dict):
            raise CrawlError("schema_changed", "Moka 地点结构改变")
        city = text(item.get("cityName"))
        province = text(item.get("provinceName"))
        if city and city not in names:
            names.append(city)
        if city and province:
            path = f"{province}/{city}"
            if path not in paths:
                paths.append(path)
    return (paths[0] if len(paths) == len(names) == 1 else "、".join(names), "")


class Moka(Adapter):
    host = "app.mokahr.com"
    org = ""
    site_id = 0
    route = "campus-recruitment"
    module_id = ""
    module_group_type = "zhineng"
    module_commitments = ("全职",)
    catalog_department_id = ""
    path = ""
    ready_endpoints = ("/api/outer/ats-apply/website/jobs/v2",)
    scope_description = (
        "Moka campus-recruitment 单站点公开无筛选全目录；实习/兼职保留原类型供公共层排除"
    )

    def detail_page(self, job_id: str) -> str:
        return f"https://{self.host}/{self.route}/{self.org}/{self.site_id}#/job/{job_id}"

    def in_scope(self, row: dict[str, Any]) -> bool:
        return True

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        return None

    async def harvest(self) -> None:
        page = cast(PageSession, self.session).page
        iv = await page.evaluate("() => window.TurboApply?.data?.aesIv")
        check(isinstance(iv, str) and len(iv.encode()) == 16, "Moka 页面 IV 无效")
        observer = cast(ExactObserver, self.session)
        catalog_path = (
            "/api/outer/ats-apply/website/jobs/module"
            if self.module_id
            else "/api/outer/ats-apply/website/jobs/v2"
        )
        observed = await observer.observed_path(catalog_path)
        payload = json.loads(observed["post_data"])
        check(payload.get("orgId") == self.org, "Moka 组织不匹配")
        check(str(payload.get("siteId")) == str(self.site_id), "Moka 站点不匹配")
        if self.module_id:
            check(str(payload.get("moduleId")) == self.module_id, "Moka 招聘模块不匹配")
            check(
                payload.get("commitments", []) == list(self.module_commitments),
                "Moka 招聘模块岗位性质筛选变化",
            )
            check(
                payload.get("needGroupType") == self.module_group_type,
                "Moka 招聘模块类别改变",
            )
        else:
            check(payload.get("site") == "campus", "Moka 入口不是校园站点")
        if self.catalog_department_id:
            check(
                [str(value) for value in payload.get("departmentIds", [])]
                == [self.catalog_department_id],
                "Moka 公司分支筛选不匹配",
            )
        else:
            check(not payload.get("departmentIds"), "Moka 目录带有未知公司筛选")
        check(int(payload.get("offset", -1)) == 0, "Moka 列表不是第一页")
        check(
            not payload.get("jobIdTopList") and not payload.get("customFields"), "Moka 目录带有筛选"
        )
        for key in ("keyword", "locations", "zhineng", "commitment"):
            check(not payload.get(key), f"Moka 目录带有筛选 {key}")
        limit = int(payload["limit"])
        check(0 < limit <= 100, "Moka 分页大小异常")
        if self.module_id:
            limit = 100
        scope = Scope(
            name=f"campus-site-{self.site_id}"
            + (f"-module-{self.module_id}" if self.module_id else "")
        )
        self.result.scopes.append(scope)
        seen: set[str] = set()
        offset = 0
        detail_api = ""
        while True:
            wrapped = await self.session.request(
                observed["url"], payload={**payload, "offset": offset, "limit": limit}
            )
            data = decode(wrapped, iv)["data"]
            expected = int(data["jobStats"]["total"])
            check(expected > 0, "Moka 公开职位目录为空或总数无效")
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "Moka 分页期间总数变化")
            rows = self.add_page(scope, data["jobs"], seen, lambda row: str(row["id"]))
            list_evidence = self.session.last_evidence
            for row in rows:
                job_id = str(row["id"])
                try:
                    check(row.get("orgId") == self.org, "Moka 列表混入其他组织")
                    if not self.in_scope(row):
                        scope.skipped_out_of_scope += 1
                        continue
                    listing = self._job(row, row, list_evidence)
                    if select(listing, "all", self.as_of).reason == "expired":
                        listing.detail_mode = "listing_only"
                        self.result.jobs.append(listing)
                        scope.skipped_expired += 1
                        continue
                    resolved = self.before_detail(
                        f"job:{job_id}", row, scope, listing, evidence=list_evidence
                    )
                    if resolved is not None:
                        self.result.jobs.extend(resolved)
                        continue
                    if not detail_api:
                        await self.session.open(
                            self.detail_page(job_id),
                            ready_endpoints=("/api/outer/ats-apply/website/job",),
                        )
                        observed_detail = await observer.observed_path(
                            "/api/outer/ats-apply/website/job"
                        )
                        detail_api = observed_detail["url"]
                        first_detail = decode(json.loads(observed_detail["body"]), iv)
                        detail_evidence = self.session.last_evidence
                    else:
                        first_detail = None
                        detail_evidence = ""
                    wrapped_detail = (
                        first_detail
                        if first_detail is not None
                        else decode(
                            await self.session.request(
                                detail_api,
                                payload={
                                    "orgId": self.org,
                                    "jobId": job_id,
                                    "siteId": self.site_id,
                                    "locale": payload.get("locale", "zh-CN"),
                                },
                                detail=True,
                            ),
                            iv,
                        )
                    )
                    detail = wrapped_detail["data"]
                    check(str(detail["id"]) == job_id, "Moka 详情与列表 ID 不一致")
                    check(detail.get("orgId") == self.org, "Moka 详情组织不一致")
                    self.verify_detail(row, detail)
                    job = self._job(
                        detail, row, detail_evidence or self.session.last_evidence, is_detail=True
                    )
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
            if scope.unique >= expected:
                scope.terminal = True
                break
            check(bool(rows), "Moka 分页提前为空")
            offset += len(rows)

    def _job(
        self,
        row: dict[str, Any],
        listing: dict[str, Any],
        evidence: str,
        *,
        is_detail: bool = False,
    ) -> Job:
        job_id = str(row["id"])
        description = text(row.get("jobDescription") or listing.get("jobDescription"))
        duties, requirements = sections(description)
        if is_detail and not requirements:
            self.result.warnings.append(
                Issue(
                    code="field_missing",
                    message=(
                        "源站详情没有岗位正文"
                        if not row.get("jobDescription")
                        else "源站详情无可辨认的任职要求段落"
                    ),
                    source_id=self.source.source_id,
                    job_key=job_id,
                    url=self.detail_page(job_id),
                )
            )
        locations = row.get("locations") or listing.get("locations") or []
        location, address = location_text(locations)
        dept = row.get("department") or listing.get("department") or {}
        zhineng = row.get("zhineng") or listing.get("zhineng") or {}
        commitment = text(row.get("commitment") or listing.get("commitment"))
        title = text(row.get("title") or listing.get("title"))
        work_type = (
            "实习"
            if "实习" in title
            else "兼职"
            if "兼职" in title
            else "校招"
            if commitment in {"全职", ""}
            else commitment
        )
        job = self.job(
            job_id,
            title=title,
            work_type=work_type,
            unit=text(dept.get("name")),
            category_raw=text(zhineng.get("name")),
            education=text(row.get("education")),
            location=location,
            address=address,
            duties=duties,
            requirements=requirements,
            published=text(row.get("publishedAt") or listing.get("publishedAt")),
            visible=row.get("status") == "open",
            closed=bool(row.get("closedAt")),
            source_url=self.detail_page(job_id),
            field_sources={
                "duties": (
                    "website/job.data.jobDescription"
                    if row.get("jobDescription") or listing.get("jobDescription")
                    else "source_missing:jobDescription"
                ),
                "requirements": (
                    "website/job.data.jobDescription:可见标题"
                    if requirements
                    else "source_missing:要求段落"
                ),
                "published": "website/job.data.publishedAt or jobs/v2.data.jobs[].publishedAt",
                "location": "website/job.data.locations[].provinceName/cityName",
            },
        )
        job.evidence = [evidence] if evidence else []
        return job


class CATL(Moka):
    name = "moka-catl"
    org = "catlhr"
    site_id = 142020
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Huaqin(Moka):
    name = "moka-huaqin"
    org = "hq"
    site_id = 45417
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Jinko(Moka):
    name = "moka-jinko"
    org = "jinkosolar"
    site_id = 41896
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Sungrow(Moka):
    name = "moka-sungrow"
    org = "sungrow"
    site_id = 94416
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class STO(Moka):
    name = "moka-sto"
    org = "sto"
    site_id = 126265
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Lygend(Moka):
    name = "moka-lygend"
    org = "lygend"
    site_id = 72100
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Digiloong(Moka):
    name = "moka-digiloong"
    org = "digiloong"
    site_id = 126358
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class HFSP(Moka):
    name = "moka-hfsp"
    org = "hfsp"
    site_id = 37149
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Sanhua(Moka):
    name = "moka-sanhua"
    org = "zjshc"
    site_id = 56209
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class EastchinaPharm(Moka):
    name = "moka-eastchinapharm"
    org = "eastchinapharm"
    site_id = 67935
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Yadea(Moka):
    name = "moka-yadea"
    org = "yadea"
    site_id = 26985
    route = "campus_apply"
    path = f"/{route}/{org}/{site_id}#/jobs"


class Fehorizon(Moka):
    name = "moka-fehorizon"
    org = "fehorizon01"
    site_id = 68154
    route = "campus_apply"
    path = f"/{route}/{org}/{site_id}#/jobs"


class Dasenlin(Moka):
    name = "moka-dasenlin"
    org = "dslyy"
    site_id = 136052
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Geely(Moka):
    name = "moka-geely"
    host = "campus.geely.com"
    org = "geely"
    site_id = 78436
    path = f"/campus-recruitment/{org}/{site_id}/#/jobs"

    def detail_page(self, job_id: str) -> str:
        return f"https://{self.host}/campus-recruitment/{self.org}/{self.site_id}/#/job/{job_id}"


class Chint(Moka):
    name = "moka-chint"
    host = "campus.chint.com"
    org = "chint"
    site_id = 40745
    path = f"/campus-recruitment/{org}/{site_id}/#/jobs"

    def detail_page(self, job_id: str) -> str:
        return f"https://{self.host}/campus-recruitment/{self.org}/{self.site_id}/#/job/{job_id}"


class Muyuan(Moka):
    name = "moka-muyuan"
    org = "muyuan"
    site_id = 70116
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Wens(Moka):
    name = "moka-wens"
    org = "wens"
    site_id = 92366
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class XCMG(Moka):
    name = "moka-xcmg"
    org = "xcmg"
    site_id = 148091
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class TrinaSolar(Moka):
    name = "moka-trinasolar-2027"
    org = "trinasolar"
    site_id = 126157
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "天合光能2027届公开校园门户全目录；部门与岗位标题保留原文"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(
            text(detail.get("title")) == text(listing.get("title")),
            "天合光能详情与列表标题不一致",
        )


class Anta2027(Moka):
    name = "moka-anta-2027"
    org = "antahr"
    site_id = 142914
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "安踏集团2027届公开校招全目录；品牌和业务部门保留原文"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(
            text(detail.get("title")) == text(listing.get("title")),
            "安踏详情与列表标题不一致",
        )


class Wzgroup(Moka):
    name = "moka-wzgroup"
    host = "campus.wzgroup.cn"
    org = "wzgroup"
    site_id = 41923
    route = "campus_apply"
    path = f"/{route}/{org}/{site_id}#/jobs"


class Vipshop(Moka):
    name = "moka-vipshop"
    host = "app-tc.mokahr.com"
    org = "vipshophr"
    site_id = 10039
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "唯品会官网跳转的10039、8015两公开校园门户；实习排除；源岗位ID跨门户去重"

    async def harvest(self) -> None:
        await super().harvest()
        self.site_id = 8015
        await self.session.open(
            f"https://{self.host}/{self.route}/{self.org}/{self.site_id}#/jobs",
            ready_endpoints=self.ready_endpoints,
        )
        await super().harvest()
        unique: dict[str, Job] = {}
        for job in self.result.jobs:
            if job.source_key in unique:
                first = unique[job.source_key]
                check(
                    first.title == job.title and first.duties == job.duties,
                    "唯品会跨门户岗位内容不一致",
                )
                first.evidence = list(dict.fromkeys([*first.evidence, *job.evidence]))
            else:
                unique[job.source_key] = job
        self.result.jobs = list(unique.values())


class Nongfu(Moka):
    name = "moka-nongfu"
    host = "jobs.yst.com.cn"
    org = "yst"
    site_id = 68367
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "养生堂校园共享全目录中明确隶属农夫山泉的岗位；排除其他法人和实习"

    async def harvest(self) -> None:
        observed = await self.session.observed("/api/outer/ats-apply/website/jobs/departments/flat")
        response = json.loads(observed["body"])
        check(response.get("code") == 0, "养生堂部门字典失败")
        self.departments = {str(d["id"]): str(d["label"]) for d in response["data"]}
        check(self.departments.get("1867931") == "农夫山泉股份有限公司", "农夫山泉法人字典变化")
        await super().harvest()

    def _job(
        self,
        row: dict[str, Any],
        listing: dict[str, Any],
        evidence: str,
        *,
        is_detail: bool = False,
    ) -> Job:
        dept_id = str(row.get("deptId") or listing.get("deptId") or "")
        department = (
            row.get("department")
            or listing.get("department")
            or {"id": dept_id, "name": self.departments.get(dept_id)}
        )
        row = {**row, "department": department}
        job = super()._job(row, listing, evidence, is_detail=is_detail)
        if not is_detail:
            return job
        check(bool(department.get("id") and department.get("name")), "养生堂共享门户缺少企业归属")
        if str(department["id"]) != "1867931":
            job.work_type = "非农夫山泉主体"
        else:
            check(department["name"] == "农夫山泉股份有限公司", "农夫山泉部门名称与已验证ID不符")
        return job


class Joyson(Moka):
    name = "moka-joyson"
    org = "joyson"
    site_id = 94311
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Zijin(Moka):
    name = "moka-zijin"
    host = "join.zjky.cn"
    org = "zijinmining"
    site_id = 117957
    path = f"/campus-recruitment/{org}/{site_id}/#/jobs"

    def detail_page(self, job_id: str) -> str:
        return f"https://{self.host}/campus-recruitment/{self.org}/{self.site_id}/#/job/{job_id}"


class ZTE(Moka):
    name = "moka-zte"
    org = "zte"
    site_id = 46903
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class ZhongAn(Moka):
    name = "moka-zhongan"
    org = "zhongan"
    site_id = 71908
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "众安在线 71908 公开校招；仅 2027 届秋招，排除实习、赛事和校园大使"

    def in_scope(self, row: dict[str, Any]) -> bool:
        title = text(row.get("title"))
        if title.startswith("[2027届秋招-"):
            return True
        if title.startswith("[实习可留用-") or title in {
            "众安 1024 人人节 · AI Coding 大赛参赛报名",
            "众安校园大使",
        }:
            return False
        check(False, "众安 71908 出现未知校招项目标题")
        return False

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(
            text(detail.get("title")) == text(listing.get("title")),
            "众安详情与列表标题不一致",
        )


class Hengrui(Moka):
    name = "moka-hengrui"
    org = "hengrui"
    site_id = 145997
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(
            text(detail.get("title")) == text(listing.get("title")),
            "恒瑞医药详情与列表标题不一致",
        )


class SunnyOptical(Moka):
    name = "moka-sunnyoptical-campus"
    host = "campus.sunnyoptical.cn"
    org = "sunnyoptical"
    site_id = 45602
    module_id = "0477326749"
    path = f"/campus-recruitment/{org}/{site_id}/#/"
    ready_endpoints = ("/api/outer/ats-apply/website/jobs/module",)
    scope_description = "舜宇光学官方 Moka 校园招聘全职模块 99 岗全目录"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "舜宇详情标题不匹配")


class SemidriveCampus(Moka):
    name = "moka-semidrive-campus"
    org = "semidrive"
    site_id = 42941
    route = "campus_apply"
    module_id = "0001295480"
    module_group_type = "list"
    path = f"/{route}/{org}/{site_id}#/"
    ready_endpoints = ("/api/outer/ats-apply/website/jobs/module",)
    scope_description = "芯驰科技独立 Moka 校招站全职模块完整目录；实习模块另列并排除"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "芯驰详情标题不匹配")


class EnflameCampus(Moka):
    name = "moka-enflame-campus"
    org = "enflame"
    site_id = 168420
    path = f"/campus-recruitment/{org}/{site_id}#/jobs/"
    scope_description = (
        "燧原科技独立 Moka 校园站全目录，仅纳入列表部门属于上海燧原科技股份有限公司的岗位"
    )

    def in_scope(self, row: dict[str, Any]) -> bool:
        department = row.get("department") or {}
        check(isinstance(department, dict), "燧原列表部门结构改变")
        return text(department.get("name")) == "上海燧原科技股份有限公司"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "燧原详情标题不匹配")
        check(detail.get("department") == listing.get("department"), "燧原详情主体不匹配")


class FourierCampus(Moka):
    name = "moka-fourier-campus"
    org = "fftai"
    site_id = 147078
    path = f"/campus-recruitment/{org}/{site_id}#/jobs/"
    scope_description = "傅利叶智能独立 Moka 校园站无筛选全目录；按源职位性质排除实习"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "傅利叶详情标题不匹配")


class CalterahCampus(Moka):
    name = "moka-calterah-campus"
    org = "calterah"
    site_id = 1109
    route = "campus_apply"
    module_id = "5441735827"
    module_group_type = "list"
    module_commitments = ()
    path = f"/{route}/{org}/{site_id}#/"
    ready_endpoints = ("/api/outer/ats-apply/website/jobs/module",)
    scope_description = "加特兰独立 Moka 校招模块无筛选全目录；按岗位性质排除实习"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "加特兰详情标题不匹配")


class AscenpowerCampus(Moka):
    name = "moka-ascenpower-campus"
    org = "ascenpower"
    site_id = 166280
    module_id = "6198202737"
    module_group_type = "list"
    module_commitments = ()
    path = f"/campus-recruitment/{org}/{site_id}#/"
    ready_endpoints = ("/api/outer/ats-apply/website/jobs/module",)
    scope_description = "芯粤能独立 Moka 校招模块无筛选全目录；按岗位性质排除实习"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "芯粤能详情标题不匹配")


class Seazen2027(Moka):
    name = "moka-seazen-2027"
    org = "seazen"
    site_id = 168436
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "新城集团 2027 新睿校园招聘 Moka 站点完整公开职位目录"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "新城详情标题不匹配")


class Longcheer2027(Moka):
    name = "moka-longcheer-2027"
    org = "longcheer"
    site_id = 166561
    route = "campus_apply"
    path = f"/{route}/{org}/{site_id}#/jobs"
    scope_description = "龙旗科技2027公开 Moka 校园站国内及海外校招无筛选全目录"


class Lingyi2027(Moka):
    name = "moka-lingyi-2027"
    org = "lingyiitech"
    site_id = 182049
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "领益智造官方 2027 届本硕博校园站无筛选全部职能及城市目录"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "领益智造详情标题不匹配")


class Zczl2027(Moka):
    name = "moka-zczl-2027"
    org = "zczl"
    site_id = 172433
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "中创智领官网2027届校园站全部板块、单位及城市的无筛选目录"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "中创智领详情标题不匹配")


class Hithium2027(Moka):
    name = "moka-hithium-2027"
    org = "hithium"
    site_id = 70080
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "海辰储能高校公告指向的 Moka 2027 校园站无筛选全部岗位"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "海辰储能详情标题不匹配")


class Dji2027(Moka):
    name = "moka-dji-2027"
    host = "apply.careers.dji.com"
    org = "dji"
    site_id = 143359
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "大疆官网所链白标 Moka 校园门户无筛选全目录；实习按源性质排除"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "大疆详情标题不匹配")


class Huolala2027(Moka):
    name = "moka-huolala-2027"
    org = "huolalahr"
    site_id = 98660
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "货拉拉官网所链 Moka 校园门户无筛选全目录；兼职和实习按源性质排除"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "货拉拉详情标题不匹配")


class ChintAnengCampus(Moka):
    name = "moka-chint-aneng-campus"
    host = "campus.chint.com"
    org = "chint"
    site_id = 40745
    catalog_department_id = "725411"
    path = f"/campus-recruitment/{org}/{site_id}/#/jobs?department%5B0%5D={catalog_department_id}"
    scope_description = "正泰集团官网 Moka 校园站仅正泰安能数字能源（浙江）股份有限公司分支"

    def in_scope(self, row: dict[str, Any]) -> bool:
        department = row.get("department") or {}
        check(
            str(department.get("id")) == self.catalog_department_id
            and text(department.get("name")) == "正泰安能数字能源（浙江）股份有限公司",
            "正泰安能筛选结果混入其他公司",
        )
        return True


class Aerofugia2027(Moka):
    name = "moka-aerofugia-2027"
    org = "geely"
    site_id = 94419
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "沃飞长空官网所链 Moka 独立校园站 94419 全目录；不纳入吉利其他站点"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "沃飞长空详情标题不匹配")


class Shein2027(Moka):
    name = "moka-shein-2027"
    org = "shein"
    site_id = 2932
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "SHEIN 官方 Moka 2027 校园站无筛选全目录；实习/兼职按源性质排除"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "SHEIN 详情标题不匹配")


class Stepfun2027(Moka):
    name = "moka-stepfun-2027"
    org = "step"
    site_id = 94905
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "阶跃星辰 2027 Moka 校园站无筛选全目录；实习与正式按源性质区分"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "阶跃星辰详情标题不匹配")


class Smartmore2027(Moka):
    name = "moka-smartmore-2027"
    org = "smartmore"
    site_id = 40506
    route = "campus_apply"
    path = f"/{route}/{org}/{site_id}#/jobs"
    scope_description = "思谋科技 2027 Moka 校园站无筛选全目录；以源码性质排除实习"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "思谋科技详情标题不匹配")


class EnvisionEnergy2027(Moka):
    name = "moka-envision-energy-2027"
    org = "envisiongroup"
    site_id = 43123
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "远景集团 Moka 2027 校园全目录仅纳入 department.id=958964 远景能源；其他事业部逐条核对后排除"
    department_id = "958964"
    department_name = "远景能源"

    def in_scope(self, row: dict[str, Any]) -> bool:
        department = row.get("department") or {}
        check(
            isinstance(department, dict) and bool(department.get("id")),
            "远景集团岗位缺少事业部身份",
        )
        return (
            str(department["id"]) == self.department_id
            and text(department.get("name")) == self.department_name
        )

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "远景集团详情标题不匹配")
        check(detail.get("department") == listing.get("department"), "远景集团详情事业部不匹配")


class EnvisionDigital2027(EnvisionEnergy2027):
    name = "moka-envision-digital-2027"
    scope_description = "远景集团 Moka 2027 校园全目录仅纳入 department.id=958965 远景智能；其他事业部逐条核对后排除"
    department_id = "958965"
    department_name = "远景智能"


class Galbot2027(Moka):
    name = "moka-galbot-2027"
    org = "yinhetongyong"
    site_id = 165930
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "银河通用机器人2027校园站全目录；按源职位性质排除日常实习"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "银河通用详情标题不一致")


class Yunshenchu2027(Moka):
    name = "moka-yunshenchu-2027"
    host = "app135149.eapps.dingtalkcloud.com"
    org = "yunshenchu"
    site_id = 100000136
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "云深处 2027 白标 Moka 校园门户无筛选全目录；按性质排除实习"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "云深处详情标题不一致")


class Deeproute2027(Moka):
    name = "moka-deeproute-2027"
    org = "deeproute"
    site_id = 145894
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "元戎启行 2027 秋招 Moka 校园站无筛选全目录；按性质排除实习"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "元戎启行详情标题不一致")


class Webank2027(Moka):
    name = "moka-webank-2027"
    host = "app-tc.mokahr.com"
    org = "webankhr"
    site_id = 20060
    path = f"/campus-recruitment/{org}/{site_id}?locale=zh-CN#/jobs"
    scope_description = "微众银行 2027 届官方 Moka 校园站无筛选公开全目录"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "微众银行详情标题不一致")


class BgyfwCampus(Moka):
    name = "moka-bgyfw-campus"
    org = "bgyfw"
    site_id = 47073
    path = f"/campus-recruitment/{org}/{site_id}/#/jobs"
    scope_description = "碧桂园服务官网直链 Moka 校园站无筛选目录；排除校园大使与实习"

    def in_scope(self, row: dict[str, Any]) -> bool:
        return "校园大使" not in text(row.get("title"))

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "碧桂园服务详情标题不一致")


class SinaCampus(Moka):
    name = "moka-sina-campus"
    org = "sina"
    site_id = 43536
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "新浪与微博共同校园招聘 Moka 公开无筛选目录；保留源部门，排除实习"


class Gaotu2027(Moka):
    name = "moka-gaotu-2027"
    org = "bjhl"
    site_id = 102145
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "高途 Moka 2027 校园站公开无筛选全目录；正式岗位和实习依源性质区分"

    def in_scope(self, row: dict[str, Any]) -> bool:
        title = text(row.get("title"))
        return "2027" in title or "27届" in title or "27秋" in title


class Kfconcept2027(Moka):
    name = "moka-kfconcept-2027"
    org = "kfconcept"
    site_id = 144795
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "卓尔摄影器材 Moka 2027 校园站公开无筛选全目录"


class Zhihu2027(Moka):
    name = "moka-zhihu-2027"
    org = "zhihu"
    site_id = 68321
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "知乎 Moka 公开校招全目录；只纳入明确 27 届正式校招，实习排除"

    def in_scope(self, row: dict[str, Any]) -> bool:
        title = text(row.get("title"))
        return "27届" in title or "2027" in title


class Vertiv2027(Moka):
    name = "moka-vertiv-2027"
    org = "vertiv"
    site_id = 118713
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "维谛技术 Moka 2027 校园站无筛选全目录；保留实际来源部门"


class Visionox2027(Moka):
    name = "moka-visionox-2027"
    org = "newvisionox"
    site_id = 24735
    route = "campus_apply"
    path = f"/campus_apply/{org}/{site_id}/#/jobs"
    scope_description = "维信诺 Moka 校园站 27 届正式岗位全目录；排除实习、校园大使与旧批次"

    def in_scope(self, row: dict[str, Any]) -> bool:
        title = text(row.get("title"))
        return ("27届" in title or "2027" in title) and "校园大使" not in title


class Voyah2027(Moka):
    name = "moka-voyah-2027"
    org = "voyah"
    site_id = 146293
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "岚图汽车 2027 校招与博士项目公开全目录；实习项目按岗位性质排除"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "岚图详情标题不匹配")


class ShanghaiHuali2027(Moka):
    name = "moka-shanghai-huali-2027"
    org = "huahong"
    site_id = 70000
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "上海华力品牌官方 Moka 2027 校园站无筛选全目录；不归作华虹集团岗位"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "上海华力详情标题不匹配")


class Deli2027(Moka):
    name = "moka-deli-2027"
    org = "nbdeli"
    site_id = 70019
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "得力集团官网 2027 校园招聘 Moka 站点无筛选完整目录；实习按源性质排除"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "得力详情标题不匹配")


class Ruijie2027(Moka):
    name = "moka-ruijie-2027"
    org = "ruijie"
    site_id = 136206
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "锐捷网络官网 2027 校园招聘 Moka 站点无筛选完整目录；实习按源性质排除"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "锐捷详情标题不匹配")


class Crland2027(Moka):
    name = "moka-crland-2027"
    org = "crland"
    site_id = 168540
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "华润置地公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"


class DongfengGufen2027(Moka):
    name = "moka-gufen-2027"
    org = "gufen"
    site_id = 143531
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "东风汽车股份有限公司公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"


class Supcon2027(Moka):
    name = "moka-supcon-2027"
    org = "supcon"
    site_id = 172631
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "中控技术公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"


class Threatbook2027(Moka):
    name = "moka-threatbook-2027"
    org = "threatbook"
    site_id = 39679
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "微步在线公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"

    def in_scope(self, row: dict[str, Any]) -> bool:
        title = text(row.get("title"))
        return "2027" in title or "27届" in title or "27秋" in title or "2027校招" in title


class Manbang2027(Moka):
    name = "moka-manbang-2027"
    org = "manbang"
    site_id = 94191
    route = "campus_apply"
    path = f"/campus_apply/{org}/{site_id}#/jobs"
    scope_description = "满帮集团公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"


class Tuyoo2027(Moka):
    name = "moka-tuyoogame-2027"
    org = "tuyoogame"
    site_id = 146219
    route = "campus_apply"
    path = f"/campus_apply/{org}/{site_id}#/jobs"
    scope_description = "途游游戏公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"

    def in_scope(self, row: dict[str, Any]) -> bool:
        title = text(row.get("title"))
        return "2027" in title or "27届" in title or "27秋" in title or "2027校招" in title


class Didi2027(Moka):
    name = "moka-didiglobal-2027"
    org = "didiglobal"
    site_id = 96064
    route = "campus_apply"
    path = f"/campus_apply/{org}/{site_id}#/jobs"
    scope_description = "滴滴出行公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"

    def in_scope(self, row: dict[str, Any]) -> bool:
        title = text(row.get("title"))
        return "2027" in title or "27届" in title or "27秋" in title or "2027校招" in title


class Qianli2027(Moka):
    name = "moka-qianli1-2027"
    org = "qianli1"
    site_id = 147197
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "千里智驾公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"


class Gtx2027(Moka):
    name = "moka-gtx-2027"
    org = "gtx"
    site_id = 102188
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "上海光通信有限公司公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"

    def in_scope(self, row: dict[str, Any]) -> bool:
        title = text(row.get("title"))
        return "2027" in title or "27届" in title or "27秋" in title or "2027校招" in title


class Easpring2027(Moka):
    name = "moka-easpring-2027"
    org = "easpring"
    site_id = 102152
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "当升科技公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"


class Wison2027(Moka):
    name = "moka-wison-2027"
    org = "wison"
    site_id = 115998
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "惠生工程公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"

    def in_scope(self, row: dict[str, Any]) -> bool:
        title = text(row.get("title"))
        return "2027" in title or "27届" in title or "27秋" in title or "2027校招" in title


class Kingdee2027(Moka):
    name = "moka-kingdeehr-2027"
    org = "kingdeehr"
    site_id = 166565
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "金蝶公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"


class Pwrd2027(Moka):
    name = "moka-pwrd-2027"
    org = "pwrd"
    site_id = 172467
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "完美世界公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"

    def in_scope(self, row: dict[str, Any]) -> bool:
        title = text(row.get("title"))
        return "2027" in title or "27届" in title or "27秋" in title or "2027校招" in title


class Hypergryph2027(Moka):
    name = "moka-hypergryph-2027"
    org = "hypergryph"
    site_id = 26326
    route = "campus_apply"
    path = f"/campus_apply/{org}/{site_id}#/jobs"
    scope_description = "鹰角网络公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"


class Amec2027(Moka):
    name = "moka-amec-2027"
    org = "amec"
    site_id = 4362
    route = "campus_apply"
    path = f"/campus_apply/{org}/{site_id}#/jobs"
    scope_description = "中微公司公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"

    def in_scope(self, row: dict[str, Any]) -> bool:
        title = text(row.get("title"))
        return "2027" in title or "27届" in title or "27秋" in title or "2027校招" in title


class Tsinghuaic2027(Moka):
    name = "moka-tsinghuaic-2027"
    org = "tsinghuaic"
    site_id = 39656
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "紫光同芯微电子有限公司公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"

    def in_scope(self, row: dict[str, Any]) -> bool:
        title = text(row.get("title"))
        return "2027" in title or "27届" in title or "27秋" in title or "2027校招" in title


class Pharmaron2027(Moka):
    name = "moka-pharmaron-2027"
    org = "pharmaron"
    site_id = 45318
    route = "campus_apply"
    path = f"/campus_apply/{org}/{site_id}#/jobs"
    scope_description = "康龙化成公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"

    def in_scope(self, row: dict[str, Any]) -> bool:
        title = text(row.get("title"))
        return "2027" in title or "27届" in title or "27秋" in title or "2027校招" in title


class Dhrobotics2027(Moka):
    name = "moka-dhrobotics-2027"
    org = "dhrobotics"
    site_id = 168695
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = (
        "深圳市大寰机器人科技有限公司公开 Moka 校园站无筛选全目录；实习与非当届岗位排除"
    )


class Sineng2027(Moka):
    name = "moka-sineng-2027"
    org = "sineng"
    site_id = 172108
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "上能电气 2027 校园站公开无筛选全目录；按源性质排除实习"


class Sanqi2027(Moka):
    name = "moka-37-2027"
    org = "37"
    site_id = 58016
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"
    scope_description = "三七互娱 2027 校园站公开无筛选全目录；按源性质排除实习"


TENANTS = (
    Sineng2027,
    Sanqi2027,
    Crland2027,
    DongfengGufen2027,
    Supcon2027,
    Threatbook2027,
    Manbang2027,
    Tuyoo2027,
    Didi2027,
    Qianli2027,
    Gtx2027,
    Easpring2027,
    Wison2027,
    Kingdee2027,
    Pwrd2027,
    Hypergryph2027,
    Amec2027,
    Tsinghuaic2027,
    Pharmaron2027,
    Dhrobotics2027,
    Gaotu2027,
    SinaCampus,
    Kfconcept2027,
    Zhihu2027,
    Vertiv2027,
    Visionox2027,
    Voyah2027,
    ShanghaiHuali2027,
    Deli2027,
    Ruijie2027,
    BgyfwCampus,
    Webank2027,
    CalterahCampus,
    AscenpowerCampus,
    FourierCampus,
    EnflameCampus,
    SemidriveCampus,
    ChintAnengCampus,
    Aerofugia2027,
    Dji2027,
    Huolala2027,
    EnvisionDigital2027,
    EnvisionEnergy2027,
    Galbot2027,
    Yunshenchu2027,
    Deeproute2027,
    Smartmore2027,
    Stepfun2027,
    Shein2027,
    Hithium2027,
    Zczl2027,
    Lingyi2027,
    Longcheer2027,
    Seazen2027,
    SunnyOptical,
    Hengrui,
    Anta2027,
    TrinaSolar,
    ZhongAn,
    Zijin,
    ZTE,
    Wzgroup,
    Vipshop,
    Nongfu,
    Joyson,
    CATL,
    Huaqin,
    Jinko,
    Sungrow,
    STO,
    Lygend,
    Digiloong,
    HFSP,
    Sanhua,
    EastchinaPharm,
    Yadea,
    Fehorizon,
    Dasenlin,
    Geely,
    Chint,
    Muyuan,
    Wens,
    XCMG,
)
