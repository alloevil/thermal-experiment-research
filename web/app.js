'use strict';

(() => {
  const dataElement = document.getElementById('case-data');
  const panels = [...document.querySelectorAll('[data-case]')];
  let records;
  try {
    records = JSON.parse(dataElement.textContent);
    if (!panels.every(panel => Array.isArray(records[panel.dataset.case]) && records[panel.dataset.case].length === 599)) {
      throw new Error('Incomplete case data');
    }
  } catch {
    const notice = document.createElement('p');
    notice.className = 'notice';
    notice.textContent = '交互数据未能加载；下方静态图表与结论仍可阅读。请使用证据文件核对。';
    document.querySelector('.explorer-toolbar').after(notice);
    return;
  }

  const command = document.getElementById('run-command');
  const announcement = document.getElementById('case-announcement');
  const copyStatus = document.getElementById('copy-status');
  const radios = [...document.querySelectorAll('input[name="window"]')];

  function inspect(panel) {
    const slider = panel.querySelector('input[type="range"]');
    const row = records[panel.dataset.case][Number(slider.value)];
    const output = panel.querySelector('output');
    output.replaceChildren();
    const readings = [
      ['时间 / ' + (row[1] === 1 ? '训练' : '后续'), row[0].toFixed(3) + ' s'],
      ['T₁ 实测 / 预测', row[2].toFixed(2) + ' / ' + row[4].toFixed(2) + ' °C'],
      ['T₂ 实测 / 预测', row[3].toFixed(2) + ' / ' + row[5].toFixed(2) + ' °C']
    ];
    readings.forEach(([label, value]) => {
      const item = document.createElement('div');
      const name = document.createElement('span');
      name.textContent = label;
      item.append(name, document.createTextNode(value));
      output.append(item);
    });
    slider.setAttribute('aria-valuetext', readings.map(([label, value]) => label + ' ' + value).join('；'));
    panel.querySelectorAll('[data-cursor]').forEach(cursor => {
      const horizontal = Number(cursor.dataset.left) + row[0] / 600 * Number(cursor.dataset.width);
      cursor.setAttribute('x1', String(horizontal));
      cursor.setAttribute('x2', String(horizontal));
    });
  }

  function selectWindow(cutoff) {
    if (!records[cutoff]) return;
    panels.forEach(panel => { panel.hidden = panel.dataset.case !== cutoff; });
    radios.forEach(radio => { radio.checked = radio.value === cutoff; });
    command.textContent = `.venv/bin/python -B real_data/tclab/assess.py \\\n  --data real_data/tclab/upstream/data.txt \\\n  --before-seconds ${cutoff} --accept-model-assumptions \\\n  --output /tmp/tclab-case-${cutoff}`;
    document.getElementById('command-context').textContent = `当前示例 · 前${cutoff}秒训练`;
    copyStatus.textContent = '输出目录必须不存在；重跑请换一个新路径。';
    announcement.textContent = `正在展示前${cutoff}秒训练的已保存结果，不是实时拟合。`;
  }

  panels.forEach(panel => {
    panel.querySelector('.point-inspector').hidden = false;
    panel.querySelector('input[type="range"]').addEventListener('input', () => inspect(panel));
    inspect(panel);
  });
  radios.forEach(radio => radio.addEventListener('change', () => selectWindow(radio.value)));
  document.querySelector('.window-switch').hidden = false;
  document.documentElement.classList.add('enhanced');
  const fromHash = () => {
    const match = location.hash.match(/^#case-(100|300)$/);
    if (match) selectWindow(match[1]);
  };
  selectWindow(location.hash === '#case-300' ? '300' : '100');
  window.addEventListener('hashchange', fromHash);

  const copyButton = document.getElementById('copy-command');
  copyButton.hidden = false;
  copyButton.addEventListener('click', async () => {
    const text = command.textContent;
    copyButton.disabled = true;
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(text);
      copyStatus.textContent = '命令已复制。请在仓库根目录运行，并使用新的输出目录。';
    } catch {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(command);
      selection.removeAllRanges();
      selection.addRange(range);
      command.parentElement.focus();
      copyStatus.textContent = '未能自动复制，已选中命令。请手动复制；没有执行任何命令。';
    } finally {
      copyButton.disabled = false;
    }
  });
})();
