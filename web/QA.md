# 交互案例页：本地验收记录

状态：**已生成、已本地浏览器验收，未提交、未推送、未部署。** 本轮没有重跑拟合或修改TCLab数据/科学结果；承接上轮尚未提交的评估产物，只读生成页面。

## 交付

- `build.py`读取两组实测评估的JSON/CSV，检查数据、拟合和源码哈希，独立复算RMSE。原生HTML/CSS/JavaScript展示100/300秒窗口、全部599点、参数来源与局部诊断。
- 无JS时两组图表、结论、FAQ与本地命令均在HTML正文。启用JS后可切换窗口、用滑条/键盘查看采样点、复制当前窗口命令，并下载原样CSV证据。
- 语义标题/描述、Open Graph、TechArticle结构化数据、来源与边界；默认noindex预览。只有显式配置正式HTTPS网址才输出canonical、sitemap及可索引robots，不宣称已被搜索引擎收录或被AI引用。
- 无框架、CDN、第三方字体、用户上传、跟踪、本地存储或在线计算。分享卡为本项目SVG的1200×630浏览器渲染PNG。

## 运行证据

|检查|实际结果|本地日志/产物（仓库根下）|
|---|---|---|
|`python -B -S -m unittest discover -s tests -p 'test_case_site.py' -v`|8项通过；含数值篡改拒绝、确定性构建、完整点数、无JS正文、元数据和本地资源|`output/playwright/site-tests-first.log`|
|`python -B -S web/build.py --output output/site-preview`|GENERATED；非部署；noindex预览|`output/site-preview/index.html`|
|Playwright CLI执行`web/verify_browser.js`|返回`status: PASS`；11条分组检查通过|`output/playwright/browser-verification-first.log`|
|`TZ=UTC /tmp/thermal-research-packaging/venv/bin/python -B scripts/check.py`|41+14+26+6+39=126项通过，退出0；8个历史阶段快照一致|`output/playwright/full-check.log`|
|两份JS语法及本轮源码空白检查|PASS；包含未跟踪的新文件|`output/playwright/source-check-verified.log`|
|`gitleaks dir web --no-banner --redact`|`no leaks found`|`output/playwright/gitleaks-web.log`|
|TCLab产物保护与浏览器下载对照|78个TCLab文件与原暂存版本相同；浏览器下载CSV逐字节匹配|`output/playwright/evidence-preservation.log`|
|`curl --noproxy '*' ... http://127.0.0.1:18766/`|HTTP 200；HTML 265425字节|本地服务，不是公网地址|

浏览器检查包含：真实键盘窗口切换；图表、指标与命令同步；第597行读数及两套SVG游标与保存数据一致；实际系统剪贴板内容核对；主动模拟复制权限拒绝后的手动选择提示；FAQ键盘开合；CSV真实下载；减少动态效果；禁用JS后的移动端可读性。14个运行时请求全部同源，零第三方请求、页面异常或HTTP错误。没有测量真实用户转化率。

截图已经打开检查：
- `output/playwright/verified-1440.png`
- `output/playwright/verified-900.png`
- `output/playwright/verified-360.png`
- `output/playwright/verified-no-js-360.png`
- `output/playwright/desktop-detail.png`、`output/playwright/mobile-detail.png`

900px与360px没有页面水平溢出；移动端用单列布局及专用坐标尺寸，而非直接缩小桌面标签。截图及原始执行日志按仓库规则放忽略的`output/`，不随仓库发布。

## 失败与残余事项

- Playwright对独立SVG文档生成可访问性快照时超时；改用浏览器直接截图生成分享卡。正式HTML页面正常加载，后续页面验收通过。8766已被占用，因此本次改用18766，不终止其他服务。
- 首次源码空白检查命令使用zsh特殊变量`path`导致找不到git；改用Python子进程并正确区分`git diff --no-index --check`的差异退出码后通过。早期命令日志保留，不将其冒充页面错误。
- 上轮两份预测CSV的CRLF曾被`git diff --cached --check`误报为尾随空白。用户要求处理后，在`.gitattributes`仅为这两个路径声明`cr-at-eol`并保留实际尾随空白检查；继续`-text`保留原始字节，不改CSV或源码哈希。回归测试同时验证正常CRLF通过、实际尾随空格拒绝、其他路径不受影响。
- 正式上线前仍需先发布对应分析入口、明确托管位置与网址、复核原创代码许可，再部署并验证真实URL/分享卡/robots。构建器不会完成这些动作。
- 本页是对同一历史记录的解释，不是独立试验、用户接入证明、最优补测收益或工业适用性证据。

## CSV提交阻断修复复核

用户要求处理后已复现原错误并修正限定路径的Git行尾检查。`python -B -S -m unittest discover -s tests -p 'test_csv_attributes.py' -v`通过；`git diff --cached --check`与`git diff --check`均退出0。完整`python -B scripts/check.py`在既有NumPy/SciPy环境下退出0，共42+14+26+6+39=127项测试通过。78个TCLab文件与修复前暂存版本逐字节一致。日志在`output/csv-line-endings/`，原失败输出保留为`before.log`。仅将`.gitattributes`修复加入暂存，不提交、推送或部署，不改变其他未提交工作的暂存状态。
