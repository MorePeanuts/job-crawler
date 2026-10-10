"""Conservative, quote-backed education and workplace-address extraction."""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from job_crawler.models import Job

EDUCATION_ALIASES = {
    "大专": "大专",
    "大学专科": "大专",
    "专科": "大专",
    "本科": "本科",
    "大学本科": "本科",
    "硕士": "硕士",
    "硕士研究生": "硕士",
    "博士": "博士",
    "博士研究生": "博士",
}
RANK = {"大专": 0, "本科": 1, "硕士": 2, "博士": 3}
DEGREE = r"博士研究生|硕士研究生|大学本科|大学专科|博士|硕士|本科|大专|专科|研究生"
MINIMUM = re.compile(
    rf"(?P<degree>{DEGREE})(?:[（(]含[）)])?(?:及其|及|以及|或|或者)?以上(?:的)?(?:学历|学位)?"
)
DIRECT = re.compile(
    rf"(?P<degree>{DEGREE})(?:的)?(?:学历|学位|应届毕业生|应届生|毕业生|应届|毕业|在读)"
)
SHORT_REQUIREMENT = re.compile(
    rf"(?:^\s*(?:\d+[.、)）]\s*)?(?:20\d{{2}}\s*届)?\s*(?:应届)?|相关专业)(?P<degree>{DEGREE})(?:生)?\s*$"
)
ELIGIBLE_LIST = re.compile(
    rf"^\s*(?:\d+[.、)）]\s*)?(?:20\d{{2}}\s*届)?\s*(?:应届)?"
    rf"(?:{DEGREE})(?:生)?(?:\s*[/、,，或]\s*(?:{DEGREE})(?:生)?)+\s*$"
)
CONTEXT_LIST = re.compile(
    rf"(?:相关(?:专业|领域|方向)(?:的)?|应届)\s*(?:在读|优秀)?"
    rf"(?:{DEGREE})(?:生)?(?:\s*(?:[/、,，]|或(?:者)?|及|和)\s*(?:顶尖|优秀)?"
    rf"(?:{DEGREE})(?:生)?)*\s*$"
)
ENGLISH_DEGREE = re.compile(r"\b(Bachelor|Master)(?:['’]s)?(?:\s+degree)?|\bPh\.?D\b", re.I)
ENGLISH_START = re.compile(
    r"^\s*(?:\d+[-.、]?\s*)?(?:Education\s*[:：]\s*)?"
    r"(?:Pursuing\s+(?:a|an)\s+)?(?:a\s+)?(?:Bachelor|Master|Ph\.?D)\b",
    re.I,
)
LOWER_BOUND = re.compile(
    rf"(?:学历(?:要求)?(?:为|不低于|至少)|最低学历(?:要求)?[为：:]?)[\s]*(?P<degree>{DEGREE})"
)
PREFERENCE = re.compile(r"优先|优选|加分|更佳|尤佳|优才|免.{0,5}(?:笔试|考试)")
EXCEPTION = re.compile(
    r"放宽|降低|破格|不受.{0,5}限制|不限学历|学历不限|(?:学历|学位).{0,3}不做要求|也可考虑|部分.{0,12}要求"
)
ADDRESS_LABEL = re.compile(r"(?:工作地址|办公地址|办公地点|工作地点)[：:]\s*([^\r\n。；;]+)")
ADDRESS_DETAIL = re.compile(
    r"(?:路|街|大道|巷|弄).{0,15}[0-9一二三四五六七八九十]+号|大厦|大楼|产业园|科技园|工业园|校区|园区|厂区"
)


@dataclass(frozen=True)
class FieldDecision:
    value: str
    status: str
    source: str = ""
    quote: str = ""


def education_clauses(sentence: str) -> list[str]:
    """Keep commas only inside adjacent degree lists, not later study/background clauses."""
    clauses: list[str] = []
    start = 0
    for separator in re.finditer(r"[，,]+", sentence):
        before = sentence[start : separator.start()]
        after = sentence[separator.end() :]
        if re.search(rf"(?:{DEGREE})(?:生)?\s*$", before) and re.match(
            rf"\s*(?:{DEGREE})(?:[，,/、或]|学历|学位|毕业生|应届|生|\s|$)", after
        ):
            continue
        clauses.append(before)
        start = separator.end()
    clauses.append(sentence[start:])
    return clauses


def education_decision(
    job: Job, policy: Literal["minimum_eligible", "explicit_only"] = "minimum_eligible"
) -> FieldDecision:
    aliases = dict(EDUCATION_ALIASES)
    if policy == "minimum_eligible":
        aliases["研究生"] = "硕士"
    raw = job.education.strip()
    if raw:
        if raw in aliases:
            return FieldDecision(aliases[raw], "structured_single", "education", raw)
        tokens = re.split(r"[,，、/或]+", raw)
        if (
            policy == "minimum_eligible"
            and len(tokens) > 1
            and all(
                t.strip() in aliases or (t.strip() == "高职" and "大专" in tokens) for t in tokens
            )
        ):
            values = [aliases[t.strip()] for t in tokens if t.strip() in aliases]
            return FieldDecision(
                min(values, key=RANK.__getitem__), "structured_minimum", "education", raw
            )
        return FieldDecision(raw, "structured_requires_mapping", "education", raw)
    candidates: list[FieldDecision] = []
    mentioned = False
    ambiguous = False
    for field in ("requirements", "duties"):
        text = getattr(job, field)
        mentioned |= bool(re.search(rf"{DEGREE}|研究生|学历|[Bb]achelor|[Mm]aster|PhD", text))
        # Keep a full sentence together to detect exceptions and parallel degree choices.
        for sentence in re.split(r"[\n\r。；;]+", text):
            if field == "requirements" and ENGLISH_START.search(sentence):
                english = list(ENGLISH_DEGREE.finditer(sentence))
                if english and not re.search(
                    r"preferred|preference|plus|advantage",
                    sentence[: english[-1].end() + 15],
                    re.I,
                ):
                    degrees = {
                        "本科"
                        if m[0].lower().startswith("bachelor")
                        else "硕士"
                        if m[0].lower().startswith("master")
                        else "博士"
                        for m in english
                    }
                    if policy == "explicit_only" and len(degrees) > 1:
                        ambiguous = True
                    else:
                        candidates.append(
                            FieldDecision(
                                min(degrees, key=RANK.__getitem__),
                                "explicit_english",
                                field,
                                sentence.strip(),
                            )
                        )
            if not re.search(DEGREE, sentence):
                continue
            if field == "duties" and not re.search(
                r"招聘对象|学历要求|任职要求|任职资格|面向.+(?:应届|毕业生)", sentence
            ):
                continue
            if EXCEPTION.search(sentence):
                ambiguous = True
                continue
            clauses = education_clauses(sentence)
            for clause in clauses:
                clean = re.sub(r"[（(][^()（）]*(?:优先|优选|加分)[^()（）]*[）)]", "", clause)
                clean = re.sub(rf"(?:{DEGREE})(?:学历|学位)?(?:者)?优先", "", clean)
                found = list(MINIMUM.finditer(clean))
                found = [
                    m
                    for m in found
                    if not PREFERENCE.search(clean[: m.start()])
                    and not re.match(r"\s*(?:者|人才)?(?:优先|优选|加分)", clean[m.end() :])
                ]
                if not found:
                    if PREFERENCE.search(clean):
                        continue
                    found = (
                        list(LOWER_BOUND.finditer(clean))
                        or list(DIRECT.finditer(clean))
                        or list(SHORT_REQUIREMENT.finditer(clean))
                        or list(ELIGIBLE_LIST.finditer(clean))
                        or list(CONTEXT_LIST.finditer(clean))
                    )
                if not found:
                    continue
                degree_words = [m[0] for m in re.finditer(DEGREE, clean)]
                if any(word not in aliases for word in degree_words):
                    ambiguous = True
                    continue
                degrees = {aliases[word] for word in degree_words}
                if len(degrees) != 1 and policy == "explicit_only":
                    ambiguous = True
                    continue
                if found:
                    # Alma mater / age / exemption rules do not establish job eligibility.
                    if re.search(
                        r"年龄|岁|毕业院校|本科阶段|本科期间|(?:学科|专业)背景|免予|免试", clause
                    ):
                        continue
                    candidates.append(
                        FieldDecision(
                            min(degrees, key=RANK.__getitem__),
                            "text_minimum" if len(degrees) > 1 else "explicit_text",
                            field,
                            clause.strip(),
                        )
                    )
    values = {candidate.value for candidate in candidates}
    if ambiguous or len(values) > 1:
        return FieldDecision("", "ambiguous_or_conditional")
    if len(values) == 1:
        return candidates[0]
    return FieldDecision("", "mentioned_not_explicit" if mentioned else "not_in_saved_text")


def address_decision(job: Job) -> FieldDecision:
    if job.address.strip():
        return FieldDecision(job.address, "structured_address", "address", job.address)
    candidates: list[FieldDecision] = []
    for field in ("requirements", "duties"):
        for match in ADDRESS_LABEL.finditer(getattr(job, field)):
            value = match[1].strip()
            if ADDRESS_DETAIL.search(value):
                candidates.append(FieldDecision(value, "explicit_workplace", field, match[0]))
    if len({c.value for c in candidates}) == 1:
        return candidates[0]
    if candidates:
        return FieldDecision("", "multiple_workplace_addresses")
    return FieldDecision("", "no_job_address_in_saved_fields")


def enrich_fields(
    job: Job, policy: Literal["minimum_eligible", "explicit_only"] = "minimum_eligible"
) -> Job:
    result = job.model_copy(deep=True)
    for field, decision in (
        ("education", education_decision(job, policy)),
        ("address", address_decision(job)),
    ):
        setattr(result, field, decision.value)
        if getattr(job, field) == decision.value and job.field_sources.get(field):
            continue
        result.field_sources[f"{field}_status"] = decision.status
        if decision.value and decision.quote:
            result.field_sources[field] = (
                f"rule:{decision.status};field:{decision.source};quote:{decision.quote}"
            )
    return result


def field_audit(originals: dict[str, Job], jobs: list[Job]) -> dict[str, object]:
    """Describe exported/reviewed fields without changing the stored source jobs."""
    summary: dict[str, object] = {}
    for field in ("education", "address"):
        summary[field] = {
            "before_nonempty": sum(bool(getattr(originals[j.key], field)) for j in jobs),
            "after_nonempty": sum(bool(getattr(j, field)) for j in jobs),
            "changed": sum(getattr(originals[j.key], field) != getattr(j, field) for j in jobs),
            "statuses": dict(
                Counter(j.field_sources.get(f"{field}_status", "unknown") for j in jobs)
            ),
        }
    return {
        "scope": "本次导入或待补全的岗位；不包含已排除岗位。空值不代表整个网站未提供。",
        "summary": summary,
        "records": [
            {
                "key": job.key,
                "company": job.company,
                "title": job.title,
                "evidence": job.evidence,
                "fields": {
                    field: {
                        "original": getattr(originals[job.key], field),
                        "value": getattr(job, field),
                        "status": job.field_sources.get(f"{field}_status", "unknown"),
                        "provenance": job.field_sources.get(field, ""),
                    }
                    for field in ("education", "address")
                },
            }
            for job in jobs
        ],
    }
