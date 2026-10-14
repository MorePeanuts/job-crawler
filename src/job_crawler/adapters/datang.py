"""Datang's public campus notices with per-position employing-unit checks."""

import json
from datetime import date
from typing import Any, Protocol, cast

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

ROOT = "https://zhaopin.china-cdt.com"
GROUP = "中国大唐集团有限公司"
NOTICE_API = ROOT + "/apply/notice/findInfo"
REVIEW_PROGRAMS = ("在京二级单位本部管培生", "电力交易管培生", "财务管理管培生")


class DatangSession(Protocol):
    last_evidence: str

    async def observed(self, needle: str) -> dict[str, Any]: ...

    async def request(
        self, url: str, *, payload: dict[str, Any], detail: bool = False
    ) -> dict[str, Any]: ...


def _date(value: object) -> str:
    check(isinstance(value, str) and len(value) >= 10, "大唐公开日期缺失")
    assert isinstance(value, str)
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError as exc:
        raise ValueError("大唐公开日期格式变化") from exc


def _education(value: object) -> str:
    raw = text(value)
    if "博士" in raw:
        return "博士"
    if "硕士" in raw:
        return "硕士"
    if "本科" in raw:
        return "本科"
    if "专科" in raw or "大专" in raw:
        return "大专"
    return ""


def _candidate(item: dict[str, Any]) -> bool:
    name = item.get("organName")
    return isinstance(name, str) and (
        name == GROUP or name.startswith(GROUP) and name.endswith("分公司")
    )


def _eligible(notice: dict[str, Any], row: dict[str, Any]) -> bool:
    title = text(notice.get("applyName"))
    if any(program in title for program in REVIEW_PROGRAMS):
        return False
    notice_name = text(notice.get("organName"))
    unit = text(row.get("organName"))
    employer = text(row.get("ownOrganName"))
    remark = text(row.get("remark"))
    if remark:
        return False
    if notice_name == GROUP:
        return unit == GROUP and employer == GROUP
    if not notice_name.startswith(GROUP) or not notice_name.endswith("分公司"):
        return False
    short = notice_name.removeprefix("中国大唐集团有限公司")
    allowed = {notice_name, notice_name + "新能源事业部", "大唐" + short + "新能源事业部"}
    return unit in allowed and employer in allowed


class Datang2027(Adapter):
    name = "datang-2027"
    host = "zhaopin.china-cdt.com"
    path = "/zpgg_xyzp.html"
    scope_description = "大唐集团2027校招；仅本公司及分公司内部单位，逐岗排除独立子公司"
    ready_endpoints = ("/apply/notice/xyzpHomeInfo",)

    async def harvest(self) -> None:
        session = cast(DatangSession, self.session)
        directory = Scope(name="campus-notices", unit="公告")
        self.result.scopes.append(directory)
        observed = await session.observed("/apply/notice/xyzpHomeInfo")
        payload = observed.get("post_data")
        check(isinstance(payload, str), "大唐公告目录请求缺失")
        assert isinstance(payload, str)
        try:
            sent = json.loads(payload)
            query = json.loads(sent["data"])
            response = json.loads(observed["body"])
            listing = json.loads(response["data"])
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("大唐公告目录结构变化") from exc
        check(sent.keys() == {"data"} and query == {"keyWord": ""}, "大唐公告目录含未知筛选")
        notices = listing.get("list")
        total = listing.get("total")
        check(
            response.get("code") == "10000"
            and isinstance(notices, list)
            and str(total).isdigit()
            and len(notices) == int(total),
            "大唐公告目录总数不闭合",
        )
        assert isinstance(notices, list)
        directory.expected = int(total)
        list_evidence = session.last_evidence
        directory.evidence.append(list_evidence)
        seen_notices: set[str] = set()
        seen_jobs: set[str] = set()
        for notice in notices:
            check(isinstance(notice, dict), "大唐公告行结构变化")
            notice_id = notice.get("applyId")
            check(
                isinstance(notice_id, str) and notice_id and notice_id not in seen_notices,
                "大唐公告 ID 重复或缺失",
            )
            seen_notices.add(notice_id)
            directory.listed += 1
            directory.unique += 1
            if not _candidate(notice):
                directory.skipped_out_of_scope += 1
                continue
            scope = Scope(name=f"notice-{notice_id}")
            self.result.scopes.append(scope)
            try:
                api = await session.request(
                    NOTICE_API,
                    payload={"data": json.dumps({"id": notice_id, "qc": "y"})},
                )
                check(
                    api.get("code") == "10000" and isinstance(api.get("data"), str),
                    "大唐公告详情失败",
                )
                item = json.loads(api["data"])
                check(
                    isinstance(item, dict)
                    and item.get("applyId") == notice_id
                    and item.get("applyName") == notice.get("applyName"),
                    "大唐公告身份不符",
                )
                assert isinstance(item, dict)
                rows = item.get("details")
                check(isinstance(rows, list), "大唐公告岗位列表缺失")
                assert isinstance(rows, list)
                check(bool(rows) or notice.get("postNumCount") == 0, "大唐有岗公告返回空详情")
                scope.expected = len(rows)
                detail_evidence = session.last_evidence
                scope.evidence.extend([list_evidence, detail_evidence])
                directory.details += 1
                for row in rows:
                    scope.listed += 1
                    check(isinstance(row, dict), "大唐岗位行结构变化")
                    assert isinstance(row, dict)
                    job_id = row.get("bringId")
                    check(
                        isinstance(job_id, str) and job_id and job_id not in seen_jobs,
                        "大唐岗位 ID 重复或缺失",
                    )
                    seen_jobs.add(job_id)
                    scope.unique += 1
                    check(
                        isinstance(row.get("applyId"), str) and bool(row["applyId"]),
                        "大唐岗位所属子公告 ID 缺失",
                    )
                    if not _eligible(notice, row):
                        scope.skipped_out_of_scope += 1
                        continue
                    try:
                        title = text(row.get("post"))
                        duties = text(row.get("postDuty"))
                        requirements = text(row.get("postDemand"))
                        check(bool(title and duties and requirements), "大唐本公司岗位正文缺失")
                        raw_education = text(row.get("educationBackground"))
                        education = _education(raw_education)
                        if raw_education:
                            check(bool(education), "大唐岗位学历字段未知")
                        deadline = _date(row.get("usefulLifeEnd") or item.get("endDate"))
                        job = self.job(
                            job_id,
                            title=title,
                            unit=text(row.get("ownOrganName")),
                            batch=text(item.get("applyName")),
                            category_raw=text(row.get("psTypeName")),
                            location=text(row.get("workPlace")),
                            education=education,
                            duties=duties,
                            requirements=requirements,
                            published=_date(item.get("applyPublicTime")),
                            deadline=deadline,
                            source_url=self.source.url,
                            field_sources={
                                "unit": "findInfo.details[].ownOrganName + organName + remark",
                                "duties": "findInfo.details[].postDuty",
                                "requirements": "findInfo.details[].postDemand",
                                "education": "findInfo.details[].educationBackground",
                                "location": "findInfo.details[].workPlace",
                                "published": "findInfo.applyPublicTime",
                                "deadline": "findInfo.details[].usefulLifeEnd or findInfo.endDate",
                            },
                        )
                        job.evidence = [list_evidence, detail_evidence]
                        self.result.jobs.append(job)
                        scope.details += 1
                    except Exception as exc:
                        self.error(exc, job_id)
                scope.terminal = True
            except Exception as exc:
                self.error(exc, notice_id)
        directory.terminal = True
