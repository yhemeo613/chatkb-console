# 设计规范（DESIGN SPECIFICATION）

> 依据「CloudBase ui-design skill」强制契约编写：任何界面改动**先改本文件，再写代码**。
> 本文件就是 AI 编码时的设计约束，改样式前先读这里。

## 1. Purpose Statement

本地单机运行的"微信高情商回复"知识库控制台。用户是系统所有者本人 + 少量授权成员，
高频操作是：查资料、生成回复、管理文档与权限。核心诉求是**低噪音、高密度、快定位**——
一切装饰必须为扫读效率让路。

## 2. Aesthetic Direction

**Industrial/utilitarian（工业实用风）**——明确的风格宣言，禁用 "modern / clean / simple"
这类无方向词。参考对象：Linear、Vercel Dashboard、Ant Design Pro 的信息密度，
但去掉其深色侧边栏套路。

## 3. Color Palette

| 令牌 | 色值 | 用途 |
|---|---|---|
| @green | `#07c160` | **唯一强调色**：主按钮、选中态、链接、成功态 |
| @text-1 | `#1b2430` | 主文字 |
| @text-2 | `#5b6672` | 次文字 |
| @text-3 | `#98a2ae` | 弱文字/标签 |
| @border | `#e3e7ec` | 全站分隔线（用线不用阴影） |
| @bg | `#f6f7f9` | 页面底色 |
| @danger / @warn / @ok | `#d93026` / `#b26a00` / `#0a8f4c` | 仅用于状态，不做装饰 |

❌ 禁用：紫色系（violet/purple/indigo/fuchsia）、蓝紫渐变、玻璃拟态、大阴影。
强调色占比控制在页面 <10%，其余全部中性色。

## 4. Typography

- **正文/中文**：`-apple-system, "PingFang SC", "Microsoft YaHei", "Segoe UI"`，
  主字号 14px、行高 1.5、段距 1 倍字号 —— **遵循 Ant Design 官方字体规范**
  （这是有意的品牌 override：中文 B 端产品系统字体栈是成熟实践，可读性优先）。
- **数字/展示**：`Bahnschrift`（DIN 系工业字体，Windows 10+ 内置，离线可用）+
  `font-variant-numeric: tabular-nums`，用于统计数字、任务耗时、日志 ID。
- **字阶**：12（辅助）/ 13（表格/说明）/ **14（正文基准）** / 16（卡片标题）/ 20（页面主数）。
- **英文小标签**：letter-spacing 0.08em + 12px（如统计带 label、logo 副标）。

## 5. Layout Strategy

- 中后台标准骨架（侧栏 + 头栏 + 内容），**按 Ant Design Pro 模式执行** ——
  这是对"必须打破居中对称"条款的有意 override：B 端控制台的确定性优先于形式创新。
- 统计数据用**单条统计带**（分隔线分列，禁止等距圆角卡片阵列）。
- 密度：内容区 16px 边距、卡片内 20px、间距只用 8/16/24 三档。
- 形状：6px 小圆角、1px `@border` 边框、**零阴影**。

## 6. Icons

只用 `@ant-design/icons` 一个库（已全站统一），❌ 禁止 emoji 当图标。

## 7. 自检记录（ui-design skill checklist）

- [x] 色彩审计：无紫系；`purple` 标签已替换（Users/Roles/Menus 的"内置/目录"改石墨灰）
- [x] 字体审计：系统栈按上文记录为有意 override；展示层 Bahnschrift
- [x] 图标审计：无 emoji 图标，全部 @ant-design/icons
- [x] 布局审计：AntD Pro 骨架（记录 override），统计带替代卡片阵列
- [x] 本规范先于代码输出
