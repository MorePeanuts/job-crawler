"""Explicit adapter registration; unknown sites never fall through to guessing."""

from job_crawler.adapters.ansteel import Ansteel
from job_crawler.adapters.bankcomm import BankComm
from job_crawler.adapters.bilibili import Bilibili
from job_crawler.adapters.byd import BYDCampus
from job_crawler.adapters.campaign51 import TENANTS as CAMPAIGN51_TENANTS
from job_crawler.adapters.coapi51 import TENANTS as COAPI51_TENANTS
from job_crawler.adapters.feishu import Desaysv
from job_crawler.adapters.hotjob import TENANTS as HOTJOB_TENANTS
from job_crawler.adapters.hzsteel import Hzsteel
from job_crawler.adapters.jd import JD
from job_crawler.adapters.lenovo import Lenovo
from job_crawler.adapters.meituan import Meituan
from job_crawler.adapters.moka import TENANTS as MOKA_TENANTS
from job_crawler.adapters.platforms import CCB, CNPC, Alibaba, Pingan
from job_crawler.adapters.sf import SF
from job_crawler.adapters.tcl import TCLCampus
from job_crawler.adapters.tencent import Tencent
from job_crawler.adapters.wtmec import Wtmec
from job_crawler.adapters.zhaopin import TENANTS as ZHAOPIN_TENANTS
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
        Lenovo,
        Desaysv,
        JD,
        Tencent,
        SF,
        BankComm,
        Meituan,
        Bilibili,
        BYDCampus,
        TCLCampus,
        *CAMPAIGN51_TENANTS,
        *COAPI51_TENANTS,
        *TENANTS,
        *HOTJOB_TENANTS,
        *MOKA_TENANTS,
        *ZHAOPIN_TENANTS,
    )
}
