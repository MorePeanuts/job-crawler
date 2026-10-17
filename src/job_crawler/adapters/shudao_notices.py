"""Explicit application deadlines from Shudao's linked public announcements."""

import hashlib
import re
from datetime import date, datetime, time
from urllib.parse import parse_qs, urljoin, urlsplit

from job_crawler.adapters.platforms import check
from job_crawler.models import Job, Scope
from job_crawler.transport import BrowserSession

DATE = re.compile(r"(20\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})日?")
VERIFIED_IMAGES = {
    "645": "56adcd4e86796d29ead4ff47614cc8cd2fb170eaa6b8b0a95f0fe3d3d64a42ae",
    "706": "766c90b997870c1ecb06236a9fe4e0fa744e9c9942bfb99035cacd35223aadd2",
}


def announcement_deadline(body: str) -> str:
    candidates: set[str] = set()
    mentions = False
    for line in body.splitlines():
        application = re.search(r"报名.{0,12}(?:时间|截止)|截止.{0,12}报名", line)
        if application is None or "年龄" in line[: application.start()]:
            continue
        mentions = True
        line = line[application.start() :]
        matches = list(DATE.finditer(line))
        if not matches:
            continue
        if len(matches) == 1 and not any(word in line for word in ("截止", "至", "止")):
            continue
        dates = [date(*map(int, match.groups())) for match in matches]
        check(dates[-1] >= dates[0], "蜀道报名日期范围倒置")
        clock = re.match(
            r"\s*(\d{1,2})(?:[:：](\d{2})|时(?:(\d{1,2})分)?)", line[matches[-1].end() :]
        )
        if clock:
            hour = int(clock[1])
            minute = int(clock[2] or clock[3] or 0)
            candidates.add(datetime.combine(dates[-1], time(hour, minute)).isoformat(sep=" "))
        else:
            candidates.add(dates[-1].isoformat())
    if not mentions:
        return ""
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
            image_evidence: list[str] = []
            images = await session.page.locator(
                'img[src*="document/loadsourceimage"]'
            ).evaluate_all("nodes => [...new Set(nodes.map(n=>n.src))]")
            for image_url in images:
                image_parts = urlsplit(image_url)
                check(image_parts.hostname == "sdhr.shudaojt.com", "蜀道公告图片域名变化")
                session.consume_request()
                response = await session.page.request.get(image_url, timeout=30000)
                check(response.status == 200, "蜀道公告图片读取失败")
                content = await response.body()
                digest = hashlib.sha256(content).hexdigest()
                check(
                    VERIFIED_IMAGES.get(params["id"][0]) == digest,
                    "蜀道招聘图片内容变化，报名时间需重新核验",
                )
                image_path = session.output / f"notice-{params['id'][0]}-{digest[:12]}.png"
                image_path.write_bytes(content)
                image_evidence.append(str(image_path))
            scope.evidence.extend([detail_evidence, evidence, *image_evidence])
            for job in related:
                job.deadline = deadline
                job.evidence.extend([detail_evidence, evidence, *image_evidence])
                job.field_sources["deadline"] = (
                    f"同名关联招聘公告报名截止：{target}"
                    if deadline
                    else f"source_missing：关联公告未载明报名截止；已核验文字/固定图片内容：{target}"
                )
            scope.details += 1
        except Exception as exc:
            failures.append((name, exc))
    scope.terminal = True
    return failures
