# SPEC-168 宇通移动校园与博士目录

状态：开发中；SPEC-156 A 组 COM0362。

## 目标与非目标

修复已声明但未启用的 hotjob-yutong 适配器。官方移动菜单分别为“校园招聘” `/mc/position/campus`（recruitType=1）、“博士招聘” `/mc/position/intern`（recruitType=12）。后者路径名称不能被误判为实习。排除社会和独立实习生目录，不扩展到未验证的其他宇通门户。

## 输入输出

使用租户 SU64e7157a1eb80519a8e4efcf 下实际观察的 positionInfo/listPosition 与 listSearchTerm 表单接口。两目录均无筛选，currentPage=1/pageSize=10/coordinateLat=""/coordinateLng=""；本轮两者均 state=200、pageForm.dataCount=0/totalPage=0/pageSize=0/currentPage=0/pageData=[]，positonNum=0；页面亦显示暂无数据。该明确零响应允许返回页大小 0，不能将其他无效页大小当作有效分页。

公共 Hotjob 显式参数化招聘类型和详情路由名称，默认行为保持 campus/1；宇通依次执行校园和博士目录。每个目录独立 scope；失败须保留另一目录结果和覆盖问题。非零时复用已有分页、详情身份与招聘类型校验；详情 URL 按本租户路由别名，不从名称推断工种。

## 失败行为与验收

零计数不一致、响应业务失败、未知筛选、详情类型错配和目录重复沿用显式失败。非零详情仍待未来真实样本，不把共享回放声称为宇通本轮非零验证。

回放核验校园与博士两个零目录、合法零页大小、非零非法页大小拒绝及移动详情类型参数；全部既有 Hotjob 回放通过。实采两目录均完整零后只读审计、再正式绑定并记录零岗位；不计入有岗位企业数。
