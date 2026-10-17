"""Huaneng public campus queries: grouped announcements, position-sized pages."""

import asyncio
import json
from typing import Any, cast

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession

PUBLIC_QUERY = """async ({operation,params}) => {
  const api=await import('/assets/recruit.7da53dca.js');
  if(operation==='catalog') return await api.e(params);
  if(operation==='announcement') return await api.c(params);
  if(operation==='units') return await api.i(params);
  if(operation==='top') return await api.f();
  if(operation==='good') return await api.p();
  if(operation==='company') return await api.d(params);
  throw new Error('Unknown public query');
}"""


class HuanengCampus(Adapter):
    name = "huaneng-campus"
    host = "zhaopin.chng.com.cn"
    path = "/CampusRecruit"
    scope_description = "华能京外、在京、管培三类单位全目录，与独立岗位总数核对"

    async def public_query(self, operation: str, params: object, filename: str) -> dict[str, Any]:
        session = cast(BrowserSession, self.session)
        session.consume_request()
        await asyncio.sleep(session.config.delay)
        async with asyncio.timeout(session.config.timeout):
            response = await session.page.evaluate(
                PUBLIC_QUERY, {"operation": operation, "params": params}
            )
        path = session.output / filename
        write_json(path, {"operation": operation, "params": params, "response": response})
        session.last_evidence = str(path)
        check(isinstance(response, dict) and response.get("code") == 0, "华能公开查询业务失败")
        data = response.get("data")
        if operation in {"units", "company", "top", "good"}:
            check(isinstance(data, list), "华能单位查询不是数组")
            return {"rows": data}
        check(isinstance(data, dict), "华能公开查询数据不是对象")
        return data

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check("中国华能集团有限公司" in await session.page.content(), "华能官网主体身份变化")
        observed = await session.observed("/admin-api/recruit/")
        response = json.loads(observed["body"])
        check(response.get("code") == 0 and isinstance(response.get("data"), list), "华能字典失败")
        dictionaries = response["data"]
        self.labels: dict[str, dict[str, str]] = {}
        for code in ("education", "job_category"):
            rows = [row for row in dictionaries if row.get("classifyCode") == code]
            check(
                len(rows) == 1 and isinstance(rows[0].get("children"), list), "华能字典缺失或重复"
            )
            pairs = [(text(row["value"]), text(row["label"])) for row in rows[0]["children"]]
            check(len(pairs) == len(dict(pairs)) and bool(pairs), "华能字典代码重复或为空")
            self.labels[code] = dict(pairs)
        self.dictionary_evidence = session.last_evidence
        self.announcements: dict[str, tuple[dict[str, Any], str]] = {}
        self.completed: set[str] = set()
        for kind in (0, 1, 2):
            try:
                await self.unit_catalog(kind)
            except Exception as exc:
                self.error(exc, f"taskType:{kind}")

    async def unit_catalog(self, kind: int) -> None:
        scope = Scope(name=f"campus-task-{kind}-by-company", evidence=[self.dictionary_evidence])
        self.result.scopes.append(scope)
        params = {
            "recruitType": 1,
            "taskType": kind,
            "pageNo": 1,
            "pageSize": 20,
            "positionName": "",
        }
        counts = await self.public_query("catalog", params, f"campus-{kind}-count.json")
        count = counts.get("total")
        check(type(count) is int and count >= 0, "华能目录总数非法")
        scope.expected = count
        scope.evidence.append(self.session.last_evidence)
        units: list[dict[str, Any]] = []
        if kind in (0, 1):
            tree = await self.public_query("units", kind, f"campus-{kind}-units.json")
            scope.evidence.append(self.session.last_evidence)
            for root in tree["rows"]:
                check(isinstance(root.get("children"), list), "华能单位树子节点缺失")
                units.extend(root["children"])
        else:
            for operation in ("top", "good"):
                tree = await self.public_query(operation, None, f"campus-2-{operation}.json")
                scope.evidence.append(self.session.last_evidence)
                units.extend(tree["rows"])
        unit_ids: set[str] = set()
        seen: set[str] = set()
        for unit in units:
            uid = text(unit.get("companyId"))
            check(
                uid.isdigit() and uid not in unit_ids and not unit.get("children"),
                "华能单位树重复或新增层级",
            )
            check(bool(text(unit.get("name"))), "华能单位名称缺失")
            unit_ids.add(uid)
            try:
                data = await self.public_query(
                    "company",
                    {
                        "recruitType": 1,
                        "taskType": kind,
                        "companyId": unit["companyId"],
                        "contentBody": unit["name"],
                    },
                    f"campus-{kind}-company-{uid}.json",
                )
                evidence = self.session.last_evidence
                scope.evidence.append(evidence)
                for announcement in data["rows"]:
                    check(
                        announcement.get("recruitType") == 1
                        and announcement.get("taskType") == kind,
                        "华能单位公告类型错配",
                    )
                    check(text(announcement.get("recruitCompanyId")) == uid, "华能公告招聘单位错配")
                    aid = text(announcement.get("id"))
                    check(aid.isdigit() and aid not in self.announcements, "华能单位公告ID重复")
                    self.announcements[aid] = announcement, evidence
                    check(
                        isinstance(announcement.get("positions"), list), "华能完整单位岗位数组缺失"
                    )
                    for row in announcement["positions"]:
                        scope.listed += 1
                        try:
                            key = text(row.get("id"))
                            check(
                                key.isdigit() and key not in seen and key not in self.completed,
                                "华能单位目录岗位重复",
                            )
                            seen.add(key)
                            scope.unique += 1
                            await self.position(kind, announcement, row, evidence)
                            self.completed.add(key)
                            scope.details += 1
                        except Exception as exc:
                            self.error(exc, text(row.get("id")))
            except Exception as exc:
                self.error(exc, uid)
        final = await self.public_query("catalog", params, f"campus-{kind}-count-final.json")
        scope.evidence.append(self.session.last_evidence)
        check(final.get("total") == count == len(seen), "华能单位全目录与独立岗位总数未闭合")
        scope.terminal = True

    async def position(
        self, kind: int, listing: dict[str, Any], row: dict[str, Any], evidence: str
    ) -> None:
        aid = text(listing.get("id"))
        key = text(row["id"])
        check(aid.isdigit() and text(row.get("announcementId")) == aid, "华能列表公告关联错配")
        if aid not in self.announcements:
            detail = await self.public_query("announcement", aid, f"announcement-{aid}.json")
            self.announcements[aid] = detail, self.session.last_evidence
        detail, detail_evidence = self.announcements[aid]
        for field in (
            "id",
            "title",
            "recruitType",
            "taskType",
            "recruitCompanyId",
            "recruitCompanyName",
        ):
            check(detail.get(field) == listing.get(field), f"华能公告{field}错配")
        check(detail.get("taskType") == kind and detail.get("status") in (0, 1), "华能公告状态未知")
        positions = detail.get("positions")
        check(isinstance(positions, list), "华能详情岗位数组缺失")
        assert isinstance(positions, list)
        matches = [item for item in positions if text(item.get("id")) == key]
        check(len(matches) == 1, "华能详情岗位缺失或重复")
        item = matches[0]
        for field in (
            "announcementId",
            "positionName",
            "address",
            "eduType",
            "endDate",
            "recruitCompanyId",
        ):
            check(item.get(field) == row.get(field), f"华能岗位{field}错配")
        check(item.get("status") in (0, 1), "华能岗位状态未知")
        education = text(item.get("eduType"))
        category = text(item.get("postCode"))
        check(education in self.labels["education"], "华能学历代码未知")
        check(category in self.labels["job_category"], "华能岗位类别代码未知")
        majors = item.get("majors")
        check(isinstance(majors, list), "华能完整专业数组缺失")
        check(
            all(text(m.get("positionId")) == key and text(m.get("majorName")) for m in majors),
            "华能专业关联错配",
        )
        requirements = text(item.get("jobReq"))
        if majors:
            requirements = (
                "专业：" + "、".join(text(m["majorName"]) for m in majors) + "\n" + requirements
            )
        check(bool(text(item.get("positionName"))) and bool(requirements), "华能岗位标题或要求为空")
        self.session.last_evidence = detail_evidence
        route = {0: "/CampusRecruit", 1: "/InternRecruit", 2: "/ManagementTraineeRecruit"}[kind]
        job = self.job(
            key,
            title=text(item["positionName"]),
            source_url=f"https://{self.host}{route}?aId={aid}",
            unit=text(detail["recruitCompanyName"]),
            batch=text(detail.get("recruitYear")),
            category_raw=self.labels["job_category"][category],
            education=self.labels["education"][education],
            location=text(item.get("address")),
            requirements=requirements,
            published=text(detail.get("publishTime")),
            deadline=text(item.get("endDate") or detail.get("endTime")),
            closed=item["status"] == 0 or detail["status"] == 0,
            field_sources={
                "requirements": "公告完整 positions[].jobReq 与 majors[].majorName",
                "education": "positions[].eduType 与官网 education 字典",
                "published": "关联公告 publishTime；不使用 createTime 或报名开始时间",
                "deadline": "positions[].endDate；保留源时分",
                "duties": "source_missing:jobReq 为源岗位要求，不据标题生成职责",
            },
        )
        job.evidence.extend([evidence, self.dictionary_evidence])
        self.result.jobs.append(job)
