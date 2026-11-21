# Changelog

所有值得注意的版本变更都会记录在这个文件里。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.1.1] - 2026-11-21

### Added
- 版本号可观测：`/health` 返回 `version` 字段；admin / web 构建注入产品版本号并在页面展示（用户中心 / 登录页 / 对话页）
- 商业化多租户：平台/企业两级角色、租户数据隔离、企业钱包计费、生命周期状态机、邀请码注册
- 平台运营工作台：开通/转正/冻结/充值企业、生成/停用企业管理员邀请码
- 企业侧接口全量租户隔离（kb/文档/应用/记录/Trace/chunk/通知/对账/问答）
- 项目路线图：`ROADMAP.md`（文档清洗与预览确认、切块策略可配置）

### Changed
- 右上角智能助手更名「EverKb Bot」，头像换为产品 logo（抽屉头部与消息列表）

### Fixed
- 真实 MySQL 老库 invite_code 表结构漂移导致的发码/列表 500
- 企业管理员跨企业可见遗留数据（越权）问题
- admin 智能助手抽屉组件 `ElMessage` 改为显式导入，消除 eslint `no-undef` 报错

## [0.1.0] - 2026-11-19

### Added
- 多格式文档解析管线（状态机 + 重试 + 替换语义）
- Markdown 在线编辑 + 自动重切块
- SSE 流式问答 + 引用溯源
- 全链路 Trace 观测（Span 树 + 聚合分析）
- 对账工具（漂移扫描）
- BM25 混合检索（RRF 融合）+ 检索评测与三路消融
- admin 管理后台 + web 用户对话端
- API 统一信封格式
