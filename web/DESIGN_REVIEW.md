# 2026-09-27：浅色科学工作台改版

用户在查看调研后确认方案A。本轮实现、验收均在本地；未提交、推送或替换线上站点。旧站仍是此前已部署版本。

## 从参考到设计

实际浏览并截图了[marimo](https://marimo.io/)、[Observable](https://observablehq.com/)和[Streamlit](https://streamlit.io/)。marimo和Streamlit把用途、尝试入口和实际工具演示连接起来；Observable用图表与操作解释问题，而不仅用文字介绍能力。本项目借鉴这些信息结构，不复制品牌素材、采用量、客户背书或云端能力。

[Linear](https://linear.app/)可抽取正文，但本次两次桌面截图中正文未正常呈现，因此不作为具体视觉设计依据。marimo演示在本次捕获中出现错误状态，也不据此评价产品质量。参考截图/正文只留在忽略的`output/playwright/design-research/`，不复制到公开站点。

选定浅色科学工作台而非深色仪器台或长篇编辑式文章：本页的主要任务是检查两组已保存结果，曲线及参数诊断应当比装饰、重复叙述更靠前。

## 实施

- 移除首屏599大卡，缩短标题区；保留元信息，真实曲线成为主视觉，不另造示意数据。
- 桌面在图表右侧放诊断，手机先显示一句关键发现，再展示曲线和参数明细。统一蓝绿操作色，橙色提示边界/缺信息，第二温度通道用紫色区分；不靠颜色单独表达含义。
- 正文16px、辅助文字14px；放大图表标签。桌面图表增加纵向绘图空间，时间/温度范围及全部599点保持一致。
- 移除重复的三段步骤介绍，将有用内容保留在对应诊断/FAQ；保留模型、噪声、独立案例、默认参数、版权及工程放行限制。
- SEO正文、结构化数据、来源下载、无JS双窗口内容与现有交互保留；无新依赖、在线拟合、上传或统计服务。

## 同条件前后测量

同一浏览器、同一数据、默认100秒窗口、FAQ收起，视口高度900px；旧版为线上页面，新版是带31px预览提示的本地构建。新提示会增加新版高度，表中未人为扣除。字体判断针对可见`p`元素，不将它冒充全站无障碍审计或用户阅读速度测量。

|视口宽度|旧图表顶部|新图表顶部|旧页面总高|新页面总高|旧/新小于14px可见段落|
|---|---:|---:|---:|---:|---:|
|1440px|1161.31px|578.95px|3893px|2826px|24 / 0|
|900px|1095.53px|622.34px|4208px|3480px|30 / 0|
|360px|1506.36px|623.66px|6262px|4684px|30 / 0|

360×800额外验收中，图表仍从623.66px开始。桌面≤600px、手机≤650px的目标达到；测得最小图表字号分别约18.88/16.45/14.09屏幕像素，均超过12px。各视口没有页面横向溢出。这些是布局测量，不证明转化、留存或用户满意度提升。

第一版手机图表741px，第二版656.75px，均未达目标；保留日志和截图。最终移除与卡片标题重复的一行工具栏说明，不通过缩小文字达标。

## 验证与证据

- `web/verify_layout.js`：从当前浏览器页面URL运行，检查默认窗口下的首屏位置、字号、溢出并截图。日志：`output/playwright/redesign/layout-final.log`。
- 原`web/verify_browser.js`仅在CLI执行时将预览地址替换为18769端口、产物目录改为本轮目录；11项分组检查返回PASS：键盘窗口切换、读数及游标、实际剪贴板、复制拒绝回退、CSV下载、减少动态效果和无JS阅读。14个运行时请求均同源，零页面异常或HTTP错误。日志：`output/playwright/redesign/browser-regression.log`。
- 独立核对16条SVG曲线×599点：原/新时间位置与归一化温度坐标一致，仅桌面绘图高度变化；嵌入JSON相同。全部78个既有TCLab文件与HEAD逐字节一致，站点内证据下载副本全部相同。日志：`output/playwright/redesign/evidence-check.log`。
- 根测试新增工作台结构与限制文案检查，不删原测试；`python scripts/check.py`涵盖新检查。源码通过`git diff --check`，新增检查脚本通过`node --check`，`gitleaks dir web --no-banner --redact`报告`no leaks found`。

最终执行`TZ=UTC /tmp/thermal-research-packaging/venv/bin/python -B scripts/check.py`退出0，43+14+26+6+39=128项测试通过，8个历史阶段快照匹配。日志：`output/playwright/redesign/full-check-final.log`。该解释器为本机已有NumPy/SciPy环境，未安装新依赖。预览首页实测HTTP 200；这不是线上改版已发布的证据。

已目视检查首屏桌面与手机截图：`output/playwright/redesign/first-screen-1440-900.png`、`first-screen-360-800.png`。完整对照为`final-1440-900.png`、`final-900-900.png`、`final-360-900.png`，无JS及300秒状态截图另在相同目录。截图保存在忽略目录，不作为科学测量证据上传。

## 本地查看

本次预览：http://127.0.0.1:18769/ 。服务停止后，可用仓库根的`python -m http.server 18769 --bind 127.0.0.1 --directory output/redesign-final`重开。

从源码重建请执行`python -B web/build.py --output /新的输出目录`；已有目录不会覆盖。用Playwright打开预览后，执行`run-code "$(cat web/verify_layout.js)"`可复核布局。所有页面变化仍待用户查看；本轮不自动部署。
