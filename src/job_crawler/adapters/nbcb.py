"""Ningbo Bank's public 2027 campus catalog, excluding separate subsidiaries."""

import json
from datetime import date
from typing import Any, Protocol, cast

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

ROOT = "https://zhaopin.nbcb.com.cn"
LIST_API = ROOT + "/api/position/schoolByPage/list"
DETAIL_API = ROOT + "/api/position/selectOne"
DICT_API = ROOT + "/api/dict/getDictList"
SUBSIDIARIES = {"永赢金租", "宁银理财", "宁银消金"}
PAGE_SIZE = 100


class BankSession(Protocol):
    last_evidence: str

    async def observed(self, needle: str) -> dict[str, Any]: ...

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]: ...


def _date(value: object, field: str) -> str:
    check(isinstance(value, str) and len(value) >= 10, f"宁波银行{field}缺失")
    assert isinstance(value, str)
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError as exc:
        raise ValueError(f"宁波银行{field}格式变化") from exc


def _unit(name: object) -> bool:
    check(isinstance(name, str) and bool(name), "宁波银行招聘机构缺失")
    assert isinstance(name, str)
    if name in SUBSIDIARIES:
        return False
    check(
        name == "总行" or name.endswith(("分行", "支行", "营业部")),
        "宁波银行出现未核实法人边界的招聘机构",
    )
    return True


def _lookup(raw: object, field: str) -> dict[str, str]:
    check(isinstance(raw, list), f"宁波银行{field}字典缺失")
    assert isinstance(raw, list)
    result: dict[str, str] = {}
    for row in raw:
        check(isinstance(row, dict), f"宁波银行{field}字典行异常")
        assert isinstance(row, dict)
        code, name = row.get("dictId"), row.get("dictName")
        check(
            isinstance(code, str)
            and isinstance(name, str)
            and bool(code and name)
            and code not in result,
            f"宁波银行{field}字典编码异常",
        )
        result[code] = name
    return result


class NingboBank2027(Adapter):
    name = "nbcb-2027"
    host = "zhaopin.nbcb.com.cn"
    path = "/"
    scope_description = "宁波银行2027校招；仅本体总行及分支机构，排除独立子公司"
    ready_endpoints = ("/api/positionNotice/notice",)

    async def harvest(self) -> None:
        session = cast(BankSession, self.session)
        notice = await session.observed("/api/positionNotice/notice")
        try:
            announcement = json.loads(notice["body"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("宁波银行校招公告结构变化") from exc
        check(
            announcement.get("status") == "0000"
            and isinstance(announcement.get("data"), dict)
            and announcement["data"].get("posYear") == "2027",
            "宁波银行当前公告不是2027届校招",
        )
        notice_evidence = session.last_evidence
        dictionary = await session.request(DICT_API)
        check(dictionary.get("status") == "0000", "宁波银行公开字典失败")
        raw_dictionary = dictionary.get("data")
        check(isinstance(raw_dictionary, dict), "宁波银行公开字典结构变化")
        assert isinstance(raw_dictionary, dict)
        locations = _lookup(raw_dictionary.get("CODE_COMPCITY"), "地点")
        education = _lookup(raw_dictionary.get("CODE_RecEducation"), "学历")
        dictionary_evidence = session.last_evidence

        scope = Scope(name="2027-campus")
        scope.evidence.extend([notice_evidence, dictionary_evidence])
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            listing = await session.request(
                LIST_API,
                payload={
                    "education": "",
                    "publishTime": "",
                    "page": page,
                    "pageSize": PAGE_SIZE,
                    "workLocation": "",
                    "recruitmentType": 1,
                },
            )
            check(listing.get("status") == "0000", "宁波银行校招目录请求失败")
            data = listing.get("data")
            check(isinstance(data, dict), "宁波银行校招目录结构变化")
            assert isinstance(data, dict)
            rows = data.get("list")
            total = data.get("total")
            check(
                isinstance(rows, list)
                and isinstance(total, int)
                and isinstance(data.get("pageNum"), int)
                and data["pageNum"] == page
                and isinstance(data.get("isLastPage"), bool)
                and isinstance(data.get("pages"), int)
                and data["pages"] >= page
                and (bool(rows) or total == 0),
                "宁波银行校招分页或总数结构变化",
            )
            assert isinstance(rows, list) and isinstance(total, int)
            if scope.expected is None:
                scope.expected = total
            check(total == scope.expected, "宁波银行校招目录总数在遍历中变化")
            list_evidence = session.last_evidence
            scope.evidence.append(list_evidence)
            for row in rows:
                scope.listed += 1
                check(isinstance(row, dict), "宁波银行校招岗位行结构变化")
                assert isinstance(row, dict)
                job_id = row.get("id")
                check(
                    isinstance(job_id, str) and bool(job_id) and job_id not in seen,
                    "宁波银行校招岗位 ID 缺失或重复",
                )
                seen.add(job_id)
                scope.unique += 1
                check(row.get("recruitmentType") == "1", "宁波银行目录混入非校招岗位")
                if not _unit(row.get("compName")):
                    scope.skipped_out_of_scope += 1
                    continue
                deadline = _date(row.get("endTime"), "截止日期")
                if deadline < self.as_of.date().isoformat():
                    scope.skipped_expired += 1
                    continue
                try:
                    detail = await session.request(DETAIL_API, payload={"id": job_id}, detail=True)
                    check(detail.get("status") == "0000", "宁波银行岗位详情请求失败")
                    item = detail.get("data")
                    check(isinstance(item, dict), "宁波银行岗位详情结构变化")
                    assert isinstance(item, dict)
                    check(
                        item.get("id") == job_id
                        and item.get("posName") == row.get("posName")
                        and item.get("compHid") == row.get("compHid")
                        and item.get("compName") == row.get("compName")
                        and item.get("recruitmentType") == "1"
                        and item.get("workLocation") == row.get("workLocation")
                        and item.get("education") == row.get("education")
                        and _date(item.get("endTime"), "截止日期") == deadline,
                        "宁波银行岗位详情身份或属性与目录不符",
                    )
                    location_code = item.get("workLocation")
                    education_code = item.get("education")
                    check(
                        isinstance(location_code, str)
                        and location_code in locations
                        and isinstance(education_code, str)
                        and education_code in education,
                        "宁波银行岗位地点或学历代码未映射",
                    )
                    duties = text(item.get("posDuty"))
                    requirements = text(item.get("posRequiRement"))
                    check(
                        bool(text(item.get("posName")) and duties and requirements),
                        "宁波银行岗位标题或正文缺失",
                    )
                    published_raw = item.get("publishTime")
                    published = _date(published_raw, "发布日期") if published_raw else ""
                    job = self.job(
                        job_id,
                        title=text(item.get("posName")),
                        unit=text(item.get("compName")),
                        batch="2027届校园招聘",
                        category_raw=text(item.get("deptName")),
                        location=locations[location_code],
                        education=education[education_code],
                        duties=duties,
                        requirements=requirements,
                        published=published,
                        deadline=deadline,
                        source_url=ROOT + "/#/campus-recruitment",
                        field_sources={
                            "unit": "selectOne.compName + compHid",
                            "duties": "selectOne.posDuty",
                            "requirements": "selectOne.posRequiRement",
                            "education": "selectOne.education + getDictList.CODE_RecEducation",
                            "location": "selectOne.workLocation + getDictList.CODE_COMPCITY",
                            "published": "selectOne.publishTime（空时保留空）",
                            "deadline": "selectOne.endTime",
                        },
                    )
                    job.evidence = [notice_evidence, list_evidence, session.last_evidence]
                    self.result.jobs.append(job)
                    scope.details += 1
                except Exception as exc:
                    self.error(exc, job_id)
            if data["isLastPage"]:
                check(page == data["pages"] and scope.unique == total, "宁波银行校招末页不闭合")
                scope.terminal = True
                break
            check(page < data["pages"] and scope.unique < total, "宁波银行校招分页未推进")
            page += 1
