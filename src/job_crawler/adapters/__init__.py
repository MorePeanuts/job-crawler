"""Explicit adapter registration; unknown sites never fall through to guessing."""

from job_crawler.adapters.ansteel import Ansteel
from job_crawler.adapters.hotjob import TENANTS as HOTJOB_TENANTS
from job_crawler.adapters.hzsteel import Hzsteel
from job_crawler.adapters.moka import TENANTS as MOKA_TENANTS
from job_crawler.adapters.platforms import CCB, CNPC, Alibaba, Pingan
from job_crawler.adapters.wtmec import Wtmec
from job_crawler.adapters.zhiye import TENANTS

REGISTRY = {
    adapter.name: adapter
    for adapter in (
        Pingan,
        CCB,
        CNPC,
        Alibaba,
        Wtmec,
        Hzsteel,
        Ansteel,
        *TENANTS,
        *HOTJOB_TENANTS,
        *MOKA_TENANTS,
    )
}
