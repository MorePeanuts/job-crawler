"""中国科大认证企业主页公开的当届校园岗位目录。"""

from typing import Any, Protocol, cast

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

API = "https://www.job.ustc.edu.cn/Ajax/jywapi.ashx"
COMPANY_ID = "26568"
EMPLOYER = "安徽楚江科技新材料股份有限公司"
CREDIT_CODE = "91340200743082289Q"


class UstcSession(Protocol):
    last_evidence: str

    async def observed(self, needle: str) -> dict[str, Any]: ...

    async def request(
        self, url: str, *, form: dict[str, str], detail: bool = False
    ) -> dict[str, Any]: ...


class UstcCompanyCampus(Adapter):
    host = "www.job.ustc.edu.cn"
    company_id = ""
    employer = ""
    credit_code = ""
    ready_endpoints = ("/Ajax/jywapi.ashx",)

    def campus_job(self, company: dict[str, Any], detail: dict[str, Any]) -> bool:
        raise NotImplementedError

    async def harvest(self) -> None:
        session = cast(UstcSession, self.session)
        observed = await session.observed("/Ajax/jywapi.ashx")
        check(observed.get("url") == API, "中国科大企业接口地址改变")
        check(
            observed.get("post_data") == f"action=companyinfo&cid={self.company_id}",
            "中国科大企业主页身份请求改变",
        )
        company = await session.request(API, form={"action": "companyinfo", "cid": self.company_id})
        check(
            company.get("r") == 0
            and company.get("CompanyName") == self.employer
            and company.get("OrgCode") == self.credit_code,
            "中国科大企业账号与名录主体不一致",
        )
        rows = company.get("JobList")
        check(isinstance(rows, list) and bool(rows), "高校企业主页岗位目录为空或格式改变")
        assert isinstance(rows, list)
        scope = Scope(name=f"ustc-company-{self.company_id}", expected=len(rows))
        self.result.scopes.append(scope)
        listed = self.add_page(scope, rows, set(), lambda row: text(row.get("ID")))
        listing_evidence = session.last_evidence
        for row in listed:
            key = text(row["ID"])
            try:
                detail = await session.request(
                    API, form={"action": "jobinfo", "jid": key}, detail=True
                )
                check(
                    detail.get("r") == 0
                    and text(detail.get("ID")) == key
                    and text(detail.get("CompanyID")) == self.company_id
                    and detail.get("CompanyName") == self.employer
                    and detail.get("JobName") == row.get("JobName"),
                    "中国科大岗位详情与认证企业列表不一致",
                )
                check(detail.get("WorkKind") == "全职", "高校企业目录出现非全职岗位")
                check(
                    bool(text(detail.get("Describe")) and text(detail.get("Require"))),
                    "高校岗位详情职责或要求缺失",
                )
                check(
                    text(detail.get("UpdateTime")) == text(row.get("UpdateDate"))[:10],
                    "高校列表与详情发布日期不一致",
                )
                if not self.campus_job(company, detail):
                    scope.skipped_out_of_scope += 1
                    continue
                job = self.job(
                    key,
                    title=text(detail["JobName"]),
                    work_type="校招",
                    source_url=(
                        "https://www.job.ustc.edu.cn/Jobinformation/list.aspx?itemid=" + key
                    ),
                    unit=self.employer,
                    location=text(detail.get("Workplace")),
                    education=text(detail.get("EducationRequired")),
                    duties=text(detail["Describe"]),
                    requirements=text(detail["Require"]),
                    published=text(detail["UpdateTime"]),
                    field_sources={
                        "unit": "高校认证企业主页 CompanyName/OrgCode 与详情 CompanyID",
                        "work_type": "高校校招频道当届岗位凭据及详情 WorkKind=全职",
                        "published": "中国科大岗位详情页面标注发布日期 UpdateTime",
                        "deadline": "source_missing:招聘期限为空；不以 Days 推断截止日期",
                        "duties": "jobinfo.Describe",
                        "requirements": "jobinfo.Require",
                        "headcount": f"企业主页招聘人数={row.get('Count')}；不按人数拆行",
                    },
                )
                job.evidence = [listing_evidence, session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1
            except Exception as exc:
                self.error(exc, key)
        scope.terminal = True


class ChujiangUstcCampus(UstcCompanyCampus):
    name = "chujiang-ustc-campus"
    company_id = COMPANY_ID
    employer = EMPLOYER
    credit_code = CREDIT_CODE
    path = "/Jobinformation/info.aspx?itemid=26568"
    scope_description = (
        "中国科大就业网楚江新材认证企业账号当前全部总裁直培生岗位；不扩为企业全网招聘"
    )

    def campus_job(self, company: dict[str, Any], detail: dict[str, Any]) -> bool:
        check("总裁直培生" in text(company.get("Profile")), "楚江校园培养批次说明缺失")
        return True


class TonglingUstc2027(UstcCompanyCampus):
    name = "tongling-ustc-2027"
    company_id = "5563"
    employer = "铜陵有色金属集团控股有限公司"
    credit_code = "91340700151105774A"
    path = "/Jobinformation/info.aspx?itemid=5563"
    scope_description = (
        "中国科大铜陵有色认证企业账号全部公开岗位；只选标题及要求均明确2027届的校招岗位"
    )

    def campus_job(self, company: dict[str, Any], detail: dict[str, Any]) -> bool:
        return "2027年校园招聘" in text(detail.get("JobName")) and "2027届" in text(
            detail.get("Require")
        )


class ZhongweiUstc2027(UstcCompanyCampus):
    name = "zhongwei-ustc-2027"
    company_id = "165411"
    employer = "中伟新材料股份有限公司"
    credit_code = "91520690314383681D"
    path = "/Jobinformation/info.aspx?itemid=165411"
    scope_description = "中国科大中伟新材料认证企业账号当前全部2027届全职岗位；不扩为企业全网招聘"

    def campus_job(self, company: dict[str, Any], detail: dict[str, Any]) -> bool:
        return text(detail.get("JobName")).startswith("2027届")


class ShanyingUstc2027(UstcCompanyCampus):
    name = "shanying-ustc-2027"
    company_id = "530"
    employer = "山鹰国际控股股份公司"
    credit_code = "91340500150523317H"
    path = "/Jobinformation/info.aspx?itemid=530"
    scope_description = "中国科大山鹰国际认证企业账号当前全部明确要求2027届毕业生的全职岗位"

    def campus_job(self, company: dict[str, Any], detail: dict[str, Any]) -> bool:
        return "2027届毕业生" in text(detail.get("Require"))


class QingshanUstc2027(UstcCompanyCampus):
    name = "qingshan-ustc-2027"
    company_id = "29423"
    employer = "青山控股集团有限公司"
    credit_code = "91330300751176226P"
    path = "/Jobinformation/info.aspx?itemid=29423"
    scope_description = (
        "中国科大青山控股认证企业账号八岗全目录；仅纳入武汉纺大2027届展位同题"
        "且无工作年限要求的冶金、机械管培生和会计三岗"
    )
    cohort_titles = frozenset({"冶金管培生", "机械管培生", "会计"})

    def campus_job(self, company: dict[str, Any], detail: dict[str, Any]) -> bool:
        if text(detail.get("JobName")) not in self.cohort_titles:
            return False
        check("年以上" not in text(detail.get("Require")), "青山当届岗位出现工作年限要求")
        return True

    async def harvest(self) -> None:
        await super().harvest()
        check(
            {job.title for job in self.result.jobs} == self.cohort_titles,
            "青山高校 2027 届已核对岗位集合变化",
        )
