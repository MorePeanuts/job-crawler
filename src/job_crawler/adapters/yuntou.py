"""Yuntou's complete official notice directory and verified closed announcements."""

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import cast
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.adapters.yuntou_images import IMAGE_NOTICES, TEXT_IMAGES
from job_crawler.models import Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession, CrawlError

ROOT = "https://www.cnyig.com"
ENTRY = ROOT + "/newslist/rczp.htm"
TZ = ZoneInfo("Asia/Shanghai")
DATE = r"(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日"
CLOCK = r"(?:(\d{1,2})[:：︰](\d{2}))?"
POINT = DATE + CLOCK
RANGE = re.compile(POINT + r"(?:至|[-—－])" + POINT)
SINGLE = re.compile(POINT)


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


@dataclass(frozen=True)
class Notice:
    url: str
    title: str
    published: str


def listing(html: str, page: int) -> tuple[list[Notice], int]:
    doc = BeautifulSoup(html, "html.parser")
    check("人才招聘" in doc.get_text(), "云投目录栏目变化")
    pager = doc.select_one("#pageContainer")
    check(pager is not None, "云投目录缺少分页控件")
    assert pager is not None
    active = pager.select_one("a.hover")
    check(active is not None and active.get_text(strip=True) == str(page), "云投当前页错配")
    maximum = re.findall(r"var\s+max\s*=\s*(\d+)\s*;", str(pager))
    check(len(maximum) == 1, "云投目录总页数缺失或不唯一")
    last = int(maximum[0])
    check(1 <= page <= last <= 100, "云投目录页数超界")
    tails = [a for a in pager.select("a") if a.get_text(strip=True) == "尾页"]
    check(len(tails) == 1, "云投目录缺少唯一尾页")
    if page != last:
        check(tails[0].get("href") == f"/newslist/rczp/{last}/15.htm", "云投尾页与页数矛盾")
    else:
        check(not tails[0].get("href"), "云投末页尾页仍可跳转")
    rows: list[Notice] = []
    for dd in doc.select("dd"):
        link = dd.select_one(".divright a[href]")
        if link is None:
            continue
        day, month = dd.select_one(".divleft span"), dd.select_one(".divleft em")
        check(day is not None and month is not None, "云投目录日期缺失")
        assert day is not None and month is not None
        published = date.fromisoformat(month.get_text(strip=True) + "-" + day.get_text(strip=True))
        url = urljoin(ROOT, str(link["href"]))
        parts = urlsplit(url)
        check(
            parts.netloc == "www.cnyig.com"
            and parts.scheme == "https"
            and re.fullmatch(
                r"/(?:html/cnyig/\d{4}/\d{1,2}/\d{1,2}|news/rczp)/[a-f0-9-]+\.html?", parts.path
            )
            is not None
            and not parts.query
            and not parts.fragment,
            "云投公告URL身份变化",
        )
        title = compact(link.get_text())
        check(bool(title), "云投公告标题为空")
        rows.append(Notice(url, title, published.isoformat()))
    check(len(rows) == 15 if page < last else 1 <= len(rows) <= 15, "云投页行数异常")
    check(len({r.url for r in rows}) == len(rows), "云投页内重复公告")
    return rows, last


def excluded(title: str) -> str:
    if re.search(r"延期|延长|补充|更正|调整|暂停|取消", title):
        return ""
    if re.search(
        r"招聘结果公示|录用.*公示|录取.*公示|补录人员(?:名单)?公示|招聘情况公示|职称申报.*公示|拟录用|录用人员|面试人员|笔试人员|资格初审结果|资格审查结果|背景调查人选|终面名单|综合成绩排名|笔试结果",
        title,
    ):
        return "招聘结果或考试流程"
    if re.search(r"社会(?:公开)?招聘|见习人员|内部公开竞聘|市场化选聘|总部部门岗位管理意见", title):
        return "明确非正式校园范围"
    return ""


def article(html: str, row: Notice) -> tuple[str, list[str], str]:
    doc = BeautifulSoup(html, "html.parser")
    title, stamp, body = (
        doc.select_one(s) for s in (".articleTitle", ".articleTime", ".articleBox")
    )
    check(title is not None and compact(title.get_text()) == row.title, "云投公告标题错配")
    check(
        stamp is not None and compact(stamp.get_text()) == "日期：" + row.published,
        "云投公告发布日期错配",
    )
    check(body is not None, "云投公告正文缺失")
    assert body is not None
    images = [
        urljoin(ROOT, str(img["src"]))
        for img in body.select("img[src]")
        if not str(img["src"]).startswith("/Ueditorutf8/dialogs/attachment/fileTypeImages/icon_")
    ]
    # Include links in the image notice fingerprint: newly added extension attachments
    # must not inherit the previously inspected image-only deadline.
    semantic = (
        compact(body.get_text())
        + "\n"
        + "\n".join(urljoin(ROOT, str(a["href"])) for a in body.select("a[href]"))
    )
    return compact(body.get_text()), images, hashlib.sha256(semantic.encode()).hexdigest()


def point(groups: tuple[str | None, ...], year: int | None = None) -> datetime:
    y, month, day, hour, minute = groups
    check(y is not None or year is not None, "云投截止日期缺少年份")
    d = date(int(y or str(year)), int(month or "0"), int(day or "0"))
    if hour is None:
        return datetime.combine(d + timedelta(days=1), time(), TZ)
    h, m = int(hour), int(minute or "0")
    if h == 24:
        check(m == 0, "云投24时的分钟非零")
        return datetime.combine(d + timedelta(days=1), time(), TZ)
    return datetime.combine(d, time(h, m), TZ)


def deadline(text: str) -> tuple[datetime, str]:
    text = compact(text)
    candidates: dict[datetime, str] = {}
    # Start exactly at an application date phrase, never at qualification/age dates.
    phrases = re.findall(
        r"报名时间[：。]?(?:自|即日起至|自招聘公告发布之日起至)?(?:20\d{2}年)[^。；;]{0,100}"
        r"|应聘者请于20\d{2}年[^。；;]{0,70}"
        r"|材料于20\d{2}年[^。；;]{0,50}",
        text,
    )
    for phrase in phrases:
        match = RANGE.search(phrase)
        if match:
            groups = match.groups()
            start = point(groups[:5])
            end = point(groups[5:], int(groups[0] or "0"))
            # A date-only start denotes the entire start day, not its end.
            lower = start if groups[3] is not None else start - timedelta(days=1)
            check(end >= lower if groups[8] is not None else end > lower, "云投报名范围倒置")
        else:
            match = SINGLE.search(phrase)
            check(
                match is not None
                and ("至" in phrase[: match.start()] or "前" in phrase[match.end() :]),
                "云投报名截止语义未知",
            )
            assert match is not None
            end = point(match.groups())
        candidates[end] = phrase
    check(len(candidates) == 1, "云投没有唯一可核验报名截止")
    return next(iter(candidates.items()))


class YuntouNotices(Adapter):
    name = "yuntou-notices"
    host = "www.cnyig.com"
    path = "/newslist/rczp.htm"
    scope_description = "云投集团官网完整招聘公告；本版证明已截止范围，开放/未知公告及附件须另验收"

    async def harvest(self) -> None:
        check(self.source.url == ENTRY, "云投来源须为集团完整招聘公告入口")
        browser = cast(BrowserSession, self.session)
        catalog = Scope(name="yuntou-all-notices", unit="公告")
        self.result.scopes.append(catalog)
        rows, maximum = listing(await browser.page.content(), 1)
        catalog.evidence.append(browser.last_evidence)
        for page in range(2, maximum + 1):
            html = await browser.request_html(ROOT + f"/newslist/rczp/{page}/15.htm")
            more, last = listing(html, page)
            check(last == maximum, "云投遍历中总页数变化")
            rows.extend(more)
            catalog.evidence.append(browser.last_evidence)
        catalog.expected = catalog.listed = len(rows)
        catalog.unique = len({r.url for r in rows})
        check(catalog.listed == catalog.unique, "云投跨页重复公告")
        records: list[dict[str, object]] = []
        for row in rows:
            reason = excluded(row.title)
            record: dict[str, object] = {
                "url": row.url,
                "title": row.title,
                "published": row.published,
            }
            records.append(record)
            if reason:
                record["disposition"] = reason
                catalog.skipped_out_of_scope += 1
                continue
            scope = Scope(
                name=row.url.rsplit("/", 1)[-1], expected=1, listed=1, unique=1, unit="公告"
            )
            self.result.scopes.append(scope)
            catalog.details += 1
            try:
                if re.search(r"延期|延长|补充|更正|调整|暂停|取消", row.title):
                    raise CrawlError(
                        "unsupported_scope", "云投出现招聘范围变更公告，须核验原公告及附件"
                    )
                html = await browser.request_html(row.url)
                scope.evidence.append(browser.last_evidence)
                body, images, fingerprint = article(html, row)
                verified = IMAGE_NOTICES.get(scope.name)
                if verified is not None:
                    check(fingerprint == verified["fingerprint"], "云投图片公告文字或链接变化")
                    await self.verify_images(browser, scope, images, verified["images"])
                    end = datetime.fromisoformat(verified["deadline"])
                    expression = verified["expression"]
                else:
                    await self.verify_images(
                        browser, scope, images, TEXT_IMAGES.get(scope.name, [])
                    )
                    if re.search(r"报名.{0,8}(?:延期|延长)|(?:延期|延长).{0,8}报名", body):
                        raise CrawlError("unsupported_scope", "云投正文出现报名延期，须另核验")
                    end, expression = deadline(body)
                record.update(deadline=end.isoformat(), deadline_evidence=expression)
                if self.as_of.astimezone(TZ) < end:
                    raise CrawlError(
                        "unsupported_scope", "云投公告尚未截止，须展开岗位附件和申请目录"
                    )
                record["disposition"] = "报名已截止，岗位附件不进入当前校园岗位"
                scope.skipped_expired = 1
                scope.terminal = True
            except Exception as exc:
                record["disposition"] = "待核验"
                self.error(exc, row.url)
        catalog.terminal = True
        path = browser.output / "yuntou-notice-dispositions.json"
        write_json(path, records)
        catalog.evidence.append(str(path))

    async def verify_images(
        self,
        browser: BrowserSession,
        scope: Scope,
        images: list[str],
        expected: list[tuple[str, str]],
    ) -> None:
        check(images == [pair[0] for pair in expected], "云投正文图片集合变化或未经核验")
        for url, digest in expected:
            browser.consume_request()
            response = await browser.page.request.get(url, timeout=30000)
            check(response.status == 200, "云投图片读取失败")
            content = await response.body()
            check(hashlib.sha256(content).hexdigest() == digest, "云投图片正文变化，截止须重验")
            path = browser.output / f"yuntou-image-{digest}.bin"
            path.write_bytes(content)
            scope.evidence.append(str(path))
