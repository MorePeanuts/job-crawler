"""Explicit application deadlines from Shudao's linked public announcements."""

import re
from datetime import date
from urllib.parse import parse_qs, urljoin, urlsplit

from job_crawler.adapters.platforms import check
from job_crawler.models import Job, Scope
from job_crawler.transport import BrowserSession

DATE = re.compile(r"(20\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})日?")


def announcement_deadline(body: str) -> str:
    candidates: set[str] = set()
    for line in body.splitlines():
        application = re.search(r"报名.{0,12}(?:时间|截止)|截止.{0,12}报名", line)
        if application is None:
            continue
        line = line[application.start() :]
        matches = list(DATE.finditer(line))
        if not matches:
            continue
        if len(matches) == 1 and not any(word in line for word in ("截止", "至", "止")):
            continue
        dates = [date(*map(int, match.groups())) for match in matches]
        check(dates[-1] >= dates[0], "蜀道报名日期范围倒置")
        candidates.add(dates[-1].isoformat())
    check(len(candidates) == 1, "蜀道公告未给出唯一可核验的完整报名截止日期")
    return next(iter(candidates))


async def attach_notice_deadlines(
    session: BrowserSession, jobs: list[Job], scope: Scope
) -> list[tuple[str, Exception]]:
    grouped: dict[str, list[Job]] = {}
    for job in jobs:
        if job.batch:
            grouped.setdefault(job.batch, []).append(job)
    scope.expected = len(grouped)
    failures: list[tuple[str, Exception]] = []
    for name, related in grouped.items():
        scope.listed += 1
        scope.unique += 1
        try:
            first = related[0]
            await session.open(first.source_url)
            page = await session.page.evaluate("""() => ({
              text:document.body.innerText,
              links:[...document.querySelectorAll('a[href]')].map(a=>({text:a.innerText,url:a.href}))
            })""")
            check(first.title in page["text"], "蜀道岗位详情标题错配")
            matches = [
                link
                for link in page["links"]
                if "model=RecruitAnnounce" in link["url"] and name in link["text"]
            ]
            check(len(matches) == 1, "蜀道岗位没有唯一同名公告关联")
            target = urljoin(first.source_url, matches[0]["url"])
            parts = urlsplit(target)
            params = parse_qs(parts.fragment.partition("?")[2])
            check(
                parts.hostname == "sdhr.shudaojt.com"
                and params.get("model") == ["RecruitAnnounce"]
                and len(params.get("id", [])) == 1
                and params["id"][0].isdigit(),
                "蜀道公告链接身份变化",
            )
            detail_evidence = session.last_evidence
            await session.open(target)
            body = await session.page.locator("body").inner_text()
            check(name in body, "蜀道公告标题错配")
            deadline = announcement_deadline(body)
            evidence = session.last_evidence
            scope.evidence.extend([detail_evidence, evidence])
            for job in related:
                job.deadline = deadline
                job.evidence.extend([detail_evidence, evidence])
                job.field_sources["deadline"] = f"同名关联招聘公告报名截止：{target}"
            scope.details += 1
        except Exception as exc:
            failures.append((name, exc))
    scope.terminal = True
    return failures
