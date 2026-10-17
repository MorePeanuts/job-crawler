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
            check(payload.get("commitments") == ["全职"], "Moka 招聘模块不是正式岗位")
            check(payload.get("needGroupType") == "zhineng", "Moka 招聘模块类别改变")
        else:
            check(payload.get("site") == "campus", "Moka 入口不是校园站点")
        check(int(payload.get("offset", -1)) == 0, "Moka 列表不是第一页")
        check(
            not payload.get("jobIdTopList") and not payload.get("customFields"), "Moka 目录带有筛选"
        )
        for key in ("keyword", "locations", "zhineng", "commitment", "departmentIds"):
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


TENANTS = (
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
