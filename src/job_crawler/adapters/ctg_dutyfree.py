"""CTG Duty Free's exact employers in the parent group's 2027 IGuopin project."""

from datetime import date
from typing import Any, Protocol, cast

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

ROOT = "https://gp-api.iguopin.com"
COMPANY_API = ROOT + "/api/company/index/v1/project-company"
JOB_API = ROOT + "/api/jobs/v1/project-job"
PROJECT_ID = "217467897776178383"
COMPANY = "中国旅游集团中免股份有限公司"
BRANCH = COMPANY + "上海数字科技分公司"
PAGE_SIZE = 100


class ProjectSession(Protocol):
    last_evidence: str

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
        credentials: str = "include",
    ) -> dict[str, Any]: ...


def _data(response: dict[str, Any], label: str) -> Any:
    check(response.get("code") == 200 and response.get("msg") == "OK", f"中免{label}接口失败")
    return response.get("data")


def _date(raw: object, label: str) -> str:
    check(isinstance(raw, str) and len(raw) >= 10, f"中免{label}缺失")
    assert isinstance(raw, str)
    try:
        return date.fromisoformat(raw[:10]).isoformat()
    except ValueError as exc:
        raise ValueError(f"中免{label}格式变化") from exc


def _body(raw: object) -> tuple[str, str]:
    check(isinstance(raw, str), "中免岗位正文缺失")
    assert isinstance(raw, str)
    parts = raw.split("【任职资格】", 1)
    check(
        len(parts) == 2 and parts[0].startswith("【职位描述】") and bool(parts[1].strip()),
        "中免岗位正文小标题变化",
    )
    duties = parts[0].removeprefix("【职位描述】").strip()
    check(bool(duties), "中免岗位职责缺失")
    return duties, parts[1].strip()


def _employers(tree: Any) -> dict[str, tuple[str, int]]:
    check(isinstance(tree, dict) and isinstance(tree.get("children"), list), "中免公司树缺失")
    assert isinstance(tree, dict)
    parents = [node for node in tree["children"] if node.get("name") == COMPANY]
    check(len(parents) == 1, "中免股份本级在公司树中缺失或重复")
    parent = parents[0]
    check(isinstance(parent.get("children"), list), "中免股份公司树分支缺失")
    branches = [node for node in parent["children"] if node.get("name") == BRANCH]
    check(len(branches) == 1, "中免股份上海数字科技分公司缺失或重复")
    result: dict[str, tuple[str, int]] = {}
    for name, node in ((COMPANY, parent), (BRANCH, branches[0])):
        company_id, count = node.get("company_id"), node.get("job_count")
        check(
            isinstance(company_id, str)
            and bool(company_id)
            and isinstance(count, int)
            and count >= 0,
            "中免招聘单位 ID 或岗位计数异常",
        )
        result[company_id] = (name, count)
    check(len(result) == 2, "中免招聘单位 ID 冲突")
    return result


class CtgDutyFreeCampus(Adapter):
    name = "ctg-dutyfree-campus"
    host = "ctgjob.iguopin.com"
    path = "/job-campus"
    scope_description = "中旅集团2027校招项目；仅中免股份本级与其上海数字科技分公司"
    ready_endpoints = (JOB_API,)

    async def harvest(self) -> None:
        session = cast(ProjectSession, self.session)
        company_response = await session.request(
            COMPANY_API,
            payload={"project_ids": [PROJECT_ID], "show_all_company": 0},
            credentials="omit",
        )
        company_data = _data(company_response, "公司树")
        check(isinstance(company_data, dict), "中免公司树结构变化")
        assert isinstance(company_data, dict)
        employers = _employers(company_data.get("list"))
        company_evidence = session.last_evidence
        scope = Scope(name="ctg-2027-dutyfree-tree")
        scope.evidence.append(company_evidence)
        self.result.scopes.append(scope)
        seen: set[str] = set()
        accepted: dict[str, int] = {company_id: 0 for company_id in employers}
        parent_id = next(
            company_id for company_id, (name, _) in employers.items() if name == COMPANY
        )
        page = 1
        while True:
            response = await session.request(
                JOB_API,
                payload={
                    "page": page,
                    "page_size": PAGE_SIZE,
                    "source": "s_job_list",
                    "company_id_with_sub": parent_id,
                    "project_id": [PROJECT_ID],
                    "project_group": [],
                },
                credentials="omit",
            )
            data = _data(response, "岗位目录")
            check(isinstance(data, dict), "中免岗位目录结构变化")
            assert isinstance(data, dict)
            rows, total = data.get("list"), data.get("total")
            check(
                isinstance(rows, list)
                and isinstance(total, int)
                and total >= 0
                and data.get("page") == page
                and data.get("page_size") == PAGE_SIZE
                and len(rows) <= PAGE_SIZE,
                "中免岗位分页或总数结构变化",
            )
            assert isinstance(rows, list) and isinstance(total, int)
            if scope.expected is None:
                scope.expected = total
            check(total == scope.expected, "中免岗位目录总数在遍历中变化")
            list_evidence = session.last_evidence
            scope.evidence.append(list_evidence)
            for row in rows:
                check(isinstance(row, dict), "中免岗位目录行结构变化")
                assert isinstance(row, dict)
                job_id = row.get("job_id")
                check(
                    isinstance(job_id, str) and bool(job_id) and job_id not in seen,
                    "中免岗位 ID 缺失或重复",
                )
                seen.add(job_id)
                scope.listed += 1
                scope.unique += 1
                company_id = row.get("company_id")
                if company_id not in employers:
                    scope.skipped_out_of_scope += 1
                    continue
                employer_name = employers[company_id][0]
                check(
                    row.get("company_name") in {employer_name, "中旅免税-" + employer_name},
                    "中免岗位招聘主体与公司树不一致",
                )
                accepted[company_id] += 1
                check(
                    row.get("recruitment_type_cn") == "校园招聘" and row.get("nature_cn") == "校招",
                    "中免公司树混入非校园招聘岗位",
                )
                if row.get("status") != 1 or row.get("hide") != 0:
                    scope.skipped_closed += 1
                    continue
                deadline = _date(row.get("end_time"), "截止日期")
                if deadline < self.as_of.date().isoformat():
                    scope.skipped_expired += 1
                    continue
                duties, requirements = _body(row.get("contents"))
                locations = row.get("district_list")
                check(
                    isinstance(locations, list)
                    and bool(locations)
                    and all(isinstance(location, dict) for location in locations),
                    "中免岗位工作地点结构变化",
                )
                assert isinstance(locations, list)
                job = self.job(
                    job_id,
                    title=text(row.get("job_name")),
                    unit=employer_name,
                    batch="2027年度校园招聘",
                    category_raw=text(row.get("category_cn")),
                    education=text(row.get("education_cn")),
                    location="、".join(text(location.get("area_cn")) for location in locations),
                    duties=duties,
                    requirements=requirements,
                    published="",
                    deadline=deadline,
                    source_url=self.source.url,
                    field_sources={
                        "unit": "project-company 精确公司 ID + project-job.company_id",
                        "duties": "project-job.contents 职位描述段",
                        "requirements": "project-job.contents 任职资格段",
                        "education": "project-job.education_cn",
                        "location": "project-job.district_list.area_cn",
                        "published": "source_missing；start_time 为招聘起始时间，非岗位发布日期",
                        "deadline": "project-job.end_time",
                    },
                )
                check(bool(job.title and job.location), "中免岗位标题或工作地点缺失")
                job.evidence = [company_evidence, list_evidence]
                self.result.jobs.append(job)
                scope.details += 1
            check(scope.unique <= total, "中免岗位目录超出总数")
            if scope.unique == total:
                for company_id, (_, expected) in employers.items():
                    check(accepted[company_id] == expected, "中免本级或分公司岗位计数未闭合")
                scope.terminal = True
                break
            check(len(rows) == PAGE_SIZE, "中免岗位未到末页却少于整页")
            page += 1
