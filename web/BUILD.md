# 热模型案例页

独立静态页面：不在线拟合、不上传记录、不保存浏览历史、不访问统计或字体服务。展示的是同一TCLab记录已保存的100/300秒评估，来源在`real_data/tclab/assessment_examples/`。读者可切换窗口、逐点查看两温度通道、阅读参数边界和复算命令；无JavaScript时两组图表及结论仍在正文。

## 本地预览

从仓库根执行，仅需Python标准库：

```sh
python -B web/build.py --output output/site-preview
python -m http.server 8765 --bind 127.0.0.1 --directory output/site-preview
```

浏览`http://127.0.0.1:8765/`。输出目录必须不存在，重建用新目录；构建不修改研究数据。默认带`noindex`及禁止抓取的robots，不设置虚构正式网址，不意味着已发布。

本次验收的实例位于`output/site-preview`，使用`http://127.0.0.1:18766/`（8766已被其他服务占用，未终止它）。端口仅用于本地查看，不是公网发布地址。

页面由`index.template.html`、`style.css`、`app.js`和真实结果确定性生成。构建器核对原数据、保存拟合和相关源码哈希，并独立重算CSV指标，输出图表、可下载证据和来源清单。标记与数值取自相同结果，不手填“更优”指标。两窗口共享时间与温度坐标，保留全部599个采样点，不将后段当作新增试验。

## 正式站点构建（不执行发布）

获得正式HTTPS网址后，可传`--base-url https://实际域名/路径/`构建到另一个新目录。只接受无凭据/查询/片段的HTTPS网址；据此生成canonical、Open Graph URL/image、sitemap及robots。默认预览不宣称远程可用。

正式发布仍需要另外确认托管位置、先发布对应分析代码、核对许可，再部署并检查线上状态。不要仅因构建成功就把正式域名当成可访问。本站不新增部署workflow，不选择原创代码许可证，不保证搜索收录或生成式搜索引用。

## 内容与边界

- 新评估采用摄氏度残差平方和，不能与旧相对摄氏度目标混作算法对照。
- 100/300秒是同一记录的两个前缀，不是两个独立案例；局部数值秩不等于参数置信。
- 网页展示的均为已保存结果；无设备控制、功率配方或最优补测收益证明。
- 证据复制到站点内，预览时不依赖尚未推送的GitHub文件；原作者来源以固定提交链接标注。
- 原始记录与CSV下载是Apache-2.0上游样例的使用与派生；提供上游许可和归属。原创代码尚无统一许可，页面明确提示，不生成虚假软件许可证字段。

## 验收

构建测试放在根`tests/test_case_site.py`，被现有`python scripts/check.py`覆盖。浏览器使用Playwright CLI验收，不新增Node依赖或浏览器测试框架。检查窗口切换、键盘、逐点读数、复制成功/失败、无JavaScript、移动端溢出及本地资源请求。900px/360px截图及日志保存在`output/playwright/`，不作为科学测量证据。

复跑本次浏览器验收时，在18766端口启动预览，再使用已有Playwright CLI会话执行：

```sh
bash ~/.codex/skills/playwright/scripts/playwright_cli.sh -s=thermal-case open http://127.0.0.1:18766/
bash ~/.codex/skills/playwright/scripts/playwright_cli.sh -s=thermal-case run-code "$(cat web/verify_browser.js)"
```

`verify_browser.js`是交给CLI执行的浏览器检查函数，不是页面运行时代码，不引入npm项目。运行环境需已有Playwright浏览器；CLI启动可能按其自身机制安装工具，本页面的构建与浏览均不需要它。分享PNG由1200×630的`social-card.svg`在浏览器渲染得到，不使用AI生成图或虚构测量曲线。正式站点URL只影响索引元数据，本次未部署或提交。
