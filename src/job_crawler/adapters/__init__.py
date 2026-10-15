"""Explicit adapter registration; unknown sites never fall through to guessing."""

from job_crawler.adapters.anker import AnkerCampus
from job_crawler.adapters.ansteel import Ansteel
from job_crawler.adapters.bank_catalogs import TENANTS as BANK_TENANTS
from job_crawler.adapters.bankcomm import BankComm
from job_crawler.adapters.bilibili import Bilibili
from job_crawler.adapters.boe import BoeCampus
from job_crawler.adapters.bohai import Bohai2027
from job_crawler.adapters.byd import BYDCampus
from job_crawler.adapters.campaign51 import TENANTS as CAMPAIGN51_TENANTS
from job_crawler.adapters.cdkj import Cdkj
from job_crawler.adapters.cdrcb import Cdrcb2027
from job_crawler.adapters.ceair import Ceair2027
from job_crawler.adapters.cec import CecCampus
from job_crawler.adapters.chinalco import Chinalco2027
from job_crawler.adapters.chinatelecom import ChinaTelecomCampus
from job_crawler.adapters.chinatower import ChinaTowerCampus, JacCampus
from job_crawler.adapters.chnenergy import Chnenergy
from job_crawler.adapters.cmbc import CmbcCampus
from job_crawler.adapters.coapi51 import TENANTS as COAPI51_TENANTS
from job_crawler.adapters.ctg_dutyfree import CtgDutyFreeCampus
from job_crawler.adapters.ctrip import CtripCampus
from job_crawler.adapters.datang import Datang2027
from job_crawler.adapters.extra_catalogs import TENANTS as EXTRA_TENANTS
from job_crawler.adapters.feishu import TENANTS as FEISHU_TENANTS
from job_crawler.adapters.fuyao import FuyaoHeadquarters
from job_crawler.adapters.grcbank import GuangzhouRuralBankCampus
from job_crawler.adapters.greentown import GreentownCampus
from job_crawler.adapters.haier import HaierCampus
from job_crawler.adapters.hotjob import TENANTS as HOTJOB_TENANTS
from job_crawler.adapters.hzbank import HzbankCampus
from job_crawler.adapters.hzsteel import Hzsteel
from job_crawler.adapters.iguopin_projects import Ceec2027, Cosco2027
from job_crawler.adapters.inline_catalogs import TENANTS as INLINE_TENANTS
from job_crawler.adapters.inovance import InovanceCampus
from job_crawler.adapters.itg_holding import ItgHoldingCampus
from job_crawler.adapters.jd import JD
from job_crawler.adapters.jxcc import JxccCampus
from job_crawler.adapters.lenovo import Lenovo
from job_crawler.adapters.lixiang import LiAutoCampus
from job_crawler.adapters.longi_legacy import LongiLegacyCampus
from job_crawler.adapters.meituan import Meituan
from job_crawler.adapters.moka import TENANTS as MOKA_TENANTS
from job_crawler.adapters.nbcb import NingboBank2027
from job_crawler.adapters.nci import NciCampus
from job_crawler.adapters.newhope import NewHopeCampus
from job_crawler.adapters.pdd import PddCampus
from job_crawler.adapters.platforms import CCB, CNPC, Alibaba, Pingan
from job_crawler.adapters.sdicpower import SdicPowerCampus
from job_crawler.adapters.sf import SF
from job_crawler.adapters.shccig_mt import ShccigHeadquartersTrainees
from job_crawler.adapters.shougang import ShougangCampus
from job_crawler.adapters.sinopharm import SinopharmCampus
from job_crawler.adapters.smic import SmicCampus
from job_crawler.adapters.spic2027 import Spic2027
from job_crawler.adapters.static_campus import TENANTS as STATIC_TENANTS
from job_crawler.adapters.sunwoda import SunwodaCampus
from job_crawler.adapters.tcl import TCLCampus
from job_crawler.adapters.tencent import Tencent
from job_crawler.adapters.wtmec import Wtmec
from job_crawler.adapters.xfusion import XfusionCampus
from job_crawler.adapters.xmwy import XiamenTungsten2027
from job_crawler.adapters.yili import YiliHeadquarters
from job_crawler.adapters.yingte import YingteCampus
from job_crawler.adapters.zhaopin import TENANTS as ZHAOPIN_TENANTS
from job_crawler.adapters.zhaopin import Cnooc2027
from job_crawler.adapters.zhiye import TENANTS, Ctf2027, WeichaiPower2027
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
        ChinaTelecomCampus,
        Cnooc2027,
        Chinalco2027,
        CtgDutyFreeCampus,
        CtripCampus,
        Alibaba,
        Wtmec,
        XfusionCampus,
        XiamenTungsten2027,
        ZttCampus,
        HzbankCampus,
        CmbcCampus,
        Hzsteel,
        Ceec2027,
        Cosco2027,
        Ansteel,
        Lenovo,
        LiAutoCampus,
        LongiLegacyCampus,
        *FEISHU_TENANTS,
        FuyaoHeadquarters,
        *INLINE_TENANTS,
        InovanceCampus,
        ItgHoldingCampus,
        *EXTRA_TENANTS,
        JD,
        JxccCampus,
        Tencent,
        SF,
        SdicPowerCampus,
        ShccigHeadquartersTrainees,
        ShougangCampus,
        BankComm,
        Meituan,
        Bilibili,
        BoeCampus,
        Bohai2027,
        BYDCampus,
        Cdkj,
        CecCampus,
        Ceair2027,
        Cdrcb2027,
        Chnenergy,
        Datang2027,
        ChinaTowerCampus,
        JacCampus,
        HaierCampus,
        NciCampus,
        NingboBank2027,
        SunwodaCampus,
        GreentownCampus,
        GuangzhouRuralBankCampus,
        NewHopeCampus,
        PddCampus,
        YingteCampus,
        YiliHeadquarters,
        SmicCampus,
        Spic2027,
        TCLCampus,
        *CAMPAIGN51_TENANTS,
        *COAPI51_TENANTS,
        *TENANTS,
        WeichaiPower2027,
        Ctf2027,
        *HOTJOB_TENANTS,
        *MOKA_TENANTS,
        *ZHAOPIN_TENANTS,
    )
}
