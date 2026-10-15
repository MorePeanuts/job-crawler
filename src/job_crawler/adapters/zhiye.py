"""Explicit Beisen tenants sharing a verified public campus API contract."""

import asyncio
import json
from typing import Any
from urllib.parse import urlencode

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Job, Scope
from job_crawler.transport import CrawlError


def date_text(value: Any) -> str:
    value = text(value)
    return "" if value.startswith(("0001-01-01", "2222-02-02")) else value


class Zhiye(Adapter):
    path = "/campus/jobs"
    mixed_catalog = False
    detail_path = "/campus/detail"
    regular_only = False
    listing_complete = False
    listing_unit_field = "Org"
    expected_org = ""
    page_size = 20
    ready_endpoints = ("/api/Jobad/GetJobAdPageList",)
    scope_description = "北森公开校园招聘 Category=2 全目录；保留实际租户/门户范围，不含社招和实习"

    def detail_page(self, job_id: str) -> str:
        return f"https://{self.host}{self.detail_path}?{urlencode({'jobAdId': job_id})}"

    def in_scope(self, row: dict[str, Any]) -> bool:
        return True

    async def harvest(self) -> None:
        observed = await self.session.observed("/api/Jobad/GetJobAdPageList")
        payload = json.loads(observed["post_data"])
        if self.mixed_catalog:
            check(
                not payload.get("Category")
                and payload.get("SpecialType") == 0
                and payload.get("PortalId") == "",
                "北森混合目录初始筛选异常",
            )
            payload["Category"] = ["2"]
        else:
            check([str(v) for v in payload.get("Category", [])] == ["2"], "不是校招 Category=2")
        check(not payload.get("KeyWords"), "校招目录仍有关键词筛选")
        for key in (
            "LocId",
            "ClassificationOne",
            "ClassificationTwo",
            "Classification3",
            "Classification4",
            "Classification5",
            "Classification6",
        ):
            check(not payload.get(key), f"目录仍有局部筛选 {key}，需接入完整入口")
        scope = Scope(name="campus-category-2")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 0
        size = max(self.page_size, int(payload["PageSize"]))
        detail_url = ""
        limit = asyncio.Semaphore(3)
        detail_lock = asyncio.Lock()
        list_evidence = ""
        abort: CrawlError | None = None

        async def read_job(listed: dict[str, Any]) -> Job | None:
            nonlocal abort
            async with limit:
                if abort is not None:
                    return None
                try:
                    if self.expected_org and (self.listing_complete or listed.get("Org")):
                        check(
                            text(listed.get("Org")) == self.expected_org,
                            "列表岗位所属法人与名录主体不一致",
                        )
                    listing = self.job(
                        str(listed["Id"]),
                        title=text(listed.get("JobAdName")),
                        source_url=self.detail_page(str(listed["Id"])),
                        published=date_text(listed.get("PostDate")),
                        deadline=date_text(listed.get("EndTime")),
                    )
                    listing.evidence = [list_evidence] if list_evidence else []
                    if self.listing_complete:
                        check(str(listed.get("CategoryId")) == "2", "列表岗位混入非校招类别")
                        check("Duty" in listed and "Require" in listed, "列表不再包含完整正文")
                        job = self.job(
                            str(listed["Id"]),
                            title=text(listed["JobAdName"]),
                            work_type=(
                                "实习"
                                if self.regular_only
                                and (
                                    "实习" in text(listed.get("Kind"))
                                    or "实习" in text(listed["JobAdName"])
                                )
                                else "校招"
                            ),
                            source_url=self.detail_page(str(listed["Id"])),
                            unit=text(listed.get(self.listing_unit_field)),
                            location=text(listed.get("LocNames")),
                            education=text(listed.get("Degree")),
                            address=text(listed.get("DetailAddress")),
                            category_raw=text(listed.get("ClassificationOne")),
                            duties=text(listed["Duty"]),
                            requirements=text(listed["Require"]),
                            published=date_text(listed.get("PostDate")),
                            deadline=date_text(listed.get("EndTime")),
                            field_sources={
                                "duties": "GetJobAdPageList.Data[].Duty",
                                "requirements": "GetJobAdPageList.Data[].Require",
                                "published": "PostDate；0001 哨兵为空",
                                "deadline": "EndTime；0001 哨兵为空",
                            },
                        )
                        job.evidence = [list_evidence] if list_evidence else []
                        scope.details += 1
                        return job
                    resolved = self.before_detail(
                        f"job:{listed['Id']}",
                        listed,
                        scope,
                        listing,
                        evidence=list_evidence,
                    )
                    if resolved is not None:
                        return resolved[0]
                    await ensure_detail(listed)
                    data = await self.session.request(
                        query(detail_url, jobAdId=listed["Id"]), detail=True
                    )
                    check(data.get("Code") == 200, "北森详情业务失败")
                    row = data["Data"]
                    check(str(row["Id"]) == str(listed["Id"]), "北森详情与列表 ID 不一致")
                    if self.expected_org:
                        check(
                            text(row.get("Org")) == self.expected_org,
                            "北森详情所属法人与名录主体不一致",
                        )
                    check(str(row["CategoryId"]) == "2", "岗位混入非校招类别")
                    check(bool(row["JobAdName"]), "岗位名称为空")
                    check("Duty" in row and "Require" in row, "详情不再包含职位描述")
                    job = self.job(
                        str(row["Id"]),
                        title=text(row["JobAdName"]),
                        work_type=(
                            "实习"
                            if self.regular_only
                            and (
                                "实习" in text(row.get("Kind")) or "实习" in text(row["JobAdName"])
                            )
                            else "校招"
                        ),
                        source_url=self.detail_page(str(row["Id"])),
                        unit=text(row.get("Org") or listed.get("Org")),
                        location=text(row.get("LocNames") or listed.get("LocNames")),
                        education=text(row.get("Degree") or listed.get("Degree")),
                        address=text(row.get("DetailAddress")),
                        category_raw=text(
                            row.get("ClassificationOne") or listed.get("ClassificationOne")
                        ),
                        duties=text(row["Duty"]),
                        requirements=text(row["Require"]),
                        published=date_text(row.get("PostDate"))
                        or date_text(listed.get("PostDate")),
                        deadline=date_text(row.get("EndTime")) or date_text(listed.get("EndTime")),
                        field_sources={
                            "duties": "GetJobAdInfo.Data.Duty",
                            "requirements": "GetJobAdInfo.Data.Require",
                            "published": "PostDate；0001 哨兵为空",
                            "deadline": "EndTime；0001 哨兵为空",
                        },
                    )
                    scope.details += 1
                    self.remember(f"job:{listed['Id']}", listed, [job])
                    return job
                except Exception as exc:
                    self.error(exc, str(listed.get("Id", "")))
                    if isinstance(exc, CrawlError) and exc.code in {
                        "access_denied",
                        "request_budget",
                        "time_budget",
                    }:
                        abort = exc
                    return None

        async def ensure_detail(listed: dict[str, Any]) -> None:
            nonlocal detail_url
            async with detail_lock:
                if not detail_url:
                    await self.session.open(
                        self.detail_page(str(listed["Id"])),
                        ready_endpoints=("/api/JobAd/GetJobAdInfo?",),
                    )
                    detail_url = (await self.session.observed("/api/JobAd/GetJobAdInfo?"))["url"]

        while True:
            result = await self.session.request(
                observed["url"], payload={**payload, "PageIndex": page, "PageSize": size}
            )
            check(result.get("Code") == 200, "北森列表业务失败")
            expected = int(result["Count"])
            check(expected >= 0, "北森目录总数无效")
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "北森目录总数变化")
            rows = self.add_page(scope, result["Data"], seen, lambda row: str(row["Id"]))
            list_evidence = self.session.last_evidence
            included = []
            for row in rows:
                if self.in_scope(row):
                    included.append(row)
                else:
                    scope.skipped_out_of_scope += 1
            jobs = await asyncio.gather(*(read_job(row) for row in included))
            self.result.jobs.extend(job for job in jobs if job is not None)
            if abort is not None:
                raise abort
            if scope.unique >= expected:
                scope.terminal = True
                break
            check(bool(rows), "北森分页提前为空")
            page += 1


class Poly(Zhiye):
    name = "zhiye-poly"
    host = "polycareer.zhiye.com"


class Mxbc2027(Zhiye):
    name = "zhiye-mxbc-2027"
    host = "careers.mxbc.com"
    listing_complete = True
    scope_description = "蜜雪集团2027届公开校园招聘 Category=2 全目录；实际招聘单位未公开时留空"


class GenertecCampus(Zhiye):
    name = "zhiye-genertec-campus"
    host = "genertec.zhiye.com"
    listing_complete = True
    scope_description = "通用技术集团公开校园招聘 Category=2 全目录；实际招聘单位未公开时留空"


class Sph2027(Zhiye):
    name = "zhiye-sph-2027"
    host = "sph.zhiye.com"
    listing_complete = True
    scope_description = "上海医药2027秋季校园招聘 Category=2 全目录；保留逐岗实际招聘单位"


class Zhenshi2027(Zhiye):
    name = "zhiye-zhenshi-2027"
    host = "zhenshigroup.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "振石控股集团2027届公开校园招聘 Category=2 全目录；源未给实际招聘法人时留空"


class Xiangyu(Zhiye):
    name = "zhiye-xiangyu"
    host = "xiangyu.zhiye.com"


class Changan(Zhiye):
    name = "zhiye-changan"
    host = "changanqiche.zhiye.com"
    path = "/campus/"


class DigitalChina(Zhiye):
    name = "zhiye-digitalchina"
    host = "digitalchina.zhiye.com"


class Bosc(Zhiye):
    name = "zhiye-bosc"
    host = "bosc.zhiye.com"


class Sinotrans(Zhiye):
    name = "zhiye-sinotrans"
    host = "sinotrans.zhiye.com"
    path = "/campus"


class Sany(Zhiye):
    name = "zhiye-sany"
    host = "sany.zhiye.com"


class Transsion(Zhiye):
    name = "zhiye-transsion"
    host = "transsion.zhiye.com"


class Bocd(Zhiye):
    name = "zhiye-bocd"
    host = "bocd.zhiye.com"


class Cscb(Zhiye):
    name = "zhiye-cscb"
    host = "cscb.zhiye.com"


class Dsbj(Zhiye):
    name = "zhiye-dsbj"
    host = "dsbj.zhiye.com"


class Sailun(Zhiye):
    name = "zhiye-sailun"
    host = "sailuntire.zhiye.com"


class Csc108(Zhiye):
    name = "zhiye-csc108"
    host = "csc108.zhiye.com"


class Tsingtao(Zhiye):
    name = "zhiye-tsingtao"
    host = "tsingtao.zhiye.com"


class Yuhong(Zhiye):
    name = "zhiye-yuhong"
    host = "yuhongzp.zhiye.com"


class Iflytek(Zhiye):
    name = "zhiye-iflytek"
    host = "iflytek.zhiye.com"


class Goldwind(Zhiye):
    name = "zhiye-goldwind"
    host = "goldwind.zhiye.com"


class Mengniu(Zhiye):
    name = "zhiye-mengniu"
    host = "mengniu.zhiye.com"


class Leapmotor(Zhiye):
    name = "zhiye-leapmotor"
    host = "leapmotor.zhiye.com"


class Mywind(Zhiye):
    name = "zhiye-mywind"
    host = "mywind.zhiye.com"


class Popmart(Zhiye):
    name = "zhiye-popmart"
    host = "popmart.zhiye.com"


class Szgas(Zhiye):
    name = "zhiye-szgas"
    host = "szgas.zhiye.com"


class Ovt(Zhiye):
    name = "zhiye-ovt"
    host = "ovt-omnivision.zhiye.com"


class Juhua(Zhiye):
    name = "zhiye-juhua"
    host = "juhua.zhiye.com"


class NewHope(Zhiye):
    name = "zhiye-newhope"
    host = "newhope.zhiye.com"


class CNAF(Zhiye):
    name = "zhiye-cnaf"
    host = "cnaf.zhiye.com"


class Greentown(Zhiye):
    name = "zhiye-gtgroup"
    host = "gtgroup.zhiye.com"


class BankOfBeijing(Zhiye):
    name = "zhiye-bankofbeijing"
    host = "bankofbeijing.zhiye.com"


class ENN(Zhiye):
    name = "zhiye-enn"
    host = "enn.zhiye.com"


class Beike(Zhiye):
    name = "zhiye-ke"
    host = "ke.zhiye.com"


class SMIC(Zhiye):
    name = "zhiye-smics"
    host = "smics.zhiye.com"


class Sunwoda(Zhiye):
    name = "zhiye-sunwoda"
    host = "sunwodacampus.zhiye.com"


class ZhongyuanBank(Zhiye):
    name = "zhiye-zybank"
    host = "zybank.zhiye.com"


class Vital(Zhiye):
    name = "zhiye-vital"
    host = "vital.zhiye.com"


class WuxiApptec(Zhiye):
    name = "zhiye-wuxiapptec-2027"
    host = "wuxiapptec.zhiye.com"
    listing_complete = True
    regular_only = True
    page_size = 100
    scope_description = "药明康德现用北森 Category=2 校招目录；仅 2027 届，未公开逐岗法人名称"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "药明康德目录混入非校招类别")
        return text(row.get("JobAdName")).startswith("2027届")


class WeichaiPower2027(Zhiye):
    name = "zhiye-weichai-power-2027"
    host = "weichai.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = (
        "潍柴动力2027招聘入口北森 Category=2 全目录；多个 OrgId 无公开法人名，单位留空"
    )


class Ctf2027(Zhiye):
    name = "zhiye-ctf-2027"
    host = "hr.ctf.com.cn"
    listing_complete = True
    regular_only = True
    scope_description = "周大福2027校招北森 Category=2 全目录；无逐岗法人名称，单位留空"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(
            str(row.get("OrgId")) == "34100" and "周大福" in text(row.get("JobAdName")),
            "周大福校招组织或品牌改变",
        )
        return True


class Gotion(Zhiye):
    name = "zhiye-gotion"
    host = "gotion.zhiye.com"
    path = "/jobs"
    mixed_catalog = True
    scope_description = "国轩高科 /jobs 混合目录，经 Category=2 过滤的全部校招岗位"


class CALB(Zhiye):
    name = "zhiye-calb"
    host = "calbjs.zhiye.com"


class CICC(Zhiye):
    regular_only = True
    name = "zhiye-cicc"
    host = "cicc.zhiye.com"
    path = "/custom/campus?hideMenu=1"
    detail_path = "/custom/campusxq"


class Jiangling(Zhiye):
    name = "zhiye-jmc"
    host = "jmc.zhiye.com"


class Avary(Zhiye):
    name = "zhiye-avary"
    host = "avaryholding.zhiye.com"


class ChinaStock(Zhiye):
    regular_only = True
    name = "zhiye-chinastock"
    host = "chinastock.zhiye.com"
    path = "/custom/campus"
    detail_path = "/custom/campusxq"


class AUX(Zhiye):
    name = "zhiye-aux"
    host = "auxgroup.zhiye.com"


class Baic(Zhiye):
    regular_only = True
    name = "zhiye-baic"
    host = "baicgroup.zhiye.com"


class Naura(Zhiye):
    regular_only = True
    name = "zhiye-naura"
    host = "career.naura.com"


class Dahua(Zhiye):
    name = "zhiye-dahua"
    host = "dahua.zhiye.com"
    regular_only = True


class Mindray(Zhiye):
    name = "zhiye-mindray"
    host = "career.mindray.com"
    listing_complete = True
    regular_only = True
    scope_description = (
        "迈瑞公开 Category=2 全校园目录，列表提供职责与任职要求；含博士校招，不含实习"
    )


class Shenzhou(Zhiye):
    name = "zhiye-shenzhou"
    host = "career.shenzhouintl.com"
    listing_complete = True
    regular_only = True
    scope_description = "申洲国际公开 Category=2 全校园目录，列表提供职责与任职要求；不含社招和实习"


class LuzhouLaojiao(Zhiye):
    name = "zhiye-luzhou-laojiao"
    host = "job.lzlj.com"
    listing_complete = True
    regular_only = True
    expected_org = "泸州老窖股份有限公司"
    scope_description = (
        "泸州老窖 Category=2 校园目录中 Org 精确匹配股份公司的全部岗位；不含其他法人"
    )


class Huafeng(Zhiye):
    name = "zhiye-huafeng"
    host = "huafeng.zhiye.com"
    path = "/campus"
    listing_complete = True
    regular_only = True
    scope_description = "华峰集团 2027 校招门户 Category=2 无筛选全目录；列表提供完整职责与要求"


class Infore(Zhiye):
    name = "zhiye-infore"
    host = "recruit.infore.com"
    listing_complete = True
    regular_only = True
    scope_description = "盈峰集团招聘门户 Category=2 无筛选校园全目录；实习由公共筛选排除"


class Seres(Zhiye):
    name = "zhiye-seres"
    host = "sokon.zhiye.com"
    listing_complete = True
    scope_description = "赛力斯集团独立 Category=2 正式校招全目录；可实习不等同实习岗位"


class Shrcb(Zhiye):
    name = "zhiye-shrcb"
    host = "shrcb.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "上海农商银行 Category=2 校园目录；长江金租独立入口不纳入本行"


class Haid(Zhiye):
    name = "zhiye-haid"
    host = "haid1.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "海大集团 2027 Category=2 校园全目录；保留业务板块和实际来源字段"


class Chery(Zhiye):
    name = "zhiye-chery"
    host = "chery.zhiye.com"
    listing_complete = True
    regular_only = True
    page_size = 200
    scope_description = "奇瑞汽车北森 Category=2 无筛选目录；仅 OrgId=886961 的奇瑞汽车股份校招"

    def in_scope(self, row: dict[str, Any]) -> bool:
        name = text(row.get("Org"))
        org_id = str(row.get("OrgId"))
        if name == "奇瑞汽车股份（校招）" or org_id == "886961":
            check(
                name == "奇瑞汽车股份（校招）" and org_id == "886961",
                "奇瑞汽车本部组织名称和编码不匹配",
            )
            check(str(row.get("CategoryId")) == "2", "奇瑞本部岗位混入非校招类别")
            check(text(row.get("Kind")) == "全职", "奇瑞本部岗位混入非全职")
            return True
        return False


class PICCGroup(Zhiye):
    name = "zhiye-picc-group"
    host = "picc.zhiye.com"
    path = "/custom/campus?hideAll=true"
    listing_complete = True
    regular_only = True
    page_size = 200
    expected_org = "中国人民保险集团股份有限公司"
    scope_description = "中国人保 Category=2 共享目录；仅 OrgId=45182 的集团股份公司本级"

    def detail_page(self, job_id: str) -> str:
        return f"https://{self.host}{self.path}"

    def in_scope(self, row: dict[str, Any]) -> bool:
        name = text(row.get("Org"))
        org_id = str(row.get("OrgId"))
        if name == self.expected_org or org_id == "45182":
            check(name == self.expected_org and org_id == "45182", "人保集团本级机构编码不匹配")
            check(str(row.get("CategoryId")) == "2", "人保集团本级混入非校招类别")
            check(text(row.get("Kind")) == "全职", "人保集团本级混入非全职岗位")
            check("2027届校招" in text(row.get("JobAdName")), "人保集团本级出现未知项目")
            return True
        return False


class ChinaLifeGroup(Zhiye):
    name = "zhiye-chinalife-group"
    host = "chinalife.zhiye.com"
    path = "/custom/campus?hideMenu=1"
    listing_complete = True
    regular_only = True
    page_size = 200
    expected_org = "中国人寿保险（集团）公司"
    scope_description = "中国人寿 Category=2 共享目录；仅 OrgId=3389294 的集团公司本级"

    def detail_page(self, job_id: str) -> str:
        return f"https://{self.host}{self.path}"

    def in_scope(self, row: dict[str, Any]) -> bool:
        name = text(row.get("Org"))
        org_id = str(row.get("OrgId"))
        if name == self.expected_org or org_id == "3389294":
            check(name == self.expected_org and org_id == "3389294", "国寿集团本级机构编码不匹配")
            check(str(row.get("CategoryId")) == "2", "国寿集团本级混入非校招类别")
            check(text(row.get("Kind")) == "全职", "国寿集团本级混入非全职岗位")
            check(
                text(row.get("PostDate")).startswith("2026-09-"),
                "国寿集团本级岗位不属于已验证的 2027 秋招发布时间范围",
            )
            return True
        return False


class YuntianhuaParent(Zhiye):
    name = "zhiye-yuntianhua-parent"
    host = "yythzb3.zhiye.com"
    listing_complete = True
    regular_only = True
    page_size = 200
    scope_description = "云天化 Category=2 共享目录；仅 OrgId=4022958 的云天化股份本部"

    def in_scope(self, row: dict[str, Any]) -> bool:
        name = text(row.get("ClassificationTwo"))
        org_id = str(row.get("OrgId"))
        parent = "云南云天化股份有限公司本部"
        if name == parent or org_id == "4022958":
            check(name == parent and org_id == "4022958", "云天化股份本部机构编码不匹配")
            check(str(row.get("CategoryId")) == "2", "云天化股份本部混入非校招类别")
            check(text(row.get("Kind")) == "全职", "云天化股份本部混入非全职岗位")
            check(
                text(row.get("PostDate")).startswith("2026-09-"),
                "云天化股份本部岗位不属于已验证的 2027 秋招发布时间范围",
            )
            row["Org"] = name
            return True
        return False


class CmhkParent(Zhiye):
    name = "zhiye-cmhk-parent"
    host = "cmhk.zhiye.com"
    page_size = 200
    expected_org = "招商局能源运输股份有限公司"
    scope_description = (
        "招商局集团 Category=2 共享目录；仅详情 OrgId=748690 的招商局能源运输股份本级"
    )

    def in_scope(self, row: dict[str, Any]) -> bool:
        name = text(row.get("Org"))
        org_id = str(row.get("OrgId"))
        if name == self.expected_org or org_id == "748690":
            check(org_id == "748690", "招商轮船本级机构编码不匹配")
            check(not name or name == self.expected_org, "招商轮船本级列表机构名称不匹配")
            check(str(row.get("CategoryId")) == "2", "招商轮船本级混入非校招类别")
            check(text(row.get("Kind")) == "全职", "招商轮船本级混入非全职岗位")
            check("2027届" in text(row.get("JobAdName")), "招商轮船本级出现未知校招项目")
            return True
        return False


class Cinda2027(Zhiye):
    name = "zhiye-cinda-2027"
    host = "cinda.zhiye.com"
    listing_complete = True
    listing_unit_field = "ClassificationTwo"
    scope_description = (
        "中国信达2027年度校招 Category=2 全目录；官方公告及附件列出总部、后援中心和分公司"
    )

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "中国信达目录混入非校招类别")
        unit = text(row.get("ClassificationTwo"))
        check(
            bool(row.get("OrgId"))
            and (unit in {"信达总部", "总部", "后援中心"} or unit.endswith("分公司")),
            "中国信达招聘机构超出公告总部、后援中心及分公司范围",
        )
        published = date_text(row.get("PostDate"))
        check(bool(published), "中国信达岗位缺少源发布日期")
        return published[:10] >= "2026-10-09"


class Vanchen2027(Zhiye):
    name = "zhiye-vanchen-2027"
    host = "vanchen1.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "万辰集团 2027 校招北森 Category=2 全目录；总部与好想来原文保留"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "万辰校招目录混入非校招类别")
        check(text(row.get("Kind")) in {"全职", "实习"}, "万辰校招岗位类型改变")
        return True


TENANTS = (
    Vanchen2027,
    Mxbc2027,
    GenertecCampus,
    Sph2027,
    Zhenshi2027,
    Cinda2027,
    CmhkParent,
    YuntianhuaParent,
    ChinaLifeGroup,
    PICCGroup,
    Chery,
    Mindray,
    Shenzhou,
    LuzhouLaojiao,
    Huafeng,
    Infore,
    Seres,
    Shrcb,
    Haid,
    Dahua,
    Baic,
    Naura,
    Poly,
    Xiangyu,
    Changan,
    DigitalChina,
    Bosc,
    Sinotrans,
    Sany,
    Transsion,
    Bocd,
    Cscb,
    Dsbj,
    Sailun,
    Csc108,
    Tsingtao,
    Yuhong,
    Iflytek,
    Goldwind,
    Mengniu,
    Leapmotor,
    Mywind,
    Popmart,
    Szgas,
    Ovt,
    Juhua,
    NewHope,
    CNAF,
    Greentown,
    BankOfBeijing,
    ENN,
    Beike,
    SMIC,
    Sunwoda,
    ZhongyuanBank,
    Vital,
    WuxiApptec,
    Gotion,
    CALB,
    CICC,
    Jiangling,
    Avary,
    ChinaStock,
    AUX,
)
