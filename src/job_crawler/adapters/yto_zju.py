"""YTO's four advertised 2027 graduate hiring tracks on Zhejiang University."""

import re
from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

EMPLOYER = "圆通速递有限公司"
TITLES = ("国际管培生", "科技管培生", "速递管培生", "圆通航空")


def compact(value: str) -> str:
    return "".join(text(value).split())


def demand(html: str) -> tuple[str, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.select_one(".con-tit")
    employer = soup.select_one(".dwxx-tit")
    info = soup.select_one(".con-info .dif")
    bodies = soup.select(".con-con")
    check(
        heading is not None
        and compact(heading.get_text()) == "圆通2027年校招宣讲会"
        and employer is not None
        and compact(employer.get_text()) == EMPLOYER
        and info is not None
        and len(bodies) == 2,
        "圆通高校公告标题、企业账号或正文结构变化",
    )
    assert info is not None
    date = re.search(r"发布时间：(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}", info.get_text())
    check(date is not None, "圆通高校公告发布时间缺失")
    assert date is not None
    page = compact(bodies[0].get_text(" ", strip=True))
    check(
        "三、招聘对象应届本科、硕士毕业生毕业时间2026年10月1日-2027年9月30日" in page
        and page.count("四、招聘岗位") == 1
        and page.count("五、福利待遇") == 1
        and "网申：即日起请尽早投递" in page,
        "圆通招聘对象、招聘区间或申请状态变化",
    )
    section = page.split("四、招聘岗位", 1)[1].split("五、福利待遇", 1)[0]
    matches = list(re.finditer(r"([1-9])．([^．]+?)(?=工作地点:)", section))
    check(
        len(matches) == 4 and [m[1] for m in matches] == ["1", "2", "3", "4"],
        "圆通招聘条目数量或编号变化",
    )
    rows: list[dict[str, str]] = []
    for i, match in enumerate(matches):
        title = match[2]
        check(title == TITLES[i], "圆通招聘类别名称变化")
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section)
        body = section[match.end() : end]
        fields = re.fullmatch(r"工作地点:(.+?)工作方向:(.+?)专业要求:(.+)", body)
        check(fields is not None, "圆通招聘类别地点、方向或专业缺失")
        assert fields is not None
        rows.append(
            {
                "title": title,
                "location": fields[1],
                "direction": fields[2],
                "majors": fields[3],
            }
        )
    return date[1], rows


class YtoZju2027(Adapter):
    name = "yto-zju-2027"
    host = "www.career.zju.edu.cn"
    path = (
        "/jyxt/sczp/xjhgl/ckXjhgwXq.zf?"
        "dwxxid=761C0E15421824AFE055000000000001&"
        "xjhbh=80e04c330a3d351713885071da695134"
    )
    scope_description = "圆通速递有限公司浙江大学 2027 届公告的四条招聘类别"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "圆通高校公告未就绪")
        published, rows = demand(await session.page.content())
        evidence = session.last_evidence
        scope = Scope(name="yto-zju-2027", expected=len(rows))
        self.result.scopes.append(scope)
        for item in self.add_page(scope, rows, set(), lambda row: row["title"]):
            job = self.job(
                item["title"],
                title=item["title"],
                source_url=self.source.url,
                unit=EMPLOYER,
                work_type="校招",
                location=item["location"],
                education="本科、硕士",
                requirements=f"工作方向：{item['direction']}；专业要求：{item['majors']}",
                published=published,
                field_sources={
                    "unit": "高校账号为圆通速递有限公司；上市公司公告核对全资关系",
                    "title": "招聘岗位四条原文类别；圆通航空保留为类别，不拆工作方向",
                    "location": "逐条工作地点；全国、全球及多城市保留原文",
                    "education": "公告三、招聘对象列本科、硕士",
                    "requirements": "逐条工作方向和专业要求",
                    "published": "高校页面发布时间",
                    "duties": "source_missing:公告未列逐岗职责",
                    "deadline": "source_missing:公告仅称即日起尽早投递，未列截止日期",
                },
            )
            job.evidence = [evidence]
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True
