"""Guard the project's enterprise recruitment source boundary."""

from urllib.parse import urlsplit

NON_ENTERPRISE_HOSTS = {
    "job.xasyxy.com",
    "kmust.uat.bysjy.com.cn",
    "qz.hnrcsc.com",
}


def is_non_enterprise_source(url: str) -> bool:
    """Reject known school and public talent portals as company adapters."""
    host = (urlsplit(url).hostname or "").lower()
    return host.endswith(".edu.cn") or host in NON_ENTERPRISE_HOSTS
