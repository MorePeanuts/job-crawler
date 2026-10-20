"""Explicit adapter registration; unknown sites never fall through to guessing."""

from job_crawler.adapters.aisidi import AisidiCampus
from job_crawler.adapters.anker import AnkerCampus
from job_crawler.adapters.ansteel import Ansteel
from job_crawler.adapters.asus import AsusMainlandCampus
from job_crawler.adapters.avary import AvaryCampus
from job_crawler.adapters.bank_catalogs import TENANTS as BANK_TENANTS
from job_crawler.adapters.bankcomm import BankComm
from job_crawler.adapters.bankgy import BankgyCampus
from job_crawler.adapters.baowu_baosteel import BaowuBaosteel2027
from job_crawler.adapters.beigene import BeigeneRecruitment
from job_crawler.adapters.bilibili import Bilibili
from job_crawler.adapters.bluefocus import BlueFocus
from job_crawler.adapters.boe import BoeCampus
from job_crawler.adapters.bohai import Bohai2027
from job_crawler.adapters.byd import BYDCampus
from job_crawler.adapters.campaign51 import TENANTS as CAMPAIGN51_TENANTS
from job_crawler.adapters.cathay import CathayIMatch
from job_crawler.adapters.cdkj import Cdkj
from job_crawler.adapters.cdrcb import Cdrcb2027
from job_crawler.adapters.ceair import Ceair2027
from job_crawler.adapters.cec import CecCampus
from job_crawler.adapters.chd import ChdCampus
from job_crawler.adapters.chinalco import Chinalco2027
from job_crawler.adapters.chinatelecom import ChinaTelecomCampus
from job_crawler.adapters.chinatower import (
    ChinaTowerCampus,
    GuangxinCampus,
    JacCampus,
    ShudaoCampus,
)
from job_crawler.adapters.chnenergy import Chnenergy
from job_crawler.adapters.chujiang_ustc import (
    ChujiangUstcCampus,
    QingshanUstc2027,
    ShanyingUstc2027,
    TonglingUstc2027,
    ZhongweiUstc2027,
)
from job_crawler.adapters.cib import Cib2027
from job_crawler.adapters.cka import CkaCareers
from job_crawler.adapters.clp import ClpGraduate2027
from job_crawler.adapters.cmb import CmbCampus
from job_crawler.adapters.cmbc import CmbcCampus
from job_crawler.adapters.coapi51 import TENANTS as COAPI51_TENANTS
from job_crawler.adapters.conch_ahnu import ConchNewMaterialsAhnu2027
from job_crawler.adapters.cpcg import CpcgCampus
from job_crawler.adapters.crecg_hebut import CrecgZhongtieJianggong2027
from job_crawler.adapters.cspc import CspcCampus
from job_crawler.adapters.ctg_dutyfree import CtgDutyFreeCampus
from job_crawler.adapters.ctrip import CtripCampus
from job_crawler.adapters.datang import Datang2027
from job_crawler.adapters.dfzq import DfzqCampus
from job_crawler.adapters.dingsheng import DingshengCampus
from job_crawler.adapters.extra_catalogs import TENANTS as EXTRA_TENANTS
from job_crawler.adapters.faw import FawCampus
from job_crawler.adapters.feishu import TENANTS as FEISHU_TENANTS
from job_crawler.adapters.foxconn import FoxconnCampus
from job_crawler.adapters.fuyao import FuyaoHeadquarters
from job_crawler.adapters.gdh import GdhMobileCampus
from job_crawler.adapters.gem import GemCampus
from job_crawler.adapters.gemdale import GemdaleCampus
from job_crawler.adapters.gig import GigCampus
from job_crawler.adapters.goldjewelry import GoldJewelryCampus
from job_crawler.adapters.grcbank import GuangzhouRuralBankCampus
from job_crawler.adapters.gree import GreeCampus
from job_crawler.adapters.greentown import GreentownCampus
from job_crawler.adapters.guangwu import GuangwuCampus
from job_crawler.adapters.guotai_haitong import GuotaiHaitongCampus
from job_crawler.adapters.haidilao import HaidilaoStoreTrainee
from job_crawler.adapters.haier import HaierCampus
from job_crawler.adapters.hailiang import HailiangCampus
from job_crawler.adapters.hbisco import HbiscoCampus
from job_crawler.adapters.hebut_fair import HebutFair2027
from job_crawler.adapters.hengli_shipbuilding import HengliShipbuilding2027
from job_crawler.adapters.hengtong_gdut import HengtongGdut2027
from job_crawler.adapters.hongqiao_cup import HongqiaoCup2027
from job_crawler.adapters.hongwang_kmust import HongwangKmust2027
from job_crawler.adapters.hotjob import TENANTS as HOTJOB_TENANTS
from job_crawler.adapters.hsbank import HsbankCampus
from job_crawler.adapters.huafa import HuafaListedCampus
from job_crawler.adapters.huaneng import HuanengCampus
from job_crawler.adapters.huawei import HuaweiGraduate
from job_crawler.adapters.hunansteel_hualing import HunansteelHualingCable2027
from job_crawler.adapters.hzbank import HzbankCampus
from job_crawler.adapters.hzsteel import Hzsteel
from job_crawler.adapters.iguopin_projects import Ceec2027, Cnbm2027, Cosco2027
from job_crawler.adapters.inline_catalogs import TENANTS as INLINE_TENANTS
from job_crawler.adapters.inovance import InovanceCampus
from job_crawler.adapters.inventec_hebut import InventecHebut2027
from job_crawler.adapters.isoftstone import ISoftStoneCampus
from job_crawler.adapters.itg_holding import ItgHoldingCampus
from job_crawler.adapters.jd import JD
from job_crawler.adapters.jianlong import JianlongCampus
from job_crawler.adapters.jointown import JointownCampus
from job_crawler.adapters.jxcc import JxccCampus
from job_crawler.adapters.kingboard import KingboardCareers
from job_crawler.adapters.laopu import LaopuCampus
from job_crawler.adapters.lenovo import Lenovo
from job_crawler.adapters.lixiang import LiAutoCampus
from job_crawler.adapters.longi_legacy import LongiLegacyCampus
from job_crawler.adapters.meituan import Meituan
from job_crawler.adapters.mingtai import MingtaiCampus
from job_crawler.adapters.moka import TENANTS as MOKA_TENANTS
from job_crawler.adapters.mtr import MtrGraduate
from job_crawler.adapters.mysteel import MysteelCampus
from job_crawler.adapters.nbcb import NingboBank2027
from job_crawler.adapters.nbport import NbportCampus
from job_crawler.adapters.nci import NciCampus
from job_crawler.adapters.netease import NeteaseCampus
from job_crawler.adapters.newhope import NewHopeCampus
from job_crawler.adapters.newworld import NewWorldCareers
from job_crawler.adapters.pccw import PccwGraduate
from job_crawler.adapters.pdd import PddCampus
from job_crawler.adapters.platforms import CCB, CNPC, Alibaba, Pingan
from job_crawler.adapters.qdbank import QdbankCampus
from job_crawler.adapters.risun_hebut import RisunDingzhouHebut2027
from job_crawler.adapters.rongsheng_hebut import RongshengHebut2027
from job_crawler.adapters.saic import SaicCampus
from job_crawler.adapters.sangang_cup import SangangMingguang2027
from job_crawler.adapters.sasdragon import SasDragonCareers
from job_crawler.adapters.satellite_hust import SatelliteHust2027
from job_crawler.adapters.sbp import SbpCampus
from job_crawler.adapters.scoped_coapi import BcdhListedCampus, KsfCampus
from job_crawler.adapters.sdhsg import SdhsgCampus
from job_crawler.adapters.sdicpower import SdicPowerCampus
from job_crawler.adapters.sf import SF
from job_crawler.adapters.shccig_mt import ShccigHeadquartersTrainees
from job_crawler.adapters.shenergy import ShenergyListedCampus
from job_crawler.adapters.shengtun import ShengtunMiningCampus
from job_crawler.adapters.shkp import ShkpMainland
from job_crawler.adapters.shougang import ShougangCampus
from job_crawler.adapters.sihc import SihcCampus
from job_crawler.adapters.sinopec import SinopecCampus
from job_crawler.adapters.sinopharm import SinopharmCampus
from job_crawler.adapters.sjm import SjmPublicJobs
from job_crawler.adapters.smic import SmicCampus
from job_crawler.adapters.spic2027 import Spic2027
from job_crawler.adapters.static_campus import TENANTS as STATIC_TENANTS
from job_crawler.adapters.stec import StecCampus
from job_crawler.adapters.sunwoda import SunwodaCampus
from job_crawler.adapters.swhy import SwhyCampus
from job_crawler.adapters.tcl import TCLCampus
from job_crawler.adapters.tencent import Tencent
from job_crawler.adapters.tfme import TfmeCampus
from job_crawler.adapters.tianshan_hebut import TianshanHebutCampus
from job_crawler.adapters.tongwei_share import TongweiShare2027
from job_crawler.adapters.uni_president import UniPresidentCareers
from job_crawler.adapters.workday import AiaWorkday, FwdWorkday, HkexWorkday, MelcoWorkday
from job_crawler.adapters.wtmec import Wtmec
from job_crawler.adapters.xfusion import XfusionCampus
from job_crawler.adapters.xingfa import XingfaCampus
from job_crawler.adapters.xmwy import XiamenTungsten2027
from job_crawler.adapters.yankuang_uibe import YankuangUibe2027
from job_crawler.adapters.yili import YiliHeadquarters
from job_crawler.adapters.yingte import YingteCampus
from job_crawler.adapters.yto_zju import YtoZju2027
from job_crawler.adapters.yuexiu2027 import YuexiuProperty2027
from job_crawler.adapters.yuneng_csu import (
    ShagangCsu2027,
    YunengCsu2027,
    ZhongjinlingnanCsu2027,
)
from job_crawler.adapters.yuntou import YuntouNotices
from job_crawler.adapters.zhaopin import TENANTS as ZHAOPIN_TENANTS
from job_crawler.adapters.zhaopin import Cnooc2027
from job_crawler.adapters.zhiye import TENANTS, Ctf2027, WeichaiPower2027
from job_crawler.adapters.zjamp import ZjampCampus
from job_crawler.adapters.zjci import ZjciCampus
from job_crawler.adapters.zjjt import Zjjt2027
from job_crawler.adapters.zto import ZtoCampus
from job_crawler.adapters.ztt import ZttCampus

REGISTRY = {
    adapter.name: adapter
    for adapter in (
        AnkerCampus,
        MtrGraduate,
        AvaryCampus,
        QdbankCampus,
        DingshengCampus,
        MingtaiCampus,
        MysteelCampus,
        SbpCampus,
        JointownCampus,
        SihcCampus,
        ChdCampus,
        AsusMainlandCampus,
        ZtoCampus,
        GreeCampus,
        SinopharmCampus,
        *STATIC_TENANTS,
        *BANK_TENANTS,
        Pingan,
        CCB,
        CNPC,
        ChinaTelecomCampus,
        Cib2027,
        ZjciCampus,
        Zjjt2027,
        ZjampCampus,
        Cnooc2027,
        Chinalco2027,
        CtgDutyFreeCampus,
        CtripCampus,
        Alibaba,
        Wtmec,
        XfusionCampus,
        XingfaCampus,
        XiamenTungsten2027,
        ZttCampus,
        HzbankCampus,
        CmbcCampus,
        CmbCampus,
        Hzsteel,
        Ceec2027,
        Cnbm2027,
        Cosco2027,
        Ansteel,
        Lenovo,
        LiAutoCampus,
        LongiLegacyCampus,
        *FEISHU_TENANTS,
        FuyaoHeadquarters,
        *INLINE_TENANTS,
        InovanceCampus,
        InventecHebut2027,
        CrecgZhongtieJianggong2027,
        HunansteelHualingCable2027,
        ConchNewMaterialsAhnu2027,
        RisunDingzhouHebut2027,
        HongqiaoCup2027,
        YankuangUibe2027,
        YtoZju2027,
        SatelliteHust2027,
        HengtongGdut2027,
        ISoftStoneCampus,
        ItgHoldingCampus,
        *EXTRA_TENANTS,
        JD,
        JxccCampus,
        Tencent,
        SF,
        SdhsgCampus,
        SdicPowerCampus,
        SaicCampus,
        ShccigHeadquartersTrainees,
        ShenergyListedCampus,
        ShengtunMiningCampus,
        ShougangCampus,
        SinopecCampus,
        FoxconnCampus,
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
        GuangxinCampus,
        ShudaoCampus,
        HuaweiGraduate,
        FawCampus,
        CpcgCampus,
        CspcCampus,
        GemCampus,
        GdhMobileCampus,
        GemdaleCampus,
        SjmPublicJobs,
        PccwGraduate,
        HuafaListedCampus,
        StecCampus,
        CkaCareers,
        ClpGraduate2027,
        TianshanHebutCampus,
        YunengCsu2027,
        ZhongjinlingnanCsu2027,
        ShagangCsu2027,
        ChujiangUstcCampus,
        QingshanUstc2027,
        TonglingUstc2027,
        ZhongweiUstc2027,
        ShanyingUstc2027,
        SangangMingguang2027,
        HengliShipbuilding2027,
        HongwangKmust2027,
        BaowuBaosteel2027,
        RongshengHebut2027,
        HebutFair2027,
        TongweiShare2027,
        KingboardCareers,
        UniPresidentCareers,
        MelcoWorkday,
        FwdWorkday,
        HkexWorkday,
        AiaWorkday,
        BeigeneRecruitment,
        DfzqCampus,
        BankgyCampus,
        NbportCampus,
        YuntouNotices,
        SwhyCampus,
        BcdhListedCampus,
        KsfCampus,
        GuotaiHaitongCampus,
        HuanengCampus,
        JianlongCampus,
        HaierCampus,
        HailiangCampus,
        BlueFocus,
        GigCampus,
        ShkpMainland,
        TfmeCampus,
        AisidiCampus,
        HaidilaoStoreTrainee,
        LaopuCampus,
        GuangwuCampus,
        HbiscoCampus,
        NciCampus,
        NeteaseCampus,
        NingboBank2027,
        SunwodaCampus,
        GreentownCampus,
        GuangzhouRuralBankCampus,
        NewHopeCampus,
        NewWorldCareers,
        HsbankCampus,
        GoldJewelryCampus,
        SasDragonCareers,
        CathayIMatch,
        PddCampus,
        YingteCampus,
        YuexiuProperty2027,
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
