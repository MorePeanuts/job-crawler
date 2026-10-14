"""Verified public Hangzhou Bank 2027 campus catalogue."""

from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import CrawlError


def bank_unit(name: str) -> bool:
    return name in {
        "总行",
        "科创金融事业总部",
        "信用小微事业部",
        "上海小微信贷中心",
    } or name.endswith(("分行", "直属支行"))


def deadline(value: object) -> str:
    raw = text(value)
    check(len(raw) == 14 and raw.isdigit(), "杭州银行截止时间格式变化")
    return datetime.strptime(raw, "%Y%m%d%H%M%S").isoformat(sep=" ")


class HzbankCampus(Adapter):
    name = "hzbank-campus"
    host = "myjob.hzbank.com.cn"
    path = "/hzzp-apply-web/static/index.html#/employ/school"
    ready_endpoints = ("/hzzp-apply/employInfo/queryEmployInfosList",)
    scope_description = "杭州银行 2027 届秋招 positionType=01 全目录；排除杭银理财独立法人"

    async def harvest(self) -> None:
        batches = await self.session.request(
            "https://myjob.hzbank.com.cn/hzzp-apply/employInfo/queryActiveBatchList?positionType=01"
        )
        check(batches.get("errorCode") == "0", "杭州银行活动批次请求失败")
        items = batches.get("result")
        if not isinstance(items, list) or len(items) != 1:
            raise CrawlError("schema_changed", "杭州银行校招批次范围变化")
        batch = items[0]
        check(
            batch.get("batchName") == "2027届秋季校园招聘项目" and batch.get("type") == "01",
            "杭州银行 2027 校招批次变化",
        )
        batch_no = str(batch["batchNo"])
        observed = await self.session.observed("/employInfo/queryEmployInfosList")
        parts = urlsplit(observed["url"])
        check(parts.hostname == self.host, "杭州银行校招接口跨域")
        query = {
            key: values[0] for key, values in parse_qs(parts.query, keep_blank_values=True).items()
        }
        check(
            query
            == {
                "page": "0",
                "positionName": "",
                "positionType": "01",
                "size": "6",
                "organNo": "",
                "batchNos": "",
            },
            "杭州银行岗位列表带未知筛选或分页参数",
        )
        scope = Scope(name="2027-campus-positionType-01")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 0
        while True:
            url = urlunsplit(parts._replace(query=urlencode({**query, "page": str(page)})))
            response = await self.session.request(url)
            check(response.get("errorCode") == "0", "杭州银行岗位接口业务失败")
            result = response["result"]
            total = int(result["totalElements"])
            pages = int(result["totalPages"])
            check(total > 0 and pages > 0, "杭州银行校招职位目录为空")
            check(int(result["number"]) == page, "杭州银行返回错误页码")
            check(int(result["size"]) == 6, "杭州银行分页大小变化")
            if scope.expected is None:
                scope.expected = total
            check(total == scope.expected, "杭州银行分页期间总数变化")
            rows = self.add_page(scope, result["content"], seen, lambda row: str(row["id"]))
            evidence = self.session.last_evidence
            for row in rows:
                check(text(row.get("batchNo")) == batch_no, "杭州银行岗位批次变化")
                check(text(row.get("positionType")) == "01", "杭州银行混入非校招岗位")
                unit = text(row.get("organizationName"))
                if unit == "杭银理财":
                    scope.skipped_out_of_scope += 1
                    continue
                check(bank_unit(unit), "杭州银行出现未知机构，法人范围未证实")
                check(
                    bool(text(row.get("jobDesc")) and text(row.get("jobRequire"))),
                    "杭州银行岗位正文缺失",
                )
                job = self.job(
                    str(row["id"]),
                    title=text(row.get("positionName")),
                    unit=unit,
                    location=text(row.get("workSpace")),
                    duties=text(row.get("jobDesc")),
                    requirements=text(row.get("jobRequire")),
                    deadline=deadline(row.get("endTime")),
                    source_url=self.source.url,
                    field_sources={
                        "duties": "queryEmployInfosList.result.content[].jobDesc",
                        "requirements": "queryEmployInfosList.result.content[].jobRequire",
                        "location": "queryEmployInfosList.result.content[].workSpace",
                        "deadline": "queryEmployInfosList.result.content[].endTime",
                        "published": "source_missing:未提供逐岗位发布时间；startTime 是招聘开始时间",
                    },
                )
                job.evidence = [evidence]
                self.result.jobs.append(job)
                scope.details += 1
            if page + 1 >= pages:
                check(bool(result["last"]), "杭州银行分页末端标志不一致")
                scope.terminal = True
                break
            check(not result["last"] and bool(rows), "杭州银行分页提前结束")
            page += 1
