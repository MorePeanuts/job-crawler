"""Recognize explicit section headings without splitting ordinary prose."""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

Section = Literal["duties", "requirements"]
DUTIES = (
    "岗位职责",
    "工作职责",
    "职位职责",
    "职位描述",
    "主要工作职责",
    "主要职责",
    "岗位内容",
    "岗位描述",
    "工作内容",
)
REQUIREMENTS = (
    "任职要求",
    "任职资格",
    "岗位要求",
    "应聘条件",
    "任职条件",
    "职位要求",
    "应聘要求",
    "基本要求",
    "工作要求",
)
SPACE = r"[\s\u200b\ufeff]*"
LABEL = "(?:" + "|".join((*DUTIES, *REQUIREMENTS)) + ")"
NUMBER = r"(?:[一二三四五六七八九十0-9]+[、.．][ \t]*)?"
# These bilingual headings occur in public Moka descriptions. Do not accept
# arbitrary suffixes (e.g. 工作职责1) as a complete heading.
TRANSLATION = r"(?:[ \t]*(?:Responsibilities|Requirements|Qualifications))?"
SUFFIX = r"(?:说明|如下)?"
WRAPPED = "|".join(
    re.escape(left)
    + SPACE
    + NUMBER
    + LABEL
    + SUFFIX
    + TRANSLATION
    + SPACE
    + r"[:：;；]?"
    + SPACE
    + re.escape(right)
    for left, right in (("【", "】"), ("[", "]"), ("（", "）"), ("(", ")"), ("<", ">"))
)
HEADING = re.compile(
    rf"(?:{WRAPPED}){SPACE}[:：;；]?"
    rf"|(?:^|(?<=[。；;]))[ \t\u200b\ufeff]*{NUMBER}[【\[（(<]?{SPACE}{LABEL}{SUFFIX}{TRANSLATION}"
    rf"[ \t\u200b\ufeff]*[】\]）)>]?[ \t\u200b\ufeff]*"
    rf"(?:[:：;；]|(?=\r?$)){SPACE}[:：;；]?",
    re.MULTILINE | re.IGNORECASE,
)
LABEL_PATTERN = re.compile(LABEL)
REFERENCE = re.compile(r"(?:根据|按照|参见|参考|详见|阅读|查看|履行|满足|符合|遵循|遵守)\s*$")


@dataclass(frozen=True)
class Heading:
    start: int
    end: int
    section: Section


def headings(body: str) -> Iterator[Heading]:
    for match in HEADING.finditer(body):
        if REFERENCE.search(body[max(0, match.start() - 12) : match.start()]):
            continue
        label = LABEL_PATTERN.search(match[0])
        assert label is not None
        yield Heading(
            match.start(), match.end(), "duties" if label[0] in DUTIES else "requirements"
        )


def strip_heading(body: str, section: Section) -> str:
    """Only strip leading headings belonging to this already structured field."""
    while True:
        heading = next(headings(body), None)
        if heading is None or body[: heading.start].strip() or heading.section != section:
            return body
        body = body[heading.end :].strip()


def clean_field_headings(body: str) -> str:
    """Keep structured-field ownership; remove explicit headings at line starts.

    Sites sometimes put a duties heading in their requirements field. Do not
    move the actual requirements on that basis, or remove inline references.
    """
    matches = [
        heading
        for heading in headings(body)
        if not body[body.rfind("\n", 0, heading.start) + 1 : heading.start].strip()
    ]
    if not matches:
        return body
    for heading in reversed(matches):
        body = body[: heading.start] + body[heading.end :]
    return body.strip()


def split_sections(
    body: str, *, unheaded_duties: bool = True, include_preamble: bool = True
) -> tuple[str, str]:
    """Consume whole headings, including bracket pairs separated by HTML newlines."""
    matches = list(headings(body))
    if not matches:
        return (body, "") if unheaded_duties else ("", "")
    values: dict[Section, list[str]] = {"duties": [], "requirements": []}
    prefix = body[: matches[0].start].strip()
    if prefix and include_preamble:
        # Introductory text is source content too; never silently discard it.
        values["duties"].append(prefix)
    for index, heading in enumerate(matches):
        end = matches[index + 1].start if index + 1 < len(matches) else len(body)
        value = body[heading.end : end].strip()
        if value:
            values[heading.section].append(value)
    return "\n".join(values["duties"]), "\n".join(values["requirements"])
