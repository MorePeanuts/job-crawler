"""Ziroom's rendered 2027 campus cards and expandable descriptions."""

import hashlib
import re
from typing import cast

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession


class ZiroomCampus(Adapter):
    name = "ziroom-campus"
    host = "job.ziroom.com"
    path = "/campus/enter"
    scope_description = "自如 2027 秋招官网十个校园卡片逐个展开验证"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "自如校园页缺少浏览器")
        page = session.page
        listing = await page.evaluate(
            """() => ({
              expected: Number(document.querySelector('div.list > div > span')?.textContent),
              rows: [...document.querySelectorAll('div.list > ul > li')].map(li => ({
                title: li.querySelector('.profile h2')?.textContent?.trim() || '',
                location: [...li.querySelectorAll('.profile > span > span')]
                  .map(x => x.textContent.trim()).filter(Boolean).join('、')
              }))
            })"""
        )
        rows = listing["rows"]
        expected = listing["expected"]
        check(isinstance(expected, int) and expected > 0, "校园岗位总数无效")
        check(len(rows) == expected, "校园岗位卡片数与页面总数不符")
        scope = Scope(name="campus-ui-cards", expected=expected)
        self.result.scopes.append(scope)
        seen: set[str] = set()
        list_evidence = session.last_evidence
        for index, row in enumerate(rows):
            title = row["title"]
            location = row["location"]
            check(bool(title) and "2027秋招" in title, "校园卡片标题非当前秋招")
            key = hashlib.sha256(f"{title}\x1f{location}".encode()).hexdigest()[:20]
            check(key not in seen, "校园岗位标题地点组合重复")
            seen.add(key)
            scope.listed += 1
            scope.unique = len(seen)
            session.consume_request()
            await (
                page.locator("div.list > ul > li")
                .nth(index)
                .locator(".profile")
                .click(timeout=10000)
            )
            detail = await page.evaluate(
                """i => {
                  const li = document.querySelectorAll('div.list > ul > li')[i];
                  return { title: li?.querySelector('.profile h2')?.textContent?.trim() || '',
                    text: li?.querySelector('.details')?.innerText || '' };
                }""",
                index,
            )
            check(detail["title"] == title, "展开后岗位标题错配")
            body = detail["text"]
            evidence = session.output / f"ziroom-campus-{index + 1:02d}.json"
            write_json(
                evidence,
                {
                    "url": self.source.url,
                    "expected": expected,
                    "index": index + 1,
                    "title": title,
                    "location": location,
                    "expanded_text": body,
                    "listing_evidence": list_evidence,
                },
            )
            duty_marker = re.search(r"【岗位职责】|岗位职责：|工作职责：", body)
            requirement_marker = re.search(r"【岗位要求】|岗位要求：|任职资格：|任职要求：", body)
            check(
                duty_marker is not None
                and requirement_marker is not None
                and duty_marker.end() < requirement_marker.start(),
                "校园岗位展开正文缺少职责或要求",
            )
            assert duty_marker is not None and requirement_marker is not None
            duties = body[duty_marker.end() : requirement_marker.start()].strip()
            requirements = body[requirement_marker.end() :].split("立即投递", 1)[0].strip()
            check(bool(duties and requirements), "校园岗位展开正文为空")
            session.last_evidence = str(evidence)
            job = self.job(
                key,
                title=title,
                work_type="校招",
                source_url=self.source.url,
                location=location,
                duties=duties,
                requirements=requirements,
                field_sources={
                    "duties": "校园卡片展开正文【岗位职责】",
                    "requirements": "校园卡片展开正文【岗位要求】",
                    "location": "校园卡片工作地点",
                    "published": "source_missing",
                },
            )
            self.result.jobs.append(job)
            scope.details += 1
            scope.evidence.append(str(evidence))
        scope.terminal = True
