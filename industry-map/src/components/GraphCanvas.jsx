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

const LINK_COLORS = ['#b79ad9', '#89abe8', '#7ec8e0', '#7fbf9f', '#dbb86d', '#e0877c', '#d99bb6', '#7e8fd6', '#9ab87a', '#c9a06d'];
const SECTION_COLORS = ['#58a6ff', '#7ec8e0', '#d29922', '#f0883e', '#3fb950', '#d99bb6'];

/** 根据着色指标获取颜色和半径 */
function getStockColorAndRadius(price, colorMetric) {
  let metricVal, colorMin, colorMax;
  switch (colorMetric) {
    case 'chg': metricVal = price.chg || 0; colorMin = -10; colorMax = 10; break;
    case 'yearChg': metricVal = price.yearChg || 0; colorMin = -30; colorMax = 50; break;
    case 'volume': metricVal = Math.min((price.volume || 0) / 10000, 200); colorMin = 0; colorMax = 100; break;
    case 'amplitude': metricVal = price.amplitude || 0; colorMin = 0; colorMax = 10; break;
    default: metricVal = price.chg || 0; colorMin = -10; colorMax = 10;
  }
  const fillColor = valueToColor(metricVal, colorMin, colorMax);
  const absVal = Math.abs(metricVal);
  const r = Math.max(4, Math.min(10, 4 + (absVal / Math.max(Math.abs(colorMax), Math.abs(colorMin), 10)) * 6));
  return { fillColor, r };
}

// ============================================================
// 模式1：力导向图（原版保留）
// ============================================================
function buildForceGraph(svg, industry, stockPrices, colorMetric, onTooltip, onNodeClick, selectedNode, width, height) {
  if (!industry || !industry.sections) return;
  const nodes = [];
  const links = [];
  let idx = 0;

  for (const sec of industry.sections) {
    for (const link of sec.links) {
      const linkNode = {
        id: 'link_' + link.name, name: link.name, type: 'link', code: null,
        r: 20, stocks: link.stocks || [],
        color: LINK_COLORS[idx % LINK_COLORS.length],
      };
      nodes.push(linkNode);
      idx++;

      for (const raw of (link.stocks || [])) {
        const code = typeof raw === 'string' ? raw : raw.code;
        const stockName = typeof raw === 'object' ? raw.name : (stockPrices[code]?.name || code);
        const codeStr = code;
        const price = stockPrices[codeStr] || {};
        const { fillColor, r } = getStockColorAndRadius(price, colorMetric);
        nodes.push({
          id: codeStr, name: stockName, code: codeStr, type: 'stock',
          price: price.price || 0, chg: price.chg || 0,
          r, fillColor, linkName: link.name, linkColor: linkNode.color,
        });
        links.push({ source: codeStr, target: 'link_' + link.name, type: 'belongs' });
      }
    }
  }

  const g = svg.append('g');
  const zoom = d3.zoom().scaleExtent([0.3, 4])
    .filter(event => !event.target.closest('.f-node'))
    .on('zoom', (event) => g.attr('transform', event.transform));
  svg.call(zoom);

  const simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(d => d.type === 'belongs' ? 60 : 120))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(d => d.r + 8));

  const linkG = g.append('g').selectAll('line').data(links).join('line')
    .attr('stroke', '#21262d').attr('stroke-width', 1).attr('stroke-dasharray', '3,3');

  const nodeG = g.append('g').selectAll('.f-node').data(nodes).join('g').attr('class', 'f-node').style('cursor', 'pointer');

  nodeG.filter(d => d.type === 'link').append('circle').attr('r', d => d.r).attr('fill', d => d.color).attr('fill-opacity', 0.25).attr('stroke', d => d.color).attr('stroke-width', 2.5);
  nodeG.filter(d => d.type === 'link').append('text').attr('dy', 4).attr('text-anchor', 'middle').attr('fill', '#e6edf3').attr('font-size', 11).attr('font-weight', 600).text(d => d.name.length > 5 ? d.name.slice(0, 5) + '..' : d.name);
  nodeG.filter(d => d.type === 'stock').append('circle').attr('r', d => d.r).attr('fill', d => d.fillColor || '#8b949e').attr('fill-opacity', 1.0).attr('stroke', d => d.fillColor || '#8b949e').attr('stroke-width', 2.5);
  nodeG.filter(d => d.type === 'stock').append('text').attr('dx', 8).attr('dy', 4).attr('fill', '#c9d1d9').attr('font-size', 9).text(d => d.name);

  // 交互
  nodeG.on('mouseenter', function(event, d) {
    const rect = svg.node().getBoundingClientRect();
    if (onTooltip) onTooltip({ node: d, x: event.clientX - rect.left, y: event.clientY - rect.top });
  });
  nodeG.on('mouseleave', () => { if (onTooltip) onTooltip(null); });
  nodeG.on('click', function(event, d) { event.stopPropagation(); if (onNodeClick) onNodeClick(d); });
  svg.on('click', () => { if (onNodeClick) onNodeClick(null); });

  // 选中高亮
  if (selectedNode) {
    nodeG.filter(d => d.id === selectedNode.id).each(function(d) {
      const group = d3.select(this);
      if (d.type === 'stock') {
        // 公司节点：圆点(0,0,r≈4-10) + 名称文字(dx=8) + 涨跌幅
        // 框住圆点+名称+涨跌幅整体
        group.insert('rect', ':first-child').attr('class', 'sel-box')
          .attr('x', -8).attr('y', -10)
          .attr('width', 140).attr('height', 20)
          .attr('fill', 'none').attr('stroke', '#58a6ff').attr('stroke-width', 1.5).attr('rx', 4);
      } else {
        // 环节节点：大圆+居中文字
        group.insert('rect', ':first-child').attr('class', 'sel-box')
          .attr('x', -(d.r || 20) - 4).attr('y', -(d.r || 20) - 4)
          .attr('width', (d.r || 20) * 2 + 8).attr('height', (d.r || 20) * 2 + 8)
          .attr('fill', 'none').attr('stroke', '#58a6ff').attr('stroke-width', 1.5).attr('rx', 4);
      }
    });
  }

  nodeG.call(d3.drag()
    .on('start', (event, d) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
    .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y; })
    .on('end', (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
  );

  simulation.on('tick', () => {
    linkG.attr('x1', d => d.source.x).attr('y1', d => d.source.y).attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    nodeG.attr('transform', d => `translate(${d.x},${d.y})`);
  });
}

// ============================================================
// 模式2：横向表格（一级为文字标题，环节垂直列表，公司圆点）
// ============================================================
function buildHorizontalTable(svg, industry, stockPrices, colorMetric, onTooltip, onNodeClick, selectedNode, width, height, zoomStateRef) {
  try {
    const sections = industry.sections || [];
    if (sections.length === 0) return;

    const COL_W = 210, COL_GAP = 24, STOCK_H = 18, BETWEEN_LINK_H = 14;
    const PADDING_TOP = 70;

    const linkColorMap = {};
    let ci = 0;
    for (const sec of sections) {
      for (const link of sec.links) { linkColorMap[link.name] = LINK_COLORS[ci % LINK_COLORS.length]; ci++; }
    }

    const colHeights = {};
    for (let i = 0; i < sections.length; i++) {
      let h = 0;
      for (const link of sections[i].links) {
        h += 22 + (link.stocks || []).length * STOCK_H + BETWEEN_LINK_H;
      }
      colHeights[i] = h;
    }

    const layoutW = sections.length * COL_W + (sections.length - 1) * COL_GAP;
    const maxColH = Math.max(...Object.values(colHeights), 0);
    const viewH = Math.max(height || 800, PADDING_TOP + maxColH + 60);
    const viewW = Math.max(width || 1200, layoutW + 40);
    svg.attr('viewBox', `0 0 ${viewW} ${viewH}`).style('width', '100%').style('height', '100%');

    const offsetX = Math.max(0, (viewW - layoutW) / 2);
    const colX = {};
    for (let i = 0; i < sections.length; i++) colX[i] = offsetX + i * (COL_W + COL_GAP) + COL_W / 2;

    const g = svg.append('g');
    // 横向表格支持滚轮缩放+鼠标拖拽平移
    const zoom = d3.zoom().scaleExtent([0.3, 5])
      .filter(event => {
        // 滚轮缩放 + 鼠标拖拽（排除stock-row内的点击）
        if (event.type === 'wheel') return true;
        if (event.type === 'mousedown') return !event.target.closest('.stock-row');
        return false;
      })
      .on('zoom', (event) => {
        zoomStateRef.current = event.transform;
        g.attr('transform', event.transform);
      });
    svg.call(zoom);
    // 恢复上次缩放状态（手动设置g的transform，不触发zoom事件）
    if (zoomStateRef.current) {
      g.attr('transform', zoomStateRef.current);
    }

    for (let i = 0; i < sections.length; i++) {
      const cx = colX[i];
      g.append('rect').attr('x', cx - COL_W / 2).attr('y', PADDING_TOP - 10).attr('width', COL_W).attr('height', (colHeights[i] || 0) + 20).attr('fill', i % 2 === 0 ? '#161b22' : '#0d1117').attr('rx', 6).attr('opacity', 0.25);
      g.append('text').attr('x', cx).attr('y', PADDING_TOP - 14).attr('text-anchor', 'middle').attr('fill', '#8b949e').attr('font-size', 13).attr('font-weight', 700).text(sections[i].name);
      g.append('line').attr('x1', cx - COL_W / 2 + 6).attr('y1', PADDING_TOP - 6).attr('x2', cx + COL_W / 2 - 6).attr('y2', PADDING_TOP - 6).attr('stroke', '#21262d').attr('stroke-width', 1).attr('stroke-dasharray', '4,4');

      let yPos = PADDING_TOP + 4;
      for (const link of sections[i].links) {
        const subColor = linkColorMap[link.name] || '#8b949e';
        g.append('rect').attr('x', cx - COL_W / 2 + 4).attr('y', yPos).attr('width', 3).attr('height', 14).attr('rx', 1.5).attr('fill', subColor);
        g.append('text').attr('x', cx - COL_W / 2 + 12).attr('y', yPos + 12).attr('fill', subColor).attr('font-size', 11).attr('font-weight', 700).text(link.name.length > 12 ? link.name.slice(0, 12) + '..' : link.name);

        let sy = yPos + 18;
        for (const raw of (link.stocks || [])) {
          const code = typeof raw === 'string' ? raw : raw.code;
          const stockName = typeof raw === 'object' ? raw.name : (stockPrices[code]?.name || code);
          const { fillColor } = getStockColorAndRadius(stockPrices[code] || {}, colorMetric);
          const nameLabel = stockName.length > 10 ? stockName.slice(0, 10) + '..' : stockName;
          const cg = (stockPrices[code]?.chg || 0);
          const cgStr = (cg >= 0 ? '+' : '') + cg.toFixed(1) + '%';
          const cgColor = cg >= 0 ? '#ff6b6b' : '#51cf66';

          // 每行公司整组：圆点+名称+涨跌幅，整行可点击
          const row = g.append('g').attr('class', 'stock-row').style('cursor', 'pointer');
          row.append('circle').attr('cx', cx - COL_W / 2 + 14).attr('cy', sy + 7).attr('r', 4).attr('fill', fillColor).attr('fill-opacity', 1.0).attr('stroke', fillColor).attr('stroke-width', 2.5);
          row.append('text').attr('x', cx - COL_W / 2 + 24).attr('y', sy + 10).attr('fill', '#c9d1d9').attr('font-size', 9).text(nameLabel);
          row.append('text').attr('x', cx + COL_W / 2 - 55).attr('y', sy + 10).attr('fill', cgColor).attr('font-size', 8).text(cgStr);

          // 点击整行
          row.on('click', function(event) { event.stopPropagation(); if (onNodeClick) onNodeClick({ id: code, code, name: stockName, type: 'stock', chg: stockPrices[code]?.chg || 0, price: stockPrices[code]?.price || 0 }); });
          row.on('mouseenter', function(event) { if (onTooltip) { const rect = svg.node().getBoundingClientRect(); onTooltip({ node: { id: code, code, name: stockName, type: 'stock', chg: stockPrices[code]?.chg || 0 }, x: event.clientX - rect.left, y: event.clientY - rect.top }); } });
          row.on('mouseleave', () => { if (onTooltip) onTooltip(null); });

          // 选中高亮框（蓝色边框框住整行）
          if (selectedNode && selectedNode.id === code) {
            row.insert('rect', ':first-child').attr('class', 'sel-box')
              .attr('x', cx - COL_W / 2 + 6).attr('y', sy - 2)
              .attr('width', COL_W - 12).attr('height', 18)
              .attr('fill', 'none').attr('stroke', '#58a6ff').attr('stroke-width', 1.5).attr('rx', 3);
          }

          sy += STOCK_H;
        }
        yPos = sy + BETWEEN_LINK_H;
      }
    }
    svg.on('click', () => { if (onNodeClick) onNodeClick(null); });
  } catch (e) { console.error('HorizontalTable error:', e.message); }
}

// ============================================================
// 模式3：星形放射
// ============================================================
function buildStarLayout(svg, industry, stockPrices, colorMetric, onTooltip, onNodeClick, selectedNode, width, height) {
  try {
    const sections = industry.sections || [];
    if (sections.length === 0) return;

    const NODE_RADIUS = 36;
    const LINK_RADIUS = 16;
    const COL_W = 300;
    const COL_GAP = 30;
    const ORBIT_R = 120;
    const STOCK_SPREAD = 55;

    const layoutW = sections.length * COL_W + (sections.length - 1) * COL_GAP;
    const viewH = Math.max(height || 800, 600);
    const viewW = Math.max(width || 1200, layoutW + 40);
    svg.attr('viewBox', `0 0 ${viewW} ${viewH}`).style('width', '100%').style('height', '100%');

    const offsetX = Math.max(0, (viewW - layoutW) / 2);
    const centerY = viewH / 2;
    const colCenters = {};
    for (let i = 0; i < sections.length; i++) {
      colCenters[i] = { x: offsetX + i * (COL_W + COL_GAP) + COL_W / 2, y: centerY };
    }

    const g = svg.append('g');
    svg.call(d3.zoom().scaleExtent([0.3, 5]).filter(event => !event.target.closest('.s-node')).on('zoom', (event) => g.attr('transform', event.transform)));

    const defs = svg.append('defs');
    defs.append('marker').attr('id', 'sarrow2').attr('viewBox', '0 -5 10 10').attr('refX', NODE_RADIUS + 6).attr('refY', 0).attr('markerWidth', 8).attr('markerHeight', 8).attr('orient', 'auto').append('path').attr('d', 'M0,-5L10,0L0,5').attr('fill', '#58a6ff');

    for (let i = 0; i < sections.length - 1; i++) {
      const a = colCenters[i], b = colCenters[i + 1];
      g.append('line').attr('x1', a.x + NODE_RADIUS).attr('y1', a.y).attr('x2', b.x - NODE_RADIUS).attr('y2', b.y).attr('stroke', '#58a6ff').attr('stroke-width', 3).attr('stroke-opacity', 0.7).attr('marker-end', 'url(#sarrow2)');
    }

    for (let i = 0; i < sections.length; i++) {
      const sec = sections[i];
      const cx = colCenters[i].x;
      const cy = colCenters[i].y;
      const colColor = SECTION_COLORS[i % SECTION_COLORS.length];
      const links = sec.links || [];
      const nLinks = links.length;

      g.append('circle').attr('cx', cx).attr('cy', cy).attr('r', ORBIT_R + STOCK_SPREAD + 30).attr('fill', i % 2 === 0 ? '#161b22' : '#0d1117').attr('opacity', 0.15);
      g.append('circle').attr('cx', cx).attr('cy', cy).attr('r', NODE_RADIUS).attr('fill', colColor).attr('fill-opacity', 0.25).attr('stroke', colColor).attr('stroke-width', 3);
      g.append('circle').attr('cx', cx).attr('cy', cy).attr('r', NODE_RADIUS + 4).attr('fill', 'none').attr('stroke', colColor).attr('stroke-width', 1).attr('stroke-opacity', 0.4);
      g.append('text').attr('x', cx).attr('y', cy + 5).attr('text-anchor', 'middle').attr('fill', '#e6edf3').attr('font-size', 16).attr('font-weight', 700).text(sec.name.length > 8 ? sec.name.slice(0, 8) + '..' : sec.name);

      if (nLinks === 0) continue;

      const angleStep = (2 * Math.PI) / nLinks;
      const startAngle = -Math.PI / 2;

      for (let j = 0; j < nLinks; j++) {
        const link = links[j];
        const angle = startAngle + j * angleStep;
        const lx = cx + ORBIT_R * Math.cos(angle);
        const ly = cy + ORBIT_R * Math.sin(angle);
        const subColor = LINK_COLORS[j % LINK_COLORS.length];
        const stks = link.stocks || [];

        g.append('line').attr('x1', cx).attr('y1', cy).attr('x2', lx).attr('y2', ly).attr('stroke', subColor).attr('stroke-width', 1).attr('stroke-opacity', 0.4).attr('stroke-dasharray', '3,3');
        g.append('circle').attr('cx', lx).attr('cy', ly).attr('r', LINK_RADIUS).attr('fill', subColor).attr('fill-opacity', 0.25).attr('stroke', subColor).attr('stroke-width', 2);
        g.append('text').attr('x', lx).attr('y', ly + 4).attr('text-anchor', 'middle').attr('fill', '#e6edf3').attr('font-size', 10).attr('font-weight', 600).text(link.name.length > 6 ? link.name.slice(0, 6) + '..' : link.name);

        const stkAngle = angle;
        const stkBaseR = LINK_RADIUS + 8;
        for (let k = 0; k < stks.length; k++) {
          const raw = stks[k];
          const code = typeof raw === 'string' ? raw : raw.code;
          const stockName = typeof raw === 'object' ? raw.name : (stockPrices[code]?.name || code);
          const price = stockPrices[code] || {};
          const { fillColor } = getStockColorAndRadius(price, colorMetric);
          const sOff = stkBaseR + k * 60;
          const sx = lx + sOff * Math.cos(stkAngle);
          const sy = ly + sOff * Math.sin(stkAngle);

          // 公司整组：圆点+名称(tspan) -> 整组可点击
          const sg = g.append('g').style('cursor', 'pointer');
          sg.append('circle').attr('cx', sx).attr('cy', sy).attr('r', 4).attr('fill', fillColor).attr('fill-opacity', 1.0).attr('stroke', fillColor).attr('stroke-width', 2.5);

          const isRight = Math.cos(stkAngle) > 0;
          const tx = sx + (isRight ? 8 : -8);
          const nameLabel = stockName.length > 6 ? stockName.slice(0, 6) + '..' : stockName;
          const cgStr = ((price.chg || 0) >= 0 ? '+' : '') + (price.chg || 0).toFixed(1) + '%';
          const cgColor = (price.chg || 0) >= 0 ? '#ff6b6b' : '#51cf66';
          const textEl = sg.append('text').attr('x', tx).attr('y', sy + 3).attr('text-anchor', isRight ? 'start' : 'end');
          textEl.append('tspan').attr('fill', '#c9d1d9').text(nameLabel + ' ');
          textEl.append('tspan').attr('fill', cgColor).text(cgStr);

          // 点击整组
          sg.on('click', function(event) { event.stopPropagation(); if (onNodeClick) onNodeClick({ id: code, code, name: stockName, type: 'stock', chg: price.chg || 0, price: price.price || 0 }); });
          sg.on('mouseenter', function(event) { if (onTooltip) { const rect = svg.node().getBoundingClientRect(); onTooltip({ node: { id: code, code, name: stockName, type: 'stock', chg: price.chg || 0 }, x: event.clientX - rect.left, y: event.clientY - rect.top }); } });
          sg.on('mouseleave', () => { if (onTooltip) onTooltip(null); });

          // 选中蓝色边框（框住圆点+名称+涨跌幅）
          if (selectedNode && selectedNode.id === code) {
            const boxW = isRight ? 100 : 90;
            sg.insert('rect', ':first-child').attr('class', 'sel-box')
              .attr('x', isRight ? sx - 4 : sx - boxW + 4).attr('y', sy - 6)
              .attr('width', boxW).attr('height', 16)
              .attr('fill', 'none').attr('stroke', '#58a6ff').attr('stroke-width', 1.5).attr('rx', 3);
          }
        }
      }
    }
    svg.on('click', () => { if (onNodeClick) onNodeClick(null); });
  } catch (e) { console.error('StarLayout error:', e.message); }
}

// ============================================================
// 主组件
// ============================================================
export default function GraphCanvas({
  layoutMode, industry, stockPrices,
  colorMetric, onTooltip, onNodeClick, selectedNode
}) {
  const svgRef = useRef(null);
  const containerRef = useRef(null);
  const zoomStateRef = useRef(null); // 保存zoom transform，选中切换时恢复

  const buildGraph = useCallback(() => {
    if (!industry || !svgRef.current) return;
    const svg = d3.select(svgRef.current);
    const container = containerRef.current;
    const width = container.clientWidth || 1200;
    const height = container.clientHeight || 800;
    svg.selectAll('*').remove();

    if (layoutMode === 'force') {
      buildForceGraph(svg, industry, stockPrices, colorMetric, onTooltip, onNodeClick, selectedNode, width, height);
    } else if (layoutMode === 'horizontal') {
      buildHorizontalTable(svg, industry, stockPrices, colorMetric, onTooltip, onNodeClick, selectedNode, width, height, zoomStateRef);
    }
  }, [layoutMode, industry, stockPrices, colorMetric, onTooltip, onNodeClick, selectedNode]);

  useEffect(() => { buildGraph(); }, [buildGraph]);
  useEffect(() => {
    const h = () => buildGraph();
    window.addEventListener('resize', h);
    return () => window.removeEventListener('resize', h);
  }, [buildGraph]);

  return (
    <div className="graph-wrapper" ref={containerRef} data-mode={layoutMode}>
      <svg ref={svgRef}></svg>
    </div>
  );
}
