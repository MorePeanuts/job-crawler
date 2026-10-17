"""Foxconn's public classic Hotjob campus catalogue."""

from typing import Any
from urllib.parse import urlencode

from job_crawler.adapters.base import text
from job_crawler.adapters.classic_hotjob import ClassicHotjobCampus
from job_crawler.adapters.platforms import check
from job_crawler.models import Job


class FoxconnCampus(ClassicHotjobCampus):
    name = "foxconn-campus"
    host = "foxconn.hotjob.cn"
    path = "/wt/Foxconn/web/index/CompFoxconnPagerecruit_School"
    endpoint = "/wt/Foxconn/web/json/position/list"
    ready_endpoints = (endpoint,)
    catalog_scope = "foxconn-campus-all"
    scope_description = "富士康官方 recruitType=1 无筛选校园目录，全部事业群；通用岗位保持原始一条"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(text(row["workType"]) in {"全职", "实习"}, "富士康岗位工作类型未知")
        return True

    def _job(self, row: dict[str, Any], evidence: str) -> Job:
        identity = str(row["postId"])
        job = self.job(
            identity,
            title=text(row["postName"]),
            unit=text(row["orgName"]),
            location=text(row["workPlace"]),
            education=text(row["education"]),
            category_raw=text(row["postType"]),
            duties=text(row["workContent"]),
            requirements=text(row["serviceCondition"]),
            published=text(row["publishDate"]),
            deadline=text(row["endDate"]),
            work_type="实习" if row["workType"] == "实习" or "实习" in row["postName"] else "校招",
            source_url=f"https://{self.host}/wt/Foxconn/web/templet1000/index/positionInfoFoxconn!getOnePosition?"
            + urlencode(
                {
                    "brandCode": 1,
                    "lanType": 1,
                    "showComp": "true",
                    "postId": identity,
                    "recruitType": 1,
                }
            ),
            field_sources={
                "duties": "postList.workContent",
                "requirements": "postList.serviceCondition",
                "published": "postList.publishDate",
                "deadline": "postList.endDate",
                "unit": "postList.orgName",
            },
        )
        job.evidence = [evidence]
        return job
