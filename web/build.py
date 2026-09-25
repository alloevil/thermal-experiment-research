"""Build a static, evidence-backed TCLab case page without scientific dependencies."""

import argparse
import csv
import hashlib
import html
import json
import math
import shutil
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
WEB = Path(__file__).resolve().parent
CASE = ROOT / 'real_data/tclab'
TITLE = '拟合成功，参数就可信吗？｜TCLab 热模型辨识实测案例'
DESCRIPTION = '用同一条599行TCLab双加热器实测记录，对照100/300秒训练窗口、参数信息与后续预测。查看零输入、参数边界和可复算证据；不是设备控制或最优补测承诺。'
REPOSITORY = 'https://github.com/alloevil/thermal-experiment-research'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_case(cutoff, case_root=CASE):
    folder = case_root / f'assessment_examples/before-{cutoff}'
    report = json.loads((folder / 'report.json').read_text())
    config = json.loads((folder / 'run-config.json').read_text())
    require(json.loads((folder / 'status.json').read_text())['status'] == 'COMPLETED', 'Incomplete assessment')
    require(report['fit']['optimizer_success'], 'Failed fit cannot be presented as completed')
    require(report['source']['sha256'] == digest(case_root / 'upstream/data.txt'), 'Changed measured source')
    require(report['fit_sha256'] == digest(folder / 'fit.json'), 'Changed frozen fit')
    require(report['fit'] == json.loads((folder / 'fit.json').read_text()), 'Report/fit mismatch')
    for name, expected in config['source_hashes'].items():
        require(digest(case_root / name) == expected, f'Assessment source changed: {name}')
    with (folder / 'prediction.csv').open(newline='') as stream:
        reader = csv.reader(stream)
        require(next(reader) == ['time_s', 'training', 'measured_T1_C', 'measured_T2_C', 'predicted_T1_C', 'predicted_T2_C'], 'Unexpected prediction schema')
        rows = [[float(value) for value in row] for row in reader]
    with (case_root / 'upstream/data.txt').open(newline='') as stream:
        source = list(csv.reader(stream))[1:]
    require(len(rows) == len(source) == 599, 'This narrative is tied to the 599-row sample')
    for row, original in zip(rows, source):
        require(len(row) == 6 and all(math.isfinite(value) for value in row), 'Invalid chart row')
        require(row[0] == float(original[0]) and row[2:4] == [float(value) for value in original[3:5]], 'Chart measurements differ from source')
        require(row[1] == int(row[0] < cutoff), 'Wrong training mask')
    require(report['selection']['before_seconds_exclusive'] == cutoff, 'Wrong report window')
    for label, flag in [('training', 1), ('validation', 0)]:
        selected = [row for row in rows if row[1] == flag]
        require(len(selected) == report['selection'][f'{label}_rows'], 'Wrong row count')
        squared = [(row[channel + 4] - row[channel + 2])**2 for row in selected for channel in range(2)]
        rmse = math.sqrt(math.fsum(squared) / len(squared))
        require(math.isclose(rmse, report[f'{label}_metrics']['rmse_C'], rel_tol=1e-12, abs_tol=1e-10), 'Reported RMSE differs from plotted data')
    require(report['engineering_release'] == 'not_supported' and report['precision_status'] == 'not_established', 'Unsupported claim status')
    return report, rows


def chart(rows, cutoff, width, mobile, temperature_max):
    left, right = 36, width - 12
    plot_width = right - left
    height = 388 if mobile else 352
    plot_height = 128 if mobile else 110
    starts = [30, height - plot_height - 38]
    chart_id = f'plot-{cutoff}-{"mobile" if mobile else "desktop"}'
    split = left + cutoff / 600 * plot_width
    output = [f'<svg class="{ "mobile-plot" if mobile else "desktop-plot"}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{chart_id}-title {chart_id}-desc">',
              f'<title id="{chart_id}-title">{cutoff}秒训练窗口的两通道实测与冻结参数预测</title>',
              f'<desc id="{chart_id}-desc">全部599个采样点。淡蓝为训练，白色为后续检验；实线是实测，虚线是模型预测。两窗口共享0至600秒和10至{temperature_max}摄氏度坐标。</desc>']
    for channel, top in enumerate(starts):
        bottom = top + plot_height
        output += [f'<text x="{left}" y="{top - 12}" class="axis channel-name">T{channel + 1} · °C</text>',
                   f'<rect class="train-region" x="{left}" y="{top}" width="{split-left:.3f}" height="{plot_height}"/>']
        for temperature in range(10, temperature_max + 1, 20):
            vertical = bottom - (temperature - 10) / (temperature_max - 10) * plot_height
            output += [f'<line class="grid-line" x1="{left}" x2="{right}" y1="{vertical:.3f}" y2="{vertical:.3f}"/>',
                       f'<text class="axis" x="{left-9}" y="{vertical+4:.3f}" text-anchor="end">{temperature}</text>']
        for column, name in [(channel + 2, 'measured'), (channel + 4, 'predicted')]:
            points = ' '.join(f'{left + row[0]/600*plot_width:.3f},{bottom - (row[column]-10)/(temperature_max-10)*plot_height:.3f}' for row in rows)
            output.append(f'<polyline class="curve channel-{channel+1} {name}" data-samples="{len(rows)}" points="{points}"/>')
        output += [f'<line class="split-line" x1="{split:.3f}" x2="{split:.3f}" y1="{top}" y2="{bottom}"/>',
                   f'<line class="cursor-line" data-cursor data-left="{left}" data-width="{plot_width}" x1="{split:.3f}" x2="{split:.3f}" y1="{top}" y2="{bottom}"/>']
    for elapsed in [0, 200, 400, 600]:
        horizontal = left + elapsed / 600 * plot_width
        output.append(f'<text class="axis" x="{horizontal:.3f}" y="{height-18}" text-anchor="middle">{elapsed}</text>')
    output += [f'<text class="axis" x="{right}" y="{height-2}" text-anchor="end">时间 / s</text>', '</svg>']
    return '\n'.join(output)


def case_markup(cutoff, report, rows, temperature_max):
    early = cutoff == 100
    heading = '这段数据里，根本没有 α₂ 的信息。' if early else '有了两路输入，参数也未必可信。'
    explanation = ('已观测训练区间内 Q₂ 始终为零。α₂ 不进入模型响应，因此优化器给出的默认值不是估计结果。'
                   if early else '局部数值秩达到3，但 U 仍触及作者设定下界。U 与 α₁ 的灵敏度形状相近，需审查参数补偿、模型和测量前提。')
    parameter_rows = []
    for index, name in enumerate(['U', 'α₁', 'α₂']):
        fixed = report['fit']['parameter_order'][index] in report['fit']['fixed_unexcited_parameters']
        bound = report['fit']['active_bound_mask'][index]
        label = '默认假设 · 未估计' if fixed else ('拟合触下界' if bound == -1 else '拟合值 · 精度未确立')
        parameter_rows.append(f'<tr><th scope="row">{name}</th><td>{report["fit"]["parameters"][index]:.7g}</td><td><span class="parameter-tag {"caution" if fixed or bound else "neutral"}">{label}</span></td></tr>')
    next_step = ('先寻找 Q₂ 输入生效后的已有温度记录，或取得独立增益标定。不要把默认 α₂ 当作数据支持的结论。'
                 if early else '先核对 U 的范围依据、固定23°C环境假设与传感器噪声。不要仅凭“有输入”就追加更大功率的试验。')
    return f'''<section class="case-panel" id="case-{cutoff}" data-case="{cutoff}" aria-labelledby="case-title-{cutoff}">
      <div class="case-topline"><h3 id="case-title-{cutoff}">前 {cutoff} 秒训练 · 后续冻结检验</h3><span class="micro-label">SAVED RESULT / 非实时拟合</span></div>
      <div class="case-layout">
        <div class="plot-area">
          <div class="plot-legend"><span class="key key-blue">T₁ 实测</span><span class="key key-orange">T₂ 实测</span><span class="key key-dashed">模型预测</span><span class="key key-shade">训练区间</span></div>
          <div class="plots">{chart(rows, cutoff, 860, False, temperature_max)}{chart(rows, cutoff, 300, True, temperature_max)}</div>
          <div class="point-inspector" hidden><label for="point-{cutoff}">沿记录查看 <span>← → 也可逐点移动</span></label><input id="point-{cutoff}" type="range" min="0" max="598" value="{cutoff-1}" aria-describedby="reading-{cutoff}"><output id="reading-{cutoff}" class="point-reading"></output></div>
          <p class="chart-caption">同一条记录的599个采样点，无降采样。实线为测量，虚线为模型；切换窗口不会改变坐标尺度。</p>
        </div>
        <aside class="diagnosis" aria-label="{cutoff}秒窗口诊断">
          <div class="eyebrow">WHAT THE DATA CAN SAY</div><h4>{heading}</h4><p>{explanation}</p>
          <dl class="metrics"><div><dt>训练 RMSE</dt><dd data-metric="training">{report['training_metrics']['rmse_C']:.3f}<small> °C</small></dd></div><div><dt>后续 RMSE</dt><dd data-metric="validation">{report['validation_metrics']['rmse_C']:.3f}<small> °C</small></dd></div></dl>
          <table class="parameter-table"><caption>参数值与来源</caption><thead><tr><th>参数</th><th>数值</th><th>状态</th></tr></thead><tbody>{''.join(parameter_rows)}</tbody></table>
          <p class="fine-print">U：W/(m² K)；α：W/%。数值秩 {report['local_information']['numerical_rank']}/3 不等于统计置信或全局可辨识。</p>
          <div class="next-step"><span>下一步，不是执行指令</span><p>{next_step}</p></div>
          <a class="text-link" href="evidence/before-{cutoff}/report.md">查看完整诊断卡 <span aria-hidden="true">↗</span></a>
        </aside>
      </div>
    </section>'''


def normalize_base(value):
    if value is None:
        return None
    parsed = urlsplit(value)
    require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password
            and not parsed.query and not parsed.fragment and not any(character.isspace() for character in value)
            and not any(character in value for character in '<>"\\'), 'Use a clean absolute HTTPS base URL without credentials/query/fragment')
    require(not any(part in ['.', '..'] for part in parsed.path.split('/')), 'Base path must be canonical')
    return value.rstrip('/') + '/'


def render(base=None):
    cases = {str(cutoff): load_case(cutoff) for cutoff in [100, 300]}
    temperature_max = math.ceil(max(row[index] for _, rows in cases.values() for row in rows for index in range(2, 6)) / 10) * 10
    metadata = [f'<meta name="robots" content="{"index, follow" if base else "noindex, nofollow"}">']
    if base:
        metadata += [f'<link rel="canonical" href="{html.escape(base, quote=True)}">',
                     f'<meta property="og:url" content="{html.escape(base, quote=True)}">',
                     f'<meta property="og:image" content="{html.escape(base, quote=True)}social-card.png">',
                     '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">']
    schema = {'@context': 'https://schema.org', '@type': 'TechArticle', 'headline': TITLE,
              'description': DESCRIPTION, 'inLanguage': 'zh-CN', 'isAccessibleForFree': True,
              'about': ['Thermal model identification', 'Parameter identifiability', 'TCLab'],
              'author': {'@type': 'Person', 'name': 'alloevil', 'url': 'https://github.com/alloevil'},
              'citation': ['https://github.com/APMonitor/arduino/tree/f36e65a70dd7122d1829883899e40e56bf6c4279/2_Regression/Energy_balance_MIMO/Python_minimize'],
              'isBasedOn': {'@type': 'SoftwareSourceCode', 'name': 'Thermal Experiment Research',
                            'codeRepository': REPOSITORY, 'programmingLanguage': 'Python'}}
    if base:
        schema['url'] = base
        schema['image'] = base + 'social-card.png'
    tokens = {'TITLE': html.escape(TITLE), 'DESCRIPTION': html.escape(DESCRIPTION, quote=True),
              'METADATA': '\n'.join(metadata), 'SCHEMA': json.dumps(schema, ensure_ascii=False).replace('<', '\\u003c'),
              'PREVIEW': '' if base else '<div class="preview-note">本地预览 · 此构建尚未部署</div>',
              'COSINE': f"{cases['300'][0]['local_information']['column_cosines'][0]['cosine']:.6f}",
              'CASES': '\n'.join(case_markup(int(cutoff), report, rows, temperature_max) for cutoff, (report, rows) in cases.items()),
              'DATA': json.dumps({cutoff: rows for cutoff, (_, rows) in cases.items()}, separators=(',', ':')).replace('<', '\\u003c')}
    content = (WEB / 'index.template.html').read_text()
    for token, value in tokens.items():
        content = content.replace('{{' + token + '}}', value)
    require('{{' not in content, 'Unresolved page placeholder')
    return content


def build(output, base_url=None):
    base = normalize_base(base_url)
    output = Path(output)
    require(not output.exists() and not output.is_symlink(), 'Output exists; use a new directory')
    content = render(base)
    output.mkdir(parents=True)
    (output / 'index.html').write_text(content)
    for name in ['style.css', 'app.js', 'icon.svg', 'social-card.svg', 'social-card.png']:
        shutil.copyfile(WEB / name, output / name)
    evidence = output / 'evidence'
    evidence.mkdir()
    for cutoff in [100, 300]:
        target = evidence / f'before-{cutoff}'
        target.mkdir()
        for name in ['report.json', 'report.md', 'prediction.csv', 'run-config.json', 'fit.json']:
            shutil.copyfile(CASE / f'assessment_examples/before-{cutoff}' / name, target / name)
    for name in ['ASSESSMENT.md', 'ASSESSMENT_RESULTS.md', 'ATTRIBUTION.md']:
        shutil.copyfile(CASE / name, evidence / name)
    shutil.copyfile(CASE / 'upstream/LICENSE', evidence / 'UPSTREAM-LICENSE.txt')
    records = [{'file': str(path.relative_to(output)), 'sha256': digest(path)} for path in sorted(evidence.rglob('*')) if path.is_file()]
    (evidence / 'manifest.json').write_text(json.dumps(records, indent=2) + '\n')
    robots = f'User-agent: *\nAllow: /\nSitemap: {base}sitemap.xml\n' if base else 'User-agent: *\nDisallow: /\n'
    (output / 'robots.txt').write_text(robots)
    if base:
        (output / 'sitemap.xml').write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>{html.escape(base)}</loc></url></urlset>\n')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-url')
    args = parser.parse_args()
    try:
        output = build(args.output, args.base_url)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f'Case page build failed: {error}\n')
    print(f'GENERATED {output / "index.html"}; not deployed. Evidence checked; {"release URL configured" if args.base_url else "noindex preview"}.')


if __name__ == '__main__':
    main()
