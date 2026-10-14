"""Explicit adapter registration; unknown sites never fall through to guessing."""

from job_crawler.adapters.anker import AnkerCampus
from job_crawler.adapters.ansteel import Ansteel
from job_crawler.adapters.bank_catalogs import TENANTS as BANK_TENANTS
from job_crawler.adapters.bankcomm import BankComm
from job_crawler.adapters.bilibili import Bilibili
from job_crawler.adapters.byd import BYDCampus
from job_crawler.adapters.campaign51 import TENANTS as CAMPAIGN51_TENANTS
from job_crawler.adapters.cdkj import Cdkj
from job_crawler.adapters.chinatower import ChinaTowerCampus, JacCampus
from job_crawler.adapters.chnenergy import Chnenergy
from job_crawler.adapters.cmbc import CmbcCampus
from job_crawler.adapters.coapi51 import TENANTS as COAPI51_TENANTS
from job_crawler.adapters.extra_catalogs import TENANTS as EXTRA_TENANTS
from job_crawler.adapters.feishu import TENANTS as FEISHU_TENANTS
from job_crawler.adapters.greentown import GreentownCampus
from job_crawler.adapters.haier import HaierCampus
from job_crawler.adapters.hotjob import TENANTS as HOTJOB_TENANTS
from job_crawler.adapters.hzbank import HzbankCampus
from job_crawler.adapters.hzsteel import Hzsteel
from job_crawler.adapters.inline_catalogs import TENANTS as INLINE_TENANTS
from job_crawler.adapters.jd import JD
from job_crawler.adapters.jxcc import JxccCampus
from job_crawler.adapters.lenovo import Lenovo
from job_crawler.adapters.lixiang import LiAutoCampus
from job_crawler.adapters.meituan import Meituan
from job_crawler.adapters.moka import TENANTS as MOKA_TENANTS
from job_crawler.adapters.nci import NciCampus
from job_crawler.adapters.newhope import NewHopeCampus
from job_crawler.adapters.pdd import PddCampus
from job_crawler.adapters.platforms import CCB, CNPC, Alibaba, Pingan
from job_crawler.adapters.sf import SF
from job_crawler.adapters.sinopharm import SinopharmCampus
from job_crawler.adapters.smic import SmicCampus
from job_crawler.adapters.static_campus import TENANTS as STATIC_TENANTS
from job_crawler.adapters.sunwoda import SunwodaCampus
from job_crawler.adapters.tcl import TCLCampus
from job_crawler.adapters.tencent import Tencent
from job_crawler.adapters.wtmec import Wtmec
from job_crawler.adapters.yingte import YingteCampus
from job_crawler.adapters.zhaopin import TENANTS as ZHAOPIN_TENANTS
from job_crawler.adapters.zhiye import TENANTS
from job_crawler.adapters.ztt import ZttCampus

REGISTRY = {
    adapter.name: adapter
    for adapter in (
        AnkerCampus,
        SinopharmCampus,
        *STATIC_TENANTS,
        *BANK_TENANTS,
        Pingan,
        CCB,
        CNPC,
        Alibaba,
        Wtmec,
        ZttCampus,
        HzbankCampus,
        CmbcCampus,
        Hzsteel,
        Ansteel,
        Lenovo,
        LiAutoCampus,
        *FEISHU_TENANTS,
        *INLINE_TENANTS,
        *EXTRA_TENANTS,
        JD,
        JxccCampus,
        Tencent,
        SF,
        BankComm,
        Meituan,
        Bilibili,
        BYDCampus,
        Cdkj,
        Chnenergy,
        ChinaTowerCampus,
        JacCampus,
        HaierCampus,
        NciCampus,
        SunwodaCampus,
        GreentownCampus,
        NewHopeCampus,
        PddCampus,
        YingteCampus,
        SmicCampus,
        TCLCampus,
        *CAMPAIGN51_TENANTS,
        *COAPI51_TENANTS,
        *TENANTS,
        *HOTJOB_TENANTS,
        *MOKA_TENANTS,
        *ZHAOPIN_TENANTS,
    )
}
