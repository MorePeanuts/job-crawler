"""GEM's complete 2027 campus circular published by SDUT."""

import re
from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.filtering import SHANGHAI
from job_crawler.models import Issue, Scope
from job_crawler.transport import BrowserSession


class GemCampus(Adapter):
    name = "gem-2027-campus-announcement"
    host = "jgxy.sdut.edu.cn"
    path = "/2026/1017/c5450a574141/page.htm"
    scope_description = (
        "山东理工大学公开发布的格林美2027全年校园简章全部12个招聘类别；"
        "不拆分专业，不声称覆盖受验证阻塞的企业官网其他独立公告"
    )

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        document = BeautifulSoup(await session.page.content(), "html.parser")
        check(
            document.title is not None
            and document.title.get_text(strip=True) == "格林美2027届校园宣讲会",
            "格林美当届简章标题改变",
        )
        articles = document.select(".wp_articlecontent")
        check(len(articles) == 1, "格林美简章正文缺失或重复")
        article = articles[0]
        body = article.get_text("", strip=True)
        check(
            all(
                value in body
                for value in ("格林美", "深交所", "www.gem.com.cn", "gem_hr@gem.com.cn")
            ),
            "格林美招聘主体或官方联系依据改变",
        )
        check(
            not article.select("img,a[href],iframe,object,embed,.pagination,.pager"),
            "格林美简章新增未处理图片、附件、链接或分页",
        )
        lines = [
            node.get_text("", strip=True) for node in article.find_all(["p", "h2"], recursive=False)
        ]
        target = [value for value in lines if "招聘对象：" in value]
        check(target == ["1、招聘对象：2027年应届毕业生"], "格林美招聘对象改变")
        period_index = lines.index("七、招聘时间")
        period = re.sub(r"\s+", "", lines[period_index + 1])
        check(period == "2026年9月-2027年8月", "格林美招聘期间改变")
        current = self.as_of.astimezone(SHANGHAI)
        check(
            (2026, 9) <= (current.year, current.month) <= (2027, 8),
            "格林美简章已不处于当届招聘期间",
        )
        location = lines[lines.index("四、工作地点") + 1]
        check(
            location.startswith("聚焦国内外8个地点：") and location.count("/") == 6,
            "格林美工作地点结构改变",
        )
        locations = location.split("：", 1)[1]
        dates = re.findall(
            r"发布时间[：:]\s*(\d{4}-\d{2}-\d{2})", document.get_text("", strip=True)
        )
        check(dates == ["2026-10-17"], "格林美学院公告发布时间改变")
        tables = article.select("table")
        check(len(tables) == 1, "格林美类别表缺失或新增未处理表格")
        rows = [
            [cell.get_text("", strip=True) for cell in row.find_all(["th", "td"], recursive=False)]
            for row in tables[0].select("tr")
        ]
        check(len(rows) == 13 and rows[0] == ["序号", "大类", "细分"], "格林美类别数或表头改变")
        scope = Scope(name="gem-2027-categories", expected=12, unit="招聘类别")
        scope.evidence.append(session.last_evidence)
        self.result.scopes.append(scope)
        self.result.warnings.append(
            Issue(
                code="source_location_count_mismatch",
                source_id=self.source.source_id,
                message="简章写8个地点但实际列七地；原文全部保留，不补造第八地",
            )
        )
        seen: set[str] = set()
        for ordinal, row in enumerate(rows[1:], 1):
            scope.listed += 1
            try:
                check(len(row) == 3 and row[0] == str(ordinal), "格林美类别编号不连续或字段缺失")
                _, title, major = row
                check(
                    bool(title) and title not in seen and bool(major), "格林美类别或专业缺失、重复"
                )
                seen.add(title)
                scope.unique += 1
                job = self.job(
                    f"2027:{ordinal}",
                    title=title,
                    source_url=f"https://{self.host}{self.path}",
                    published=dates[0],
                    location=locations,
                    requirements=f"招聘对象：2027年应届毕业生\n专业：{major}\n公告招聘期间：{period}\n{location}\n招聘邮箱：gem_hr@gem.com.cn（邮件主题：应聘-学历-学校-姓名-专业）",
                    field_sources={
                        "published": "学院公开招聘公告发布时间，非宣讲时间",
                        "requirements": "完整简章类别专业及通用应届要求；月级招聘期间保留原文",
                        "location": "公告工作地点原文，8地计数与七地枚举不一致",
                        "education": "source_missing:薪资学历档次不等于类别最低学历要求",
                        "duties": "source_missing:仅列招聘类别及专业",
                        "deadline": "source_missing:招聘期间仅精确到月，未提供具体报名截止日",
                    },
                )
                self.result.jobs.append(job)
                scope.details += 1
            except Exception as exc:
                self.error(exc, str(ordinal))
        scope.terminal = True
