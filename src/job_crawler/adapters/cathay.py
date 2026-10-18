"""Cathay's public iMatch graph and official campus campaigns."""

import json
from datetime import datetime
from typing import Any, cast
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from playwright.async_api import Error as PlaywrightError

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.cathay_data import (
    CAMPUS,
    CHANNEL,
    CHANNEL_PAGES,
    DETAIL_API,
    ENTRY,
    INFO,
    JAVA,
    LIST_API,
    MA,
    MA_PAGES,
    ROOT,
    campus_basis,
    campus_rows,
    catalog,
    detail,
    editorial,
    gateway,
    internship,
    job_fields,
    job_id,
    joint_deadline,
    links,
    scalar,
    short_link,
    unwrap,
)
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession, CrawlError

TRAINING_IDS = {"I00021731", "I00014277"}


def envelope(key: str) -> dict[str, object]:
    return {
        "MWHEADER": {
            "TXNSEQ": datetime.now().strftime("%Y%m%d%H%M%S%f")[:17] + "job",
            "MSGID": "EZM-C-JOBINFOQ001",
            "SOURCECHANNEL": "HRD-LX-FND-01",
        },
        "TRANRQ": {"APPL_FORM_NO": key},
    }


def dictionary(data: dict[str, Any]) -> dict[str, str]:
    rows = unwrap(data).get("i18nItems")
    check(isinstance(rows, list) and bool(rows), "国泰公开翻译字典缺失")
    assert isinstance(rows, list)
    result: dict[str, str] = {}
    for row in rows:
        check(isinstance(row, dict), "国泰翻译字典行不是对象")
        key, value = scalar(row, "key"), scalar(row, "value")
        check(bool(key) and key not in result, "国泰字典键为空或重复")
        result[key] = value
    check(
        result.get("COMMON_UI_JOB_ACCEPT_ROLE_2") == "應屆畢業生"
        and result.get("COMMON_UI_DTEZF041_EMP_TYPE_01") == "全職"
        and result.get("COMMON_UI_DTEZF041_EMP_TYPE_03") == "實習生",
        "国泰性质/应届枚举语义变化",
    )
    return result


def programme_pages(html: str, base: str, expected: set[str]) -> set[str]:
    urls = links(html, base)
    prefix = base.rsplit("/", 1)[0] + "/"
    pages = {u for u in urls if u.startswith(prefix) and u.endswith(".html") and u != base}
    check(pages == {prefix + name for name in expected}, "国泰专题子页面集合变化")
    return pages


class CathayIMatch(Adapter):
    name = "cathay-imatch-campus"
    host = "recruit.cathayholdings.com"
    path = "/iMatch/job/search"
    ready_endpoints = (LIST_API,)
    scope_description = (
        "国泰金控统一iMatch完整目录、官方校招/MA/通路专题及关联职位；正式全职应届岗位；"
        "不含CAP/CIP/资讯培训实习与集团其他独立系统"
    )

    @property
    def browser(self) -> BrowserSession:
        return cast(BrowserSession, self.session)

    def refs(self, name: str, keys: set[str], evidence: list[str]) -> None:
        check(bool(keys), "国泰专题未发现任何可核验职位引用")
        self.result.scopes.append(
            Scope(
                name=name,
                unit="职位引用",
                expected=len(keys),
                listed=len(keys),
                unique=len(keys),
                details=len(keys),
                terminal=True,
                evidence=evidence,
            )
        )

    async def campaigns(self) -> tuple[set[str], set[str], dict[str, list[str]]]:
        browser = self.browser
        keys: set[str] = set()
        campus: set[str] = set()
        provenance: dict[str, list[str]] = {}
        for name, base, pages in (
            ("campus", CAMPUS, set()),
            ("ma", MA, MA_PAGES),
            ("channel", CHANNEL, CHANNEL_PAGES),
        ):
            scope = Scope(
                name="cathay-programme-" + name, unit="专题", expected=1, listed=1, unique=1
            )
            self.result.scopes.append(scope)
            try:
                await browser.open(base)
                html = await browser.page.content()
                evidence = [browser.last_evidence]
                if name == "campus":
                    doc = BeautifulSoup(html, "html.parser")
                    scripts = [
                        urljoin(base, str(s["src"]))
                        for s in doc.select("script[src]")
                        if "/js/cathay" in urljoin(base, str(s["src"]))
                    ]
                    check(scripts == [CAMPUS + "js/cathay2026hr.js"], "国泰校招数据脚本变化")
                    rows = campus_rows(await browser.request_html(scripts[0], validate_html=False))
                    evidence.append(browser.last_evidence)
                    ids = {r["id"] for r in rows}
                    campus.update(ids)
                    p = browser.output / "cathay-campus-catalog.json"
                    write_json(p, rows)
                    evidence.append(str(p))
                else:
                    subs = programme_pages(html, base, pages)
                    ids = {job_id(u) for u in links(html, base) if job_id(u)}
                    for url in sorted(subs):
                        sub = await browser.request_html(url)
                        found = {job_id(u) for u in links(sub, url) if job_id(u)}
                        check(
                            bool(found)
                            or (name == "ma" and url.endswith("/qna.html") and "申請資格" in sub),
                            "国泰专题子页缺少职位链接",
                        )
                        ids.update(found)
                        evidence.append(browser.last_evidence)
                    if name == "ma":
                        campus.update(ids)
                self.refs("cathay-" + name + "-references", ids, evidence)
                for key in ids:
                    provenance.setdefault(key, []).extend(evidence)
                keys.update(ids)
                scope.details = 1
                scope.terminal = True
                scope.evidence = evidence
            except Exception as exc:
                self.error(exc, name)
        training = Scope(
            name="cathay-training-programme", unit="专题", expected=1, listed=1, unique=1
        )
        self.result.scopes.append(training)
        try:
            await browser.open(JAVA)
            html = await browser.page.content()
            check(
                "This site is currently suspended" in BeautifulSoup(html, "html.parser").get_text(),
                "国泰资讯培训入口状态变化，需重新核验正式/实习范围",
            )
            training.evidence.append(browser.last_evidence)
            # Its known public iMatch training records are also fetched below. The
            # suspended site is disclosed; it is never treated as a working empty board.
            training.skipped_out_of_scope = 1
            training.terminal = True
            keys.update(TRAINING_IDS)
        except Exception as exc:
            self.error(exc, "training")
        return keys, campus, provenance

    async def resolve(self, url: str) -> str:
        browser = self.browser
        browser.consume_request()
        browser.capture = False
        page = await browser.page.context.new_page()
        status: int | None = None
        try:
            try:
                response = await page.goto(url, wait_until="commit", timeout=30000)
                if response is not None:
                    status = response.status
                    check(status < 400, "国泰短链访问失败")
            except PlaywrightError:
                # Some public redirect chains interrupt the first navigation.
                # Completion still requires a known final URL and loaded DOM.
                pass
            await page.wait_for_function(
                "() => !['reurl.cc','pse.is'].includes(location.hostname) && "
                "!location.hostname.endsWith('.pse.is') && location.protocol==='https:'",
                timeout=25000,
            )
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            final = page.url
            check(bool(job_id(final)) or editorial(final), "国泰短链未到已验证职位或文章")
            p = browser.output / f"cathay-redirect-{browser.requests:05}.json"
            safe = (
                INFO + job_id(final)
                if job_id(final)
                else urlsplit(final)._replace(query="", fragment="").geturl()
            )
            write_json(p, {"url": url, "final_url": safe, "status": status})
            browser.last_evidence = str(p)
            return safe
        finally:
            await page.close()

    async def harvest(self) -> None:
        check(self.source.url == ENTRY, "国泰来源须为无筛选iMatch入口")
        browser = self.browser
        observed = await browser.observed_path(LIST_API)
        listing_evidence = browser.last_evidence
        listing = catalog(
            json.loads(observed["body"]),
            json.loads(observed["post_data"]),
            await browser.page.content(),
        )
        main = {scalar(row, "APPL_FORM_NO"): row for row in listing}
        self.refs("cathay-imatch-catalog", set(main), [listing_evidence])
        translation = await browser.observed_path("/api/Sys/GetTranslation")
        labels = dictionary(json.loads(translation["body"]))
        dictionary_evidence = browser.last_evidence
        extra, campus, provenance = await self.campaigns()
        known = set(main) | extra
        for key in main:
            provenance.setdefault(key, []).append(listing_evidence)
        await browser.open(ENTRY, ready_endpoints=self.ready_endpoints)
        bodies: dict[str, dict[str, Any]] = {}
        evidence: dict[str, str] = {}
        attempted: set[str] = set()
        redirects: dict[str, str] = {}
        redirect_evidence: dict[str, str] = {}
        edges: dict[str, set[str]] = {}
        records: dict[str, dict[str, object]] = {}
        master = Scope(name="cathay-unique-details", unit="唯一职位/目录")
        self.result.scopes.append(master)
        for _ in range(10):
            pending = sorted(known - attempted)
            check(len(known) <= 5000, "国泰关联目录超出5000项预算")
            if not pending:
                break
            for key in pending:
                attempted.add(key)
                try:
                    raw = await browser.request(
                        DETAIL_API,
                        payload=envelope(key),
                        headers={"Accept-Language": "zh_TW"},
                        detail=True,
                    )
                    bodies[key] = detail(raw, key, main.get(key))
                    evidence[key] = browser.last_evidence
                except Exception as exc:
                    self.error(exc, key)
            unresolved: dict[str, set[str]] = {}
            for key in pending:
                if key not in bodies:
                    continue
                body = bodies[key]
                try:
                    if scalar(body, "IS_OPEN") == "N" or internship(body) or key == "I00012494":
                        continue
                    content = (
                        scalar(body, "JOB_DESCRIPTION") + "\n" + scalar(body, "OTHER_CONDITION")
                    )
                    urls = links(content)
                    is_gateway = gateway(body)
                    check(not is_gateway or bool(urls), "国泰总览没有可展开链接")
                    link_scope = Scope(
                        name="cathay-links-" + key,
                        unit="正文链接",
                        expected=len(urls),
                        listed=len(urls),
                        unique=len(urls),
                        evidence=[evidence[key]],
                    )
                    if urls:
                        self.result.scopes.append(link_scope)
                    for url in sorted(urls):
                        target = job_id(url)
                        if target:
                            known.add(target)
                            edges.setdefault(key, set()).add(target)
                            link_scope.details += 1
                        elif short_link(url):
                            unresolved.setdefault(url, set()).add(key)
                        elif editorial(url) or url.rstrip("/") == ROOT:
                            link_scope.skipped_out_of_scope += 1
                        else:
                            self.error(
                                CrawlError("unsupported_scope", "国泰职位正文含未支持外部链接"), key
                            )
                    link_scope.terminal = True
                except Exception as exc:
                    self.error(exc, key)
            for url, parents in sorted(unresolved.items()):
                try:
                    if url not in redirects:
                        redirects[url] = await self.resolve(url)
                        redirect_evidence[url] = browser.last_evidence
                    final = redirects[url]
                    target = job_id(final)
                    for key in parents:
                        link_scope = next(
                            s for s in self.result.scopes if s.name == "cathay-links-" + key
                        )
                        link_scope.evidence.append(redirect_evidence[url])
                        if target:
                            known.add(target)
                            edges.setdefault(key, set()).add(target)
                            link_scope.details += 1
                        else:
                            link_scope.skipped_out_of_scope += 1
                except Exception as exc:
                    self.error(exc, ",".join(sorted(parents)))
            if unresolved:
                await browser.open(ENTRY, ready_endpoints=self.ready_endpoints)
        check(known <= attempted, "国泰关联图未遍历完成")
        # Propagate explicit campus directory membership before choosing jobs; a
        # child may already have been encountered in the main all-jobs catalogue.
        for _ in range(len(edges) + 1):
            inherited = set(campus)
            for parent, children in edges.items():
                body = bodies[parent]
                if gateway(body) and (parent in campus or campus_basis(body)):
                    inherited.update(children)
            if inherited == campus:
                break
            campus = inherited
        master.expected = master.listed = master.unique = len(known)
        for key in sorted(known):
            record: dict[str, object] = {"id": key, "disposition": "待核验"}
            records[key] = record
            if key not in bodies:
                continue
            body = bodies[key]
            record.update(
                title=scalar(body, "JOB_TITLE"),
                updated_raw=scalar(body, "UPD_DATE"),
                evidence=evidence[key],
                linked_ids=sorted(edges.get(key, set())),
            )
            master.evidence.append(evidence[key])
            try:
                if key in TRAINING_IDS:
                    check(internship(body), "国泰资讯培训性质改变")
                if scalar(body, "IS_OPEN") == "N":
                    master.skipped_closed += 1
                    record["disposition"] = "IS_OPEN=N，已关闭"
                elif internship(body):
                    master.skipped_out_of_scope += 1
                    record["disposition"] = "实习/工读/临时约聘"
                elif key == "I00012494":
                    cutoff = joint_deadline(body)
                    check(self.as_of >= cutoff, "国泰联合招募仍开放，需要展开四职系实际岗位")
                    master.skipped_expired += 1
                    record.update(disposition="联合招募报名批次已截止", deadline=cutoff.isoformat())
                elif gateway(body):
                    master.details += 1
                    record["disposition"] = "职位总览已展开，不输出虚构岗位"
                else:
                    basis = "官方校招专题/应届目录归属" if key in campus else campus_basis(body)
                    if not basis:
                        master.skipped_out_of_scope += 1
                        record["disposition"] = "综合目录无明确应届资格"
                        continue
                    record["campus_basis"] = basis
                    fields = job_fields(body, labels)
                    fingerprint = {"detail": body, "campus_basis": basis, "fields": fields}
                    cached = self.before_detail(key, fingerprint, master, evidence=evidence[key])
                    if cached is not None:
                        self.result.jobs.extend(cached)
                        record["disposition"] = "公共增量字段复用，本轮重新核验开放状态"
                        continue
                    job = self.job(key, source_url=INFO + key, apply_url=INFO + key, **fields)
                    job.evidence = list(
                        dict.fromkeys(
                            [evidence[key], dictionary_evidence, *provenance.get(key, [])]
                        )
                    )
                    job.field_sources = {
                        "title": "TRANRS.JOB_TITLE",
                        "unit": "TRANRS.COMPANY_NAME + GetTranslation",
                        "duties": "TRANRS.JOB_DESCRIPTION",
                        "requirements": "TRANRS.OTHER_CONDITION/DEG_COND/MAJ/EXP/LNG/KNS/LIT/ACCEPT_ROLE",
                        "education": "TRANRS.DEG_COND",
                        "location": "TRANRS.LOCATION_NAME",
                        "address": "TRANRS.WORK_LOCATION_MEMO",
                        "published": "未提供；UPD_DATE为更新日期",
                        "deadline": "公开正文报名截止文字；未提供留空",
                        "work_type": basis,
                    }
                    self.result.jobs.append(job)
                    self.remember(key, fingerprint, [job])
                    master.details += 1
                    record["disposition"] = "开放正式应届岗位"
            except Exception as exc:
                self.error(exc, key)
        master.terminal = True
        p = browser.output / "cathay-dispositions.json"
        write_json(p, list(records.values()))
        master.evidence.append(str(p))
