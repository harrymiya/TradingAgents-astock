import React, { useRef, useEffect, useCallback } from 'react';
import * as d3 from 'd3';
import './GraphCanvas.css';

// 颜色映射
function getColor(value, metric) {
  if (value === null || value === undefined) return '#8b949e';
  switch (metric) {
    case 'chg':
    case 'yearChg':
    case 'monthChg':
      if (value > 5) return '#00c853';
      if (value > 3) return '#2ea043';
      if (value > 1) return '#58a6ff';
      if (value > 0) return '#8b949e';
      if (value > -1) return '#8b949e';
      if (value > -3) return '#f85149';
      if (value > -5) return '#d73a49';
      return '#7d1a2c';
    case 'volume':
      const v = value / 10000;
      if (v > 100) return '#00c853';
      if (v > 30) return '#2ea043';
      if (v > 10) return '#58a6ff';
      if (v > 3) return '#8b949e';
      return '#6e7681';
    case 'amplitude':
      if (value > 10) return '#00c853';
      if (value > 5) return '#2ea043';
      if (value > 3) return '#58a6ff';
      if (value > 1) return '#8b949e';
      return '#6e7681';
    default:
      return '#8b949e';
  }
}

// 环节节点颜色（固定方案）
const LINK_COLORS = ['#7c3aed', '#2563eb', '#0891b2', '#059669', '#d97706', '#dc2626', '#db2777', '#4f46e5'];

export default function GraphCanvas({ industry, industryData, stockPrices, colorMetric, labelMode, onTooltip, onNodeClick, selectedNode }) {
  const svgRef = useRef(null);
  const containerRef = useRef(null);

  const buildGraph = useCallback(() => {
    const data = industryData[industry];
    if (!data || !svgRef.current) return;

    const svg = d3.select(svgRef.current);
    const container = containerRef.current;
    const width = container.clientWidth || 1200;
    const height = container.clientHeight || 800;

    svg.selectAll('*').remove();

    const links_data = data['环节'];
    const nodes = [];
    const links = [];
    const nodeMap = {};

    // 环节->颜色映射
    const linkNames = Object.keys(links_data);
    const linkColorMap = {};
    linkNames.forEach((name, i) => {
      linkColorMap[name] = LINK_COLORS[i % LINK_COLORS.length];
    });

    // Build nodes: 环节节点 + 股票节点
    let nodeIdx = 0;

    for (const [linkName, linkData] of Object.entries(links_data)) {
      // 环节节点
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
        // 携带该环节的所有股票代码和名称
        stocks: linkData['股票'].map(c => ({
          code: c,
          name: (stockPrices[c] && stockPrices[c].name) || c,
        })),
      };
      nodes.push(linkNode);
      nodeMap[linkNode.id] = nodeIdx;
      nodeIdx++;

      // 股票节点
      for (const code of linkData['股票']) {
        const price = stockPrices[code] || {};
        const stockNode = {
          id: code,
          name: price.name || code,
          code: code,
          type: 'stock',
          price: price.price || 0,
          chg: price.chg || 0,
          yearChg: price.yearChg || 0,
          monthChg: price.monthChg || price.chg || 0,
          volume: price.volume || 0,
          amplitude: price.amplitude || 0,
          linkName: linkName,
          linkColor: linkColorMap[linkName],
          r: 8,
        };
        nodes.push(stockNode);
        nodeMap[code] = nodeIdx;
        nodeIdx++;

        // 股票 -> 所属环节
        links.push({ source: code, target: 'link_' + linkName, type: 'belongs' });
      }

      // 环节间的上下游关系
      for (const up of linkData['上游']) {
        if (links_data[up]) {
          links.push({ source: 'link_' + up, target: 'link_' + linkName, type: 'flow' });
        }
      }
    }

    // ---- D3 力导向图 ----
    const g = svg.append('g');

    // zoom
    const zoom = d3.zoom()
      .scaleExtent([0.3, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });
    svg.call(zoom);

    // 力模拟
    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(d => {
        return d.type === 'belongs' ? 60 : 120;
      }))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(d => d.r + 8));

    // 画箭头标记
    const defs = svg.append('defs');
    defs.append('marker')
      .attr('id', 'arrow')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 20)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#30363d');

    // Links
    const linkG = g.append('g').selectAll('line')
      .data(links)
      .join('line')
      .attr('class', 'link')
      .attr('stroke', d => d.type === 'flow' ? '#30363d' : '#21262d')
      .attr('stroke-width', d => d.type === 'flow' ? 1.5 : 1)
      .attr('stroke-dasharray', d => d.type === 'belongs' ? '3,3' : 'none')
      .attr('marker-end', d => d.type === 'flow' ? 'url(#arrow)' : null);

    // ---- Nodes ----
    const nodeG = g.append('g').selectAll('.node')
      .data(nodes)
      .join('g')
      .attr('class', 'node')
      .style('cursor', 'pointer');

    // 环节节点 - 大圆
    nodeG.filter(d => d.type === 'link')
      .append('circle')
      .attr('r', d => d.r)
      .attr('fill', d => d.color)
      .attr('fill-opacity', 0.25)
      .attr('stroke', d => d.color)
      .attr('stroke-width', 2.5)
      .style('transition', 'r 0.15s');

    // 环节节点 - 外圈光晕(壁垒等级)
    nodeG.filter(d => d.type === 'link')
      .append('circle')
      .attr('r', d => d.r + 4)
      .attr('fill', 'none')
      .attr('stroke', d => d.color)
      .attr('stroke-width', d => 1 + d.barrier * 0.5)
      .attr('stroke-opacity', 0.3);

    // 股票节点
    nodeG.filter(d => d.type === 'stock')
      .append('circle')
      .attr('r', d => d.r)
      .attr('fill', d => getColor(d.chg, 'chg'))
      .attr('stroke', '#fff')
      .attr('stroke-width', 1);

    // 环节标签
    if (labelMode === 'link' || labelMode === 'both') {
      nodeG.filter(d => d.type === 'link')
        .append('text')
        .attr('dy', 4)
        .attr('text-anchor', 'middle')
        .attr('fill', '#e6edf3')
        .attr('font-size', 12)
        .attr('font-weight', 600)
        .attr('pointer-events', 'none')
        .text(d => d.name.length > 5 ? d.name.slice(0, 5) + '..' : d.name);
    }

    // 股票标签
    if (labelMode === 'stock' || labelMode === 'both') {
      nodeG.filter(d => d.type === 'stock')
        .append('text')
        .attr('dx', d => d.r + 6)
        .attr('dy', 4)
        .attr('fill', '#c9d1d9')
        .attr('font-size', 10)
        .attr('pointer-events', 'none')
        .text(d => d.name);
    }

    // 环节间关系标签（简化版：只在上游关系较远的链路上标注）
    const linkLabels = g.append('g').selectAll('.link-label')
      .data(links.filter(d => d.type === 'flow'))
      .join('text')
      .attr('class', 'link-label')
      .attr('fill', '#6e7681')
      .attr('font-size', 9)
      .attr('text-anchor', 'middle')
      .attr('pointer-events', 'none');

    // ---- 交互 ----
    // Tooltip - 鼠标悬停
    nodeG.on('mouseenter', function(event, d) {
      const rect = container.getBoundingClientRect();
      onTooltip({
        node: d,
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      });
    });

    nodeG.on('mouseleave', () => {
      // 延迟关闭让用户有时间移动到tooltip
    });

    // 点击节点 → 右侧详情栏
    nodeG.on('click', function(event, d) {
      event.stopPropagation();
      if (onNodeClick) {
        onNodeClick(d);
      }
    });

    // 点击空白取消选中
    svg.on('click', () => {
      if (onNodeClick) onNodeClick(null);
    });

    // 选中节点高亮
    if (selectedNode) {
      nodeG.attr('opacity', d => {
        if (d.id === selectedNode.id) return 1;
        // 同类型节点半透明，突出选中
        if (selectedNode.type === 'link' && d.linkName === selectedNode.linkName) return 1;
        if (selectedNode.type === 'stock' && d.type === 'stock') return 0.4;
        if (selectedNode.type === 'link' && d.type === 'stock' && d.linkName === selectedNode.name) return 1;
        return 0.3;
      });
    } else {
      nodeG.attr('opacity', 1);
    }

    // 点击可固定节点（拖拽后保持位置）
    nodeG.call(d3.drag()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on('drag', (event, d) => {
        d.fx = event.x;
        d.fy = event.y;
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        // 不固定，让力继续
        d.fx = null;
        d.fy = null;
      })
    );

    // ---- Simulation Tick ----
    simulation.on('tick', () => {
      linkG
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);

      nodeG.attr('transform', d => `translate(${d.x},${d.y})`);

      linkLabels
        .attr('x', d => (d.source.x + d.target.x) / 2)
        .attr('y', d => (d.source.y + d.target.y) / 2)
        .text(d => {
          // 只显示特别重要的环节关系
          const src = d.source;
          const tgt = d.target;
          if (src.type === 'link' && tgt.type === 'link') {
            return '↓';
          }
          return '';
        });
    });

    // 初始缩放适应
    const initialZoom = () => {
      const bounds = g.node()?.getBBox();
      if (bounds) {
        const scale = Math.min(
          width / (bounds.width + 100),
          height / (bounds.height + 100),
          1.5
        );
        const tx = (width - bounds.width * scale) / 2 - bounds.x * scale;
        const ty = (height - bounds.height * scale) / 2 - bounds.y * scale;
        svg.transition().duration(500).call(
          zoom.transform,
          d3.zoomIdentity.translate(tx, ty).scale(scale)
        );
      }
    };

    // 等simulation稳定后缩放
    setTimeout(initialZoom, 1000);

    return () => {
      simulation.stop();
    };

  }, [industry, industryData, stockPrices, colorMetric, labelMode, onTooltip]);

  useEffect(() => {
    const cleanup = buildGraph();
    return cleanup;
  }, [buildGraph]);

  // 窗口大小变化时重绘
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
