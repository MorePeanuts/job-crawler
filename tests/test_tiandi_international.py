"""天地科技国际分公司两岗的机构及身份回放。"""

import pytest

from job_crawler.adapters.tiandi_international import jobs, split_contents, tenant, unit_node
from job_crawler.transport import CrawlError


def test_branch_tree_and_same_named_jobs_keep_distinct_ids() -> None:
    tenant(
        {
            "code": 200,
            "data": {
                "key": "cctegjob",
                "company_id": "10685382754151861",
                "company": {"name": "中国煤炭科工集团有限公司"},
            },
        }
    )
    tree = {
        "code": 200,
        "data": {
            "organization_tree": {
                "company_id": "10685382754151861",
                "name": "中国煤炭科工集团有限公司",
                "children": [
                    {"company_id": "135435436473453420", "name": "天地科技股份有限公司"},
                    {
                        "company_id": "10685391416427355",
                        "name": "天地科技股份有限公司国际分公司",
                        "all_job_count": 2,
                        "job_count": 2,
                    },
                ],
            }
        },
    }
    assert unit_node(tree)["all_job_count"] == 2
    rows = [
        {
            "job_id": str(number),
            "department_cn": department,
            "company_id": "10685391416427355",
            "company_name": "天地科技股份有限公司国际分公司",
            "job_name": "项目助理",
            "recruitment_type_cn": "校园招聘",
            "nature_cn": "校招",
            "status": 1,
            "contents": "【职责描述】项目执行【职责要求】硕士",
        }
        for number, department in ((1, "技术产业部"), (2, "国际合作中心"))
    ]
    response = {"code": 200, "data": {"total": 2, "page": 1, "page_size": 20, "list": rows}}
    assert [row["job_id"] for row in jobs(response, 2)] == ["1", "2"]
    rows[1]["nature_cn"] = "社招"
    with pytest.raises(CrawlError):
        jobs(response, 2)
    with pytest.raises(CrawlError):
        jobs({**response, "data": {**response["data"], "total": 3}}, 2)


def test_official_duties_requirements_heading_is_preserved() -> None:
    duties, requirements = split_contents("【职责描述】参与项目执行。\n【职责要求】硕士研究生。")
    assert duties == "参与项目执行。"
    assert requirements == "硕士研究生。"
