"""Validated public iMatch fields and literal campaign catalogues (SPEC-234)."""

import json
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from job_crawler.adapters.base import text
from job_crawler.adapters.platforms import check

HOST = "recruit.cathayholdings.com"
ROOT = f"https://{HOST}"
ENTRY = ROOT + "/iMatch/job/search"
CAMPUS = "https://toucherfb.com/cathayholdings/recruit/"
MA = "https://ma.cathayholdings.com/index.html"
CHANNEL = ROOT + "/iMatch/channel/index.html"
JAVA = "https://javatraining.cathayholdings.com/"
INFO = ROOT + "/iMatch/job/info/"
LIST_API = "/api/job/EZM-C-JOBLISTQ001"
DETAIL_API = ROOT + "/api/job/EZM-C-JOBINFOQ001?msgHidden=true"
ID = re.compile(r"I{1,2}\d{8}")
FILTERS: dict[str, object] = {
    "LOCATION_PARENT_ID": "",
    "LOCATION_ID_LIST": [],
    "COMPANY_LIST": [],
    "JOB_TYPE": "",
    "EMPLOYMENT_TYPE": "",
    "WORKED_YEARS_CONDITION": "",
    "EDU_DEGREE_CONDITION": "",
    "KEYWORD": "",
}
NAV = {
    CAMPUS.rstrip("/"): "國泰校園徵才",
    MA: "國泰儲備幹部計畫",
    JAVA.rstrip("/"): "國泰資訊人才培育計畫",
    "https://toucherfb.com/cathayholdings/internship/CAP.htm": "國泰大 CAP 實習生計畫",
    "https://toucherfb.com/cathayholdings/internship/CIPjobs.htm": "國泰 CIP (暑期) 實習生計畫",
    CHANNEL: "國泰世華通路人員招募",
}
MA_PAGES = {"gma-feature.html", "cma-feature.html", "cim-feature.html", "qna.html"}
CHANNEL_PAGES = {"sfa.html", "rm.html", "op.html", "ps.html", "rrm.html", "arm.html", "cia.html"}


def scalar(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    check(value is None or isinstance(value, str), f"国泰字段{key}不是文本")
    return (value or "").replace("\\n", "\n").strip()


def strings(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    check(value is None or isinstance(value, list), f"国泰字段{key}不是数组")
    check(all(isinstance(x, str) for x in value or []), f"国泰字段{key}数组结构变化")
    return value or []


def unwrap(data: dict[str, Any]) -> dict[str, Any]:
    header = data.get("MWHEADER")
    check(isinstance(header, dict) and header.get("RETURNCODE") == "0000", "国泰接口业务失败")
    body = data.get("TRANRS")
    check(isinstance(body, dict), "国泰接口TRANRS缺失")
    assert isinstance(body, dict)
    return body


def job_id(url: str) -> str:
    p = urlsplit(url)
    if p.hostname != HOST or p.scheme != "https":
        return ""
    match = re.fullmatch(r"/iMatch/job/info/(I{1,2}\d{8})/?", p.path)
    if match:
        return match[1]
    if p.path == "/CathaybkHR/servlet/HttpDispatcher/EZA0_0320/jobDetail":
        ids = parse_qs(p.query).get("applFormNo", [])
        check(len(ids) == 1 and ID.fullmatch(ids[0]) is not None, "国泰旧详情ID缺失")
        return ids[0]
    return ""


def links(html: str, base: str = ENTRY) -> set[str]:
    doc = BeautifulSoup(html, "html.parser")
    urls = {str(a["href"]).strip() for a in doc.select("a[href]")}
    urls.update(re.findall(r'https?://[^\s<>"，。；）)】」』]+', doc.get_text(" ")))
    return {urljoin(base, u).rstrip(".,；。") for u in urls if u and not u.startswith("#")}


def short_link(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    return host in {"reurl.cc", "pse.is"} or host.endswith(".pse.is")


def editorial(url: str) -> bool:
    p = urlsplit(url)
    return p.hostname in {"vocus.cc", "www.bnext.com.tw"} and p.path.startswith("/article/")


def catalog(data: dict[str, Any], request: dict[str, Any], html: str) -> list[dict[str, Any]]:
    check(request.get("TRANRQ") == FILTERS, "国泰目录带有局部筛选或未知参数")
    body = unwrap(data)
    check(set(body) == {"JOB_LIST"}, "国泰目录出现未知分页/总数字段")
    rows = body["JOB_LIST"]
    check(isinstance(rows, list) and len(rows) <= 5000, "国泰目录结构或上限变化")
    ids: set[str] = set()
    for row in rows:
        check(isinstance(row, dict), "国泰目录行不是对象")
        key = scalar(row, "APPL_FORM_NO")
        check(ID.fullmatch(key) is not None and key not in ids, "国泰目录ID无效或重复")
        check(bool(scalar(row, "JOB_TITLE")), "国泰目录岗位标题缺失")
        ids.add(key)
    doc = BeautifulSoup(html, "html.parser")
    totals = re.findall(r"共計\s*(\d+)\s*筆資料", doc.get_text(" "))
    check(bool(totals) and {int(x) for x in totals} == {len(rows)}, "国泰DOM总数与完整数组不符")
    anchors = doc.select('a[href*="toucherfb.com/cathayholdings/recruit"]')
    check(bool(anchors), "国泰专题导航缺失")
    for a in anchors:
        container = a.find_parent("ul")
        check(container is not None, "国泰专题导航边界变化")
        assert container is not None
        nav = {
            urljoin(ENTRY, str(n["href"])).rstrip("/"): n.get_text(" ", strip=True)
            for n in container.select("a[href]")
        }
        check(nav == NAV, "国泰专题导航集合或招聘类型改变")
    return rows


def campus_rows(script: str) -> list[dict[str, str]]:
    blobs = re.findall(r"\bvar\s+jobs\s*=\s*(\{.*?\n\});", script, re.S)
    check(len(blobs) == 1, "国泰校招jobs完整字面量缺失")
    blob = re.sub(r"(\[)\s*//[^\n]*", r"\1", blobs[0])
    blob = re.sub(r"(?m)^\s*//[^\n]*", "", blob)
    blob = re.sub(r"([,{])\s*(students|company|title|url)\s*:", r'\1"\2":', blob)
    blob = re.sub(r",\s*([}\]])", r"\1", blob)
    parsed = json.loads(blob)
    check(
        isinstance(parsed, dict) and set(parsed) == {"MT", "DT", "OP", "FIA", "SE"},
        "国泰校招职系变化",
    )
    result: list[dict[str, str]] = []
    for category, rows in parsed.items():
        check(isinstance(rows, list) and bool(rows), "国泰校招职系为空或结构变化")
        for row in rows:
            check(
                isinstance(row, dict) and set(row) <= {"students", "company", "title", "url"},
                "国泰校招行字段变化",
            )
            check(all(isinstance(v, str) for v in row.values()), "国泰校招行不是文本")
            check(all(row.get(k) for k in ("company", "title", "url")), "国泰校招行缺少字段")
            key = job_id(row["url"])
            check(bool(key), "国泰校招链接不是已验证详情")
            result.append({**row, "category": category, "id": key})
    check(
        0 < len(result) <= 1000 and len({x["id"] for x in result}) == len(result),
        "国泰校招ID重复或数量未知",
    )
    return result


def detail(data: dict[str, Any], key: str, listing: dict[str, Any] | None) -> dict[str, Any]:
    body = unwrap(data)
    check(scalar(body, "APPL_FORM_NO") == key, "国泰详情ID错配")
    check(bool(scalar(body, "JOB_TITLE")), "国泰详情标题缺失")
    check(scalar(body, "IS_OPEN") in {"Y", "N"}, "国泰详情开放状态未知")
    if listing:
        check(scalar(body, "JOB_TITLE") == scalar(listing, "JOB_TITLE"), "国泰列表详情标题变化")
        check(
            scalar(body, "COMPANY_NAME") == scalar(listing, "COMPANY_NAME"), "国泰列表详情主体错配"
        )
        check(
            scalar(body, "EMPLOYMENT_TYPE_DESC") == scalar(listing, "EMPLOYMENT_TYPE_DESC"),
            "国泰列表详情性质变化",
        )
    check(bool(scalar(body, "JOB_DESCRIPTION")), "国泰详情职责为空")
    check(
        not BeautifulSoup(
            scalar(body, "JOB_DESCRIPTION") + scalar(body, "OTHER_CONDITION"), "html.parser"
        ).select("img,iframe,object,embed"),
        "国泰详情有未处理附件或图片",
    )
    return body


def internship(body: dict[str, Any]) -> bool:
    kind = scalar(body, "EMPLOYMENT_TYPE_DESC")
    check(kind in {f"COMMON_UI_DTEZF041_EMP_TYPE_0{x}" for x in range(1, 6)}, "国泰聘用性质未知")
    title = scalar(body, "JOB_TITLE")
    if kind.endswith(("_02", "_03", "_04")) or re.search(r"實習|工讀|intern", title, re.I):
        return True
    check(kind.endswith("_01"), "国泰其他聘用性质无法归为正式或实习")
    return False


def campus_basis(body: dict[str, Any]) -> str:
    if "COMMON_UI_JOB_ACCEPT_ROLE_2" in strings(body, "ACCEPT_ROLE_DESC_LIST"):
        return "ACCEPT_ROLE_DESC_LIST=應屆畢業生"
    title = scalar(body, "JOB_TITLE")
    if re.search(r"校園徵才|應屆畢業|新鮮人", title):
        return "JOB_TITLE明确校招/应届"
    for line in text(
        scalar(body, "JOB_DESCRIPTION") + "\n" + scalar(body, "OTHER_CONDITION")
    ).splitlines():
        if not re.search(r"應屆|新鮮人", line):
            continue
        check(
            not re.search(r"不(?:接受|招收|歡迎)|非應屆|不適合", line),
            "国泰应届资格存在否定，需核验",
        )
        return line
    return ""


def gateway(body: dict[str, Any]) -> bool:
    value = "\n".join(scalar(body, k) for k in ("JOB_TITLE", "JOB_DESCRIPTION", "OTHER_CONDITION"))
    return re.search(r"職[缺務]總覽|總覽頁|勿在此頁投遞", value) is not None


def joint_deadline(body: dict[str, Any]) -> datetime:
    value = scalar(body, "OTHER_CONDITION")
    years = re.findall(r"(20\d{2})年\d{1,2}-\d{1,2}月聯合招募", value)
    matches = re.findall(r"履歷投遞區間落在(?:現在|\d{1,2}/\d{1,2})-(\d{1,2})/(\d{1,2})\)", value)
    check(
        len(years) == 1 and len(matches) == value.count("履歷投遞區間") and bool(matches),
        "国泰联合招募报名日期缺失或无法解析",
    )
    check(not re.search(r"延長|延期|延後", value), "国泰联合招募出现延期声明")
    return max(
        datetime(int(years[0]), int(m), int(d), tzinfo=ZoneInfo("Asia/Shanghai"))
        for m, d in matches
    ) + timedelta(days=1)


def translated(value: str, dictionary: dict[str, str]) -> str:
    check(value in dictionary and bool(dictionary[value]), f"国泰枚举未识别：{value}")
    return dictionary[value]


def job_fields(body: dict[str, Any], dictionary: dict[str, str]) -> dict[str, str]:
    conditions: list[str] = []
    for key, label in (("DEG_COND", "學歷"), ("OTHER_CONDITION", "其他條件")):
        if scalar(body, key):
            conditions.append(label + "：" + text(scalar(body, key)))
    years = scalar(body, "WORKED_YEARS_CONDITION")
    if years:
        check(re.fullmatch(r"\d+", years) is not None, "国泰最低年资格式变化")
        conditions.append("最低工作年資：" + years + "年以上")
    for key, label in (
        ("MAJ_COND_LIST", "科系"),
        ("EXP_COND_LIST", "產業經驗"),
        ("KNS_COND_Y_LIST", "必備技能"),
        ("KNS_COND_N_LIST", "加分技能"),
        ("LIT_COND_Y_LIST", "必備證照"),
        ("LIT_COND_N_LIST", "加分證照"),
    ):
        values = strings(body, key)
        if values:
            conditions.append(label + "：" + "、".join(values))
    for key, label in (("LNG_COND_Y_LIST", "必備語言"), ("LNG_COND_N_LIST", "加分語言")):
        values = body.get(key)
        check(values is None or isinstance(values, list), "国泰语言条件不是数组")
        for value in values or []:
            check(isinstance(value, dict), "国泰语言条件不是对象")
            check(
                bool(scalar(value, "LANG_NAME")) and bool(scalar(value, "LANG_LEVEL_NAME")),
                "国泰语言条件不完整",
            )
            conditions.append(
                label + "：" + scalar(value, "LANG_NAME") + " " + scalar(value, "LANG_LEVEL_NAME")
            )
    roles = strings(body, "ACCEPT_ROLE_DESC_LIST")
    if roles:
        conditions.append("接受身分：" + "、".join(translated(v, dictionary) for v in roles))
    duties = text(scalar(body, "JOB_DESCRIPTION"))
    requirements = "\n".join(conditions)
    dates = [
        line
        for line in (duties + "\n" + requirements).splitlines()
        if re.search(
            r"(?:履歷|報名|招募|應徵|收件|申請).{0,20}(?:截止|截至|期限)|(?:收件|報名)至", line
        )
    ]
    return {
        "title": scalar(body, "JOB_TITLE"),
        "unit": translated(scalar(body, "COMPANY_NAME"), dictionary),
        "category_raw": translated(scalar(body, "JOB_TYPE_DESC"), dictionary),
        "education": scalar(body, "DEG_COND"),
        "location": scalar(body, "LOCATION_NAME"),
        "address": scalar(body, "WORK_LOCATION_MEMO"),
        "duties": duties,
        "requirements": requirements,
        "published": "",
        "deadline": "\n".join(dates),
    }
