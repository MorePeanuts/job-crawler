"""Yili's public Hotjob campus catalog, restricted to headquarters jobs."""

from typing import Any

from job_crawler.adapters.base import text
from job_crawler.adapters.classic_hotjob import ClassicHotjobCampus
from job_crawler.adapters.platforms import check
from job_crawler.models import Job


class YiliHeadquarters(ClassicHotjobCampus):
    name = "yili-headquarters"
    host = "yili.hotjob.cn"
    path = (
        "/wt/yili/web/templet1000/index/"
        "corpwebPosition1000yili!gotoPostListForAjax?brandCode=1&recruitType=1"
    )
    scope_description = "伊利官网 recruitType=1 全量校招；仅总部 2027 届正式岗位"

    endpoint = "/wt/yili/web/json/position/list"
    catalog_scope = "campus-headquarters"

    def in_scope(self, row: dict[str, Any]) -> bool:
        if text(row.get("orgName")) != "总部":
            return False
        check(text(row.get("deptOrgName")).startswith("总部"), "伊利总部岗位部门归属不明")
        if "2027届校招" not in text(row.get("postName")):
            return False
        check(
            bool(text(row.get("workContent"))) and bool(text(row.get("serviceCondition"))),
            "伊利总部岗位缺少正文",
        )
        return True

    def _job(self, row: dict[str, Any], evidence: str) -> Job:
        post_id = str(row["postId"])
        job = self.job(
            post_id,
            title=text(row["postName"]),
            unit="总部",
            location=text(row.get("workPlace")),
            education=text(row.get("education")),
            category_raw=text(row.get("postType")),
            batch="2027届校招",
            duties=text(row.get("workContent")),
            requirements=text(row.get("serviceCondition")),
            published=text(row.get("publishDate")),
            deadline=text(row.get("endDate")),
            source_url=f"https://{self.host}{self.path}",
            field_sources={
                "duties": "postList[].workContent",
                "requirements": "postList[].serviceCondition",
                "published": "postList[].publishDate",
                "deadline": "postList[].endDate",
                "unit": "postList[].orgName=总部，deptOrgName以总部开头",
                "location": "postList[].workPlace；无省级路径则保留原文",
            },
        )
        job.evidence = [evidence]
        return job
