---
name: mobile-design-spec
description: 移动端 App 设计规范速查（iOS / Android / 微信小程序 / H5 四平台）。涵盖机型尺寸与逻辑分辨率、pt/dp/sp/rpx/rem 单位换算、安全区域（刘海 44pt、底部 34pt）、最小可点击区域、字号字体、品牌色值、圆角间距、图标尺寸、切图导出倍率与命名、自适应布局策略和设计自查清单。凡涉及移动端 UI 设计稿、页面适配、尺寸/字号/色值选取、pt-px-dp-rpx-rem-vw 换算、@2x/@3x 切图、刘海屏安全区、小程序胶囊按钮避让、H5 rem 方案等场景都应使用本技能——即使用户没有明确说出"设计规范"这个词。
---

# 移动端设计规范（iOS / Android / 小程序 / H5）

来源：《移动端设计规范合集：iOS、Android、小程序、H5 页面尺寸规范》。核心原则一句话：**单位统一、倍率清晰、安全区域不踩坑**。

## 使用方式

按目标平台读取对应参考文件（按需加载，不要一次全读）：

| 目标平台 | 参考文件 |
|---|---|
| iOS（iPhone/iPad App） | `references/ios.md` |
| Android App | `references/android.md` |
| 微信小程序 | `references/miniprogram.md` |
| H5 / 移动端网页 | `references/h5.md` |

跨平台项目（一套稿多端用）直接看下方"四平台对比"与"导出规范"。

## 单位换算速查（最常用）

| 平台 | 单位 | 换算要点 |
|---|---|---|
| iOS | pt | 1pt = 2px（@2x）= 3px（@3x） |
| Android | dp / sp | px = dp × (dpi ÷ 160)；文字用 sp（随系统字号缩放） |
| 小程序 | rpx | 屏宽固定 750rpx；以 375px 屏为基准时 1rpx = 0.5px，即 rpx = px × 2 |
| H5 | rem / vw | 750 设计稿：1rem = 75px（rem = 设计稿px ÷ 75）；375 稿：1rem = 37.5px；1px ≈ 0.1333vw |

**设计稿基准**：iOS 用 375×812（pt）；Android 用 360×640 或 360×800（dp）；小程序与 H5 用 750×1334（@2x）。
团队统一产出建议以 **750 宽（@2x）** 为基准：iOS 逻辑宽 375、Android 360dp、小程序 750rpx 都能良好映射。

⚠️ Android 不要直接用 iPhone 的 375 宽度做设计稿——dp 与 pt 数值体系不同，会导致布局错位。

## 关键数字（跨平台通用速记）

| 项目 | iOS | Android | 小程序 | H5（@2x） |
|---|---|---|---|---|
| 状态栏（刘海屏） | 44pt（旧机型 20pt） | 约 24-32dp | 跟随微信导航栏 | — |
| 底部安全区 | 34pt（Home Indicator） | 手势导航条 | 避开 | env(safe-area-inset-bottom) |
| 最小可点击区域 | 44×44pt | 48×48dp | ≥44px | 88px（逻辑 44px） |
| 页面左右边距 | 16pt | 16dp | — | 30px（逻辑 15px） |
| 页面主字体 | 17pt | 14sp | 15px | 28px（逻辑 14px） |
| 标签栏高度 | 49pt | 56dp | 56px | — |
| 卡片圆角 | 8pt | — | 8px | 16px（逻辑 8px） |
| 品牌主色 | #007AFF（系统蓝） | #6200EE（Material 紫） | #07C160（微信绿） | #576B95（微信内链接色） |

## 切图导出规范

- **iOS**：@1x / @2x / @3x 三套，命名如 `icon_home@3x.png`
- **Android**：mdpi / hdpi / xhdpi / xxhdpi / xxxhdpi（1x/1.5x/2x/3x/4x）
- **命名规范**：`模块_功能_状态`，如 `btn_primary_default` / `btn_primary_pressed`
- **交付标注**：用蓝湖 / Figma / MasterGo 全量标注间距、字号、色值、圆角

## 适配策略选择

- **等比适配**：简单页面按宽度整体缩放，文字可不缩放
- **弹性布局**（复杂页面首选）：flex/grid，文字流式，图片定宽，关键模块锚定
- **流式布局**：百分比宽度 + max-width 限制
- **响应式断点**：手机 <768px；平板 768-1024px；桌面 >1024px

## 设计自查清单（交付前过一遍）

- [ ] 安全区域已预留（iOS 刘海 44pt / 底部 34pt；H5 用 env(safe-area-inset-bottom)）
- [ ] 最小可点击区域达标（iOS 44pt / Android 48dp）
- [ ] 字号使用各平台推荐值（见各参考文件）
- [ ] 主色/辅助色对比度 ≥ 4.5:1
- [ ] 切图按倍率导出（@2x/@3x 或 mdpi~xxxhdpi）
- [ ] 深色模式是否需要适配（提供深浅两套色板）
- [ ] H5 的 1px 边框问题已处理（transform: scaleY(0.5) 等方案）
- [ ] 长图/大图已做懒加载；首屏 >3s 需骨架屏
