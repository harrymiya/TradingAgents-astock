import React, { useRef, useEffect, useCallback } from 'react';
import * as d3 from 'd3';
import './GraphCanvas.css';

// 蓝→红渐变（低→高）
function valueToColor(value, minVal = -10, maxVal = 10) {
  if (value === null || value === undefined) return '#8b949e';
  const t = Math.max(0, Math.min(1, (value - minVal) / (maxVal - minVal)));
  if (t < 0.5) {
    const s = t * 2;
    return d3.interpolateRgb('#1a6bff', '#ffb320')(s);
  } else {
    const s = (t - 0.5) * 2;
    return d3.interpolateRgb('#ffb320', '#ff2d2d')(s);
  }
}

// 环节节点颜色（固定方案）
const LINK_COLORS = ['#7c3aed', '#2563eb', '#0891b2', '#059669', '#d97706', '#dc2626', '#db2777', '#4f46e5'];

// ============================================================
// 模式1：力导向图
// ============================================================
function buildForceGraph(svg, data, industry, stockPrices, featData, colorMetric, onTooltip, onNodeClick, selectedNode, width, height) {
  const links_data = data['环节'];
  const nodes = [];
  const links = [];
  const nodeMap = {};

  const linkNames = Object.keys(links_data);
  const linkColorMap = {};
  linkNames.forEach((name, i) => {
    linkColorMap[name] = LINK_COLORS[i % LINK_COLORS.length];
  });

  let nodeIdx = 0;

  for (const [linkName, linkData] of Object.entries(links_data)) {
    const linkNode = {
      id: 'link_' + linkName,
      name: linkName,
      type: 'link',
      code: null,
      barrier: linkData['壁垒'],
      localRate: linkData['国产化率'],
      stockCount: linkData['股票'].length,
      upstream: linkData['上游'] || [],
      downstream: linkData['下游'] || [],
      desc: linkData['描述'],
      color: linkColorMap[linkName],
      r: 22 + linkData['壁垒'] * 4,
      stocks: linkData['股票'].map(c => ({
        code: c,
        name: (stockPrices[c] && stockPrices[c].name) || c,
      })),
    };
    nodes.push(linkNode);
    nodeMap[linkNode.id] = nodeIdx;
    nodeIdx++;

    for (const code of linkData['股票']) {
      const price = stockPrices[code] || {};
      const feat = (featData && featData[code]) || {};

      let metricVal, colorMin, colorMax, radMax;
      switch (colorMetric) {
        case 'chg': metricVal = price.chg || 0; colorMin = -10; colorMax = 10; radMax = 16; break;
        case 'yearChg': metricVal = price.yearChg || 0; colorMin = -30; colorMax = 50; radMax = 18; break;
        case 'volume': metricVal = Math.min((price.volume || 0) / 10000, 200); colorMin = 0; colorMax = 100; radMax = 20; break;
        case 'amplitude': metricVal = price.amplitude || 0; colorMin = 0; colorMax = 10; radMax = 16; break;
        case 'rsi': metricVal = feat.rsi !== undefined ? feat.rsi : 0; colorMin = -2; colorMax = 2; radMax = 14; break;
        case 's3_score': metricVal = feat.s3_score !== undefined ? feat.s3_score : 50; colorMin = 0; colorMax = 100; radMax = 18; break;
        case 'composite': metricVal = feat.composite !== undefined ? feat.composite : 50; colorMin = 0; colorMax = 100; radMax = 18; break;
        case 'pos_20d': metricVal = feat.pos_20d !== undefined ? feat.pos_20d : 50; colorMin = 0; colorMax = 100; radMax = 16; break;
        case 'ma20_pct': metricVal = feat.ma20_pct !== undefined ? feat.ma20_pct : 0; colorMin = -20; colorMax = 20; radMax = 16; break;
        default: metricVal = price.chg || 0; colorMin = -10; colorMax = 10; radMax = 14;
      }

      const absVal = Math.abs(metricVal);
      const r = Math.max(5, Math.min(radMax, 5 + (absVal / Math.max(Math.abs(colorMax || 10), Math.abs(colorMin || 10), 10)) * (radMax - 5)));

      let fillColor;
      if (colorMetric === 'rsi') fillColor = valueToColor(metricVal, -2, 2);
      else if (colorMetric === 'composite' || colorMetric === 's3_score') fillColor = valueToColor(metricVal, 0, 100);
      else fillColor = valueToColor(metricVal, colorMin, colorMax);

      const stockNode = {
        id: code,
        name: price.name || code,
        code: code,
        type: 'stock',
        price: price.price || 0,
        chg: price.chg || 0,
        yearChg: price.yearChg || 0,
        volume: price.volume || 0,
        amplitude: price.amplitude || 0,
        linkName: linkName,
        linkColor: linkColorMap[linkName],
        r: r,
        fillColor: fillColor,
        feat: feat,
      };
      nodes.push(stockNode);
      nodeMap[code] = nodeIdx;
      nodeIdx++;
      links.push({ source: code, target: 'link_' + linkName, type: 'belongs' });
    }

    for (const up of linkData['上游']) {
      if (links_data[up]) {
        links.push({ source: 'link_' + up, target: 'link_' + linkName, type: 'flow' });
      }
    }
  }

  const g = svg.append('g');

  // 缩放 + 拖拽平移（鼠标左键按住拖动）
  const zoom = d3.zoom()
    .scaleExtent([0.3, 4])
    .on('zoom', (event) => { g.attr('transform', event.transform); });
  svg.call(zoom);

  const simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(d => d.type === 'belongs' ? 60 : 120))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(d => d.r + 8));

  const defs = svg.append('defs');
  defs.append('marker')
    .attr('id', 'arrow').attr('viewBox', '0 -5 10 10').attr('refX', 20).attr('refY', 0)
    .attr('markerWidth', 6).attr('markerHeight', 6).attr('orient', 'auto')
    .append('path').attr('d', 'M0,-5L10,0L0,5').attr('fill', '#30363d');

  const linkG = g.append('g').selectAll('line')
    .data(links).join('line')
    .attr('class', 'link')
    .attr('stroke', d => d.type === 'flow' ? '#30363d' : '#21262d')
    .attr('stroke-width', d => d.type === 'flow' ? 1.5 : 1)
    .attr('stroke-dasharray', d => d.type === 'belongs' ? '3,3' : 'none')
    .attr('marker-end', d => d.type === 'flow' ? 'url(#arrow)' : null);

  const nodeG = g.append('g').selectAll('.node')
    .data(nodes).join('g').attr('class', 'node').style('cursor', 'pointer');

  nodeG.filter(d => d.type === 'link').append('circle')
    .attr('r', d => d.r).attr('fill', d => d.color).attr('fill-opacity', 0.25)
    .attr('stroke', d => d.color).attr('stroke-width', 2.5).style('transition', 'r 0.15s');

  nodeG.filter(d => d.type === 'link').append('circle')
    .attr('r', d => d.r + 4).attr('fill', 'none')
    .attr('stroke', d => d.color).attr('stroke-width', d => 1 + d.barrier * 0.5).attr('stroke-opacity', 0.3);

  nodeG.filter(d => d.type === 'stock').append('circle')
    .attr('r', d => d.r).attr('fill', d => d.fillColor || '#8b949e').attr('fill-opacity', 0.85)
    .attr('stroke', d => d.fillColor || '#8b949e').attr('stroke-width', 1.5).attr('stroke-opacity', 0.5);

  nodeG.filter(d => d.type === 'link').append('text')
    .attr('dy', 4).attr('text-anchor', 'middle').attr('fill', '#e6edf3')
    .attr('font-size', 12).attr('font-weight', 600).attr('pointer-events', 'none')
    .text(d => d.name.length > 5 ? d.name.slice(0, 5) + '..' : d.name);

  nodeG.filter(d => d.type === 'stock').append('text')
    .attr('dx', d => d.r + 5).attr('dy', 4).attr('fill', '#c9d1d9')
    .attr('font-size', 10).attr('pointer-events', 'none')
    .text(d => d.name);

  // 指标值标签（仅force模式用简短显示）
  nodeG.filter(d => d.type === 'stock').append('text')
    .attr('dx', d => d.r + 5).attr('dy', 16).attr('fill', '#8b949e')
    .attr('font-size', 8).attr('pointer-events', 'none')
    .text(d => {
      if (d.chg !== 0) return d.chgStr;
      return '';
    });

  const linkLabels = g.append('g').selectAll('.link-label')
    .data(links.filter(d => d.type === 'flow')).join('text')
    .attr('class', 'link-label').attr('fill', '#6e7681').attr('font-size', 9)
    .attr('text-anchor', 'middle').attr('pointer-events', 'none');

  nodeG.on('mouseenter', function(event, d) {
    const rect = svgRefCache.getBoundingClientRect();
    onTooltip({ node: d, x: event.clientX - rect.left, y: event.clientY - rect.top });
  });
  nodeG.on('mouseleave', (event, d) => {
    // 鼠标移出节点，清tooltip
    if (onTooltip) onTooltip(null);
  });
  nodeG.on('click', function(event, d) {
    event.stopPropagation();
    if (onNodeClick) onNodeClick(d);
  });
  svg.on('click', () => { if (onNodeClick) onNodeClick(null); });

  if (selectedNode) {
    nodeG.attr('opacity', d => {
      if (d.id === selectedNode.id) return 1;
      if (selectedNode.type === 'link' && d.linkName === selectedNode.linkName) return 1;
      if (selectedNode.type === 'stock' && d.type === 'stock') return 0.4;
      if (selectedNode.type === 'link' && d.type === 'stock' && d.linkName === selectedNode.name) return 1;
      return 0.3;
    });
  } else {
    nodeG.attr('opacity', 1);
  }

  nodeG.call(d3.drag()
    .on('start', (event, d) => {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x; d.fy = d.y;
    })
    .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y; })
    .on('end', (event, d) => {
      if (!event.active) simulation.alphaTarget(0);
      d.fx = null; d.fy = null;
    })
  );

  simulation.on('tick', () => {
    linkG.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    nodeG.attr('transform', d => `translate(${d.x},${d.y})`);
    linkLabels.attr('x', d => (d.source.x + d.target.x) / 2)
      .attr('y', d => (d.source.y + d.target.y) / 2).text(d => '↓');
  });

  setTimeout(() => {
    const bounds = g.node()?.getBBox();
    if (bounds) {
      const scale = Math.min(width / (bounds.width + 100), height / (bounds.height + 100), 1.5);
      const tx = (width - bounds.width * scale) / 2 - bounds.x * scale;
      const ty = (height - bounds.height * scale) / 2 - bounds.y * scale;
      svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
    }
  }, 1500);
}

let svgRefCache = null;

// ============================================================
// 模式2：横向流水线图（上下游列式布局）
//  每个环节节点在上方（带标题+描述），下方竖排列出该环节的股票
//  每个环节占一列，列宽自适应，整体居中
// ============================================================
function buildHorizontalGraph(svg, data, industry, stockPrices, featData, colorMetric, onTooltip, onNodeClick, selectedNode, width, height) {
  try {
  const links_data = data['环节'];
  const linkNames = Object.keys(links_data);

  // 环节颜色表
  const linkColorMap = {};
  linkNames.forEach((name, i) => {
    linkColorMap[name] = LINK_COLORS[i % LINK_COLORS.length];
  });

  // --- 1. 拓扑排序（分层，确定上下游顺序） ---
  const level = {};
  const inDeg = {};
  for (const name of linkNames) inDeg[name] = 0;
  for (const [name, ld] of Object.entries(links_data)) {
    for (const up of (ld['上游'] || [])) {
      if (links_data[up]) inDeg[name]++;
    }
  }

  let queue = [];
  for (const name of linkNames) {
    if (inDeg[name] === 0) {
      level[name] = 0;
      queue.push(name);
    }
  }
  if (queue.length === 0) {
    level[linkNames[0]] = 0;
    queue.push(linkNames[0]);
  }

  const visited = new Set(Object.keys(level));
  while (queue.length > 0) {
    const next = [];
    for (const name of queue) {
      const cur = level[name];
      for (const down of (links_data[name]['下游'] || [])) {
        if (links_data[down] && !visited.has(down)) {
          level[down] = cur + 1;
          visited.add(down);
          next.push(down);
        }
      }
    }
    queue = next;
  }
  const maxLvl = Math.max(...Object.values(level), 0);
  for (const name of linkNames) {
    if (!visited.has(name)) {
      level[name] = maxLvl + 1;
      visited.add(name);
    }
  }

  // --- 2. 按层级分组（每个level一列） ---
  const levelGroups = {};
  for (const [name, lvl] of Object.entries(level)) {
    if (!levelGroups[lvl]) levelGroups[lvl] = [];
    levelGroups[lvl].push(name);
  }
  const sortedLevels = Object.keys(levelGroups).sort((a, b) => Number(a) - Number(b));

  // --- 3. 每个环节展开为一列 ---
  // 把levelGroups展开为「每一列=1个环节」的扁平列表
  // 同时保留level序号做列背景色交替

  // 环节展开：一个环节 = 一列（含环节标题+股票列表）
  // 同一level（同层）的环节依次排列
  const columns = []; // [{name, level, links_data[name], stocks: []}]
  for (const lvl of sortedLevels) {
    for (const name of levelGroups[lvl]) {
      columns.push({
        name: name,
        level: Number(lvl),
        data: links_data[name],
        stocks: links_data[name]['股票'],
      });
    }
  }

  // --- 4. 列宽计算 ---
  // 列宽取决于该环节最多的股票数 + 环节标题的行高
  const STOCK_H = 24;       // 每个股票行高
  const SECTION_H = 80;     // 环节标题区域高度（圆+名称+家数）
  const COL_PAD = 20;       // 列内左右padding
  const COL_GAP = 16;       // 列间距
  const HEADER_H = 50;      // 顶部列标签高
  const MARGIN_T = HEADER_H + 10;
  const MARGIN_B = 30;

  // 基础列宽（显示6个字+涨跌幅+代码）
  const textWidth = 140;

  // 列高 = HEADER_H + 环节区域
  let maxColH = 0;
  const colHeights = columns.map(col => {
    const h = MARGIN_T + SECTION_H + col.stocks.length * STOCK_H + MARGIN_B;
    maxColH = Math.max(maxColH, h);
    return h;
  });

  // 内容总高度 = 顶部标签区 + 环节标题 + 股票列表 + 底部间距
  const contentH = maxColH + 40;
  // viewport高度 = 容器高度（不低于内容高度，如果有剩余空间则居中）
  const viewH = Math.max(height || 800, contentH);
  // 垂直偏移：内容在viewH中居中
  const offsetY = (viewH - contentH) / 2;

  // 列宽 = 每个股票项宽度（名称~7字+涨跌幅~6字+代码~6字=~19字*9px=~171px，加padding）
  // 用固定宽度200px
  const COL_W = 200;
  const totalW = columns.length * (COL_W + COL_GAP) - COL_GAP + COL_PAD * 2;

  // 计算整体水平偏移：居中
  const usableW = Math.max(width || 1200, totalW);
  const offsetX = (usableW - totalW) / 2;

  svg.attr('viewBox', `0 0 ${usableW} ${viewH}`)
     .style('width', '100%').style('height', '100%');

  // --- 5. 构建节点坐标 ---
  const nodes = [];
  const links = [];

  for (let ci = 0; ci < columns.length; ci++) {
    const col = columns[ci];
    const x = offsetX + COL_PAD + ci * (COL_W + COL_GAP);

    // 环节标题节点
    const color = linkColorMap[col.name];
    const linkNodeId = 'link_' + col.name;
    const linkY = offsetY + MARGIN_T + SECTION_H / 2;

    const linkNode = {
      id: linkNodeId,
      name: col.name,
      type: 'link',
      code: null,
      barrier: col.data['壁垒'],
      localRate: col.data['国产化率'],
      stockCount: col.stocks.length,
      upstream: col.data['上游'] || [],
      downstream: col.data['下游'] || [],
      desc: col.data['描述'],
      color: color,
      r: 22,
      x: x + COL_W / 2,
      y: linkY,
      stocks: col.stocks.map(c => ({
        code: c,
        name: (stockPrices[c] && stockPrices[c].name) || c,
      })),
    };
    nodes.push(linkNode);

    // 股票节点
    let sy = offsetY + MARGIN_T + SECTION_H + 4;
    for (const code of col.stocks) {
      const price = stockPrices[code] || {};
      const feat = (featData && featData[code]) || {};

      let metricVal, colorMin, colorMax;
      switch (colorMetric) {
        case 'chg': metricVal = price.chg || 0; colorMin = -10; colorMax = 10; break;
        case 'yearChg': metricVal = price.yearChg || 0; colorMin = -30; colorMax = 50; break;
        case 'volume': metricVal = Math.min((price.volume || 0) / 10000, 200); colorMin = 0; colorMax = 100; break;
        case 'amplitude': metricVal = price.amplitude || 0; colorMin = 0; colorMax = 10; break;
        case 'rsi': metricVal = feat.rsi !== undefined ? feat.rsi : 0; colorMin = -2; colorMax = 2; break;
        case 's3_score': metricVal = feat.s3_score !== undefined ? feat.s3_score : 50; colorMin = 0; colorMax = 100; break;
        case 'composite': metricVal = feat.composite !== undefined ? feat.composite : 50; colorMin = 0; colorMax = 100; break;
        case 'pos_20d': metricVal = feat.pos_20d !== undefined ? feat.pos_20d : 50; colorMin = 0; colorMax = 100; break;
        case 'ma20_pct': metricVal = feat.ma20_pct !== undefined ? feat.ma20_pct : 0; colorMin = -20; colorMax = 20; break;
        default: metricVal = price.chg || 0; colorMin = -10; colorMax = 10;
      }

      let fillColor;
      if (colorMetric === 'rsi') fillColor = valueToColor(metricVal, -2, 2);
      else if (colorMetric === 'composite' || colorMetric === 's3_score') fillColor = valueToColor(metricVal, 0, 100);
      else fillColor = valueToColor(metricVal, colorMin, colorMax);

      // 股票名称
      const nameStr = price.name || code;
      const codeShort = code.length >= 6 ? code.slice(-6) : code;

      const stockNode = {
        id: code,
        name: nameStr,
        code: codeShort,
        codeFull: code,
        type: 'stock',
        price: price.price || 0,
        chg: price.chg || 0,
        yearChg: price.yearChg || 0,
        volume: price.volume || 0,
        amplitude: price.amplitude || 0,
        linkName: col.name,
        linkColor: color,
        r: 5,
        fillColor: fillColor,
        x: x + COL_W / 2,
        y: sy + STOCK_H / 2,
        chgStr: (price.chg >= 0 ? '+' : '') + (price.chg || 0).toFixed(1) + '%',
        feat: feat,
      };
      nodes.push(stockNode);
      links.push({ source: code, target: linkNodeId });
      sy += STOCK_H;
    }

    // 环节间上游箭头
    for (const up of (col.data['上游'] || [])) {
      if (linkNames.includes(up)) {
        links.push({ source: 'link_' + up, target: linkNodeId, type: 'flow' });
      }
    }
  }

  // --- 6. 绘制 ---
  const g = svg.append('g');

  // 缩放 + 拖拽平移（鼠标左键按住拖动；Ctrl+滚轮缩放）
  const zoom = d3.zoom()
    .scaleExtent([0.3, 5])
    .on('zoom', (event) => { g.attr('transform', event.transform); });
  svg.call(zoom);

  // 列背景
  for (let ci = 0; ci < columns.length; ci++) {
    const x = offsetX + COL_PAD + ci * (COL_W + COL_GAP);
    g.append('rect')
      .attr('x', x).attr('y', offsetY).attr('width', COL_W).attr('height', contentH)
      .attr('fill', columns[ci].level % 2 === 0 ? '#161b22' : '#0d1117')
      .attr('opacity', 0.25);
  }

  // 顶部列标签
  for (let ci = 0; ci < columns.length; ci++) {
    const x = offsetX + COL_PAD + ci * (COL_W + COL_GAP);
    const lvl = columns[ci].level;
    const positions = ['上游', '中上游', '中游', '中下游', '下游'];
    const label = positions[Math.min(lvl, 4)];

    g.append('text')
      .attr('x', x + COL_W / 2).attr('y', offsetY + 16)
      .attr('text-anchor', 'middle').attr('fill', '#58a6ff')
      .attr('font-size', 11).attr('font-weight', 600)
      .text(label + '级');

    // 列分隔线
    if (ci < columns.length - 1) {
      g.append('line')
        .attr('x1', x + COL_W + COL_GAP / 2).attr('y1', offsetY + 0)
        .attr('x2', x + COL_W + COL_GAP / 2).attr('y2', offsetY + contentH)
        .attr('stroke', '#21262d').attr('stroke-width', 1).attr('stroke-dasharray', '4,4');
    }
  }

  // 列标题行（环节名称）
  for (let ci = 0; ci < columns.length; ci++) {
    const x = offsetX + COL_PAD + ci * (COL_W + COL_GAP);
    g.append('text')
      .attr('x', x + COL_W / 2).attr('y', offsetY + HEADER_H - 10)
      .attr('text-anchor', 'middle').attr('fill', '#e6edf3')
      .attr('font-size', 12).attr('font-weight', 600)
      .text(columns[ci].name.length > 8 ? columns[ci].name.slice(0, 8) + '..' : columns[ci].name);

    // 家数统计小字
    g.append('text')
      .attr('x', x + COL_W / 2).attr('y', offsetY + HEADER_H + 4)
      .attr('text-anchor', 'middle').attr('fill', '#6e7681')
      .attr('font-size', 10)
      .text(columns[ci].stocks.length + '家');
  }

  // 箭头定义
  const defs = svg.append('defs');
  defs.append('marker')
    .attr('id', 'harrow')
    .attr('viewBox', '0 -5 10 10').attr('refX', 18).attr('refY', 0)
    .attr('markerWidth', 6).attr('markerHeight', 6).attr('orient', 'auto')
    .append('path').attr('d', 'M0,-5L10,0L0,5').attr('fill', '#58a6ff');

  // 环节间上下游箭头
  for (const link of links) {
    if (link.type !== 'flow') continue;
    const srcNode = nodes.find(n => n.id === link.source);
    const tgtNode = nodes.find(n => n.id === link.target);
    if (!srcNode || !tgtNode) continue;

    // 水平箭头（两个不同列的环节之间）
    const srcX = srcNode.x + srcNode.r;
    const tgtX = tgtNode.x - tgtNode.r;
    g.append('line')
      .attr('x1', srcX).attr('y1', srcNode.y)
      .attr('x2', tgtX).attr('y2', tgtNode.y)
      .attr('stroke', '#58a6ff').attr('stroke-width', 1.5)
      .attr('stroke-opacity', 0.35).attr('marker-end', 'url(#harrow)');
  }

  // 节点组
  const nodeG = g.append('g').selectAll('.h-node')
    .data(nodes).join('g').attr('class', 'h-node').style('cursor', 'pointer');

  // 环节圆
  nodeG.filter(d => d.type === 'link').append('circle')
    .attr('cx', d => d.x).attr('cy', d => d.y)
    .attr('r', d => d.r).attr('fill', d => d.color)
    .attr('fill-opacity', 0.2).attr('stroke', d => d.color).attr('stroke-width', 2.5);

  nodeG.filter(d => d.type === 'link').append('circle')
    .attr('cx', d => d.x).attr('cy', d => d.y)
    .attr('r', d => d.r + 4).attr('fill', 'none').attr('stroke', d => d.color)
    .attr('stroke-width', d => 1 + (d.barrier || 0) * 0.5).attr('stroke-opacity', 0.3);

  // 环节圆内文字（环节简称）
  nodeG.filter(d => d.type === 'link').append('text')
    .attr('x', d => d.x).attr('y', d => d.y + 4)
    .attr('text-anchor', 'middle').attr('fill', '#e6edf3')
    .attr('font-size', 9).attr('font-weight', 600).attr('pointer-events', 'none')
    .text(d => d.name.length > 3 ? d.name.slice(0, 3) : d.name);

  // 股票圆点
  nodeG.filter(d => d.type === 'stock').append('circle')
    .attr('cx', d => d.x).attr('cy', d => d.y)
    .attr('r', d => d.r).attr('fill', d => d.fillColor || '#8b949e')
    .attr('fill-opacity', 0.85).attr('stroke', d => d.fillColor || '#8b949e')
    .attr('stroke-width', 1.5);

  // 股票名称（圆点右侧）
  nodeG.filter(d => d.type === 'stock').append('text')
    .attr('x', d => d.x + 10).attr('y', d => d.y + 3)
    .attr('fill', '#c9d1d9').attr('font-size', 10)
    .attr('pointer-events', 'none')
    .text(d => d.name);

  // 涨跌幅/指标值
  nodeG.filter(d => d.type === 'stock').append('text')
    .attr('x', d => d.x + 100).attr('y', d => d.y + 3)
    .attr('fill', d => {
      if (colorMetric === 'chg' || colorMetric === 'yearChg') {
        return d.chg >= 0 ? '#ff6b6b' : '#51cf66';
      }
      return '#ffb320';  // 其他指标用橙色
    })
    .attr('font-size', 9).attr('pointer-events', 'none')
    .text(d => {
      // 根据colorMetric显示对应数值
      switch(colorMetric) {
        case 'chg': return d.chgStr;
        case 'yearChg': return (d.yearChg >= 0 ? '+' : '') + (d.yearChg || 0).toFixed(1) + '%';
        case 'volume': return (d.volume / 10000).toFixed(0) + '万';
        case 'amplitude': return (d.amplitude || 0).toFixed(1) + '%';
        case 'rsi':
          if (d.feat && d.feat.rsi_label) return d.feat.rsi_label;
          return (d.feat && d.feat.rsi !== undefined) ? d.feat.rsi.toFixed(0) : '-';
        case 's3_score':
          if (d.feat && d.feat.s3_label) return d.feat.s3_label;
          return (d.feat && d.feat.s3_score !== undefined) ? d.feat.s3_score.toFixed(0) : '-';
        case 'composite': return (d.feat && d.feat.composite !== undefined) ? d.feat.composite.toFixed(0) : '-';
        case 'pos_20d': return (d.feat && d.feat.pos_20d !== undefined) ? d.feat.pos_20d.toFixed(0) : '-';
        case 'ma20_pct': return (d.feat && d.feat.ma20_pct !== undefined) ? d.feat.ma20_pct.toFixed(1) + '%' : '-';
        default: return d.chgStr;
      }
    });

  // 代码（灰色小字，涨跌幅右侧）
  nodeG.filter(d => d.type === 'stock').append('text')
    .attr('x', d => d.x + 142).attr('y', d => d.y + 3)
    .attr('fill', '#6e7681').attr('font-size', 9)
    .attr('pointer-events', 'none')
    .text(d => d.code);

  // 交互
  nodeG.on('mouseenter', function(event, d) {
    const rect = svgRefCache.getBoundingClientRect();
    onTooltip({ node: d, x: event.clientX - rect.left, y: event.clientY - rect.top });
  });
  nodeG.on('mouseleave', (event, d) => {
    // 鼠标移出节点，清tooltip
    if (onTooltip) onTooltip(null);
  });
  nodeG.on('click', function(event, d) {
    event.stopPropagation();
    if (onNodeClick) onNodeClick(d);
  });
  svg.on('click', () => { if (onNodeClick) onNodeClick(null); });

  if (selectedNode) {
    nodeG.attr('opacity', d => {
      if (d.id === selectedNode.id) return 1;
      if (selectedNode.type === 'link' && d.linkName === selectedNode.linkName) return 1;
      if (selectedNode.type === 'link' && d.type === 'stock' && d.linkName === selectedNode.name) return 1;
      return 0.3;
    });
  } else {
    nodeG.attr('opacity', 1);
  }
} catch(e) { 
  console.error('buildHorizontalGraph error:', e.message, e.stack); 
  var errDiv = document.createElement('div');
  errDiv.style.cssText = 'position:fixed;bottom:0;left:0;right:0;background:#f00;color:#fff;padding:8px;z-index:9999;font-size:12px';
  errDiv.textContent = 'Horizontal Error: ' + e.message;
  document.body.appendChild(errDiv);
}
}

// ============================================================
// 主组件
// ============================================================
export default function GraphCanvas({
  layoutMode, industry, industryData, stockPrices, featData,
  colorMetric, onTooltip, onNodeClick, selectedNode
}) {
  const svgRef = useRef(null);
  const containerRef = useRef(null);

  const buildGraph = useCallback(() => {
    const data = industryData[industry];
    if (!data || !svgRef.current || !data['环节']) return;

    const svg = d3.select(svgRef.current);
    const container = containerRef.current;
    const width = container.clientWidth || 1200;
    const height = container.clientHeight || 800;

    svg.selectAll('*').remove();
    svgRefCache = container;

    if (layoutMode === 'horizontal') {
      buildHorizontalGraph(svg, data, industry, stockPrices, featData, colorMetric, onTooltip, onNodeClick, selectedNode, width, height);
    } else {
      buildForceGraph(svg, data, industry, stockPrices, featData, colorMetric, onTooltip, onNodeClick, selectedNode, width, height);
    }
  }, [layoutMode, industry, industryData, stockPrices, colorMetric, onTooltip, onNodeClick, selectedNode]);

  useEffect(() => {
    buildGraph();
  }, [buildGraph]);

  useEffect(() => {
    const handleResize = () => buildGraph();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [buildGraph]);

  return (
    <div className="graph-wrapper" ref={containerRef}>
      <svg ref={svgRef}></svg>
    </div>
  );
}
