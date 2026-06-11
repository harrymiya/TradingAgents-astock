import React, { useState, useEffect, useRef, useCallback } from 'react';
import './KlinePanel.css';

const API_URL = '/api/kline';

/**
 * KlinePanel — 悬浮在拓扑图下方的K线面板
 * absolute定位，可拖拽顶部边缘调整高度，可关闭
 * SVG铺满，支持60/120/250日切换、十字光标+Tooltip
 */
export default function KlinePanel({ code, name, onClose }) {
  const [klines, setKlines] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(120);
  const [hoverIdx, setHoverIdx] = useState(null);
  const svgRef = useRef(null);
  const panelRef = useRef(null);

  // 拖拽状态
  const [panelHeight, setPanelHeight] = useState(280);
  const dragging = useRef(false);
  const startY = useRef(0);
  const startH = useRef(0);

  // 拉取K线数据
  useEffect(() => {
    if (!code) return;
    setLoading(true);
    setError(null);
    setHoverIdx(null);
    fetch(`${API_URL}?code=${code}&days=${days}`)
      .then(r => r.json())
      .then(data => {
        if (data.error) {
          setError(data.error);
        } else if (data.klines && data.klines.length > 0) {
          setKlines(data.klines);
        } else {
          setError('暂无K线数据');
        }
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [code, days]);

  // 拖拽事件 — 从顶部边缘拖拽等比放大K线区域
  const handleDragStart = useCallback((e) => {
    dragging.current = true;
    startY.current = e.clientY || e.touches?.[0]?.clientY || 0;
    startH.current = panelRef.current?.offsetHeight || 280;
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
  }, []);

  useEffect(() => {
    const handleDragMove = (e) => {
      if (!dragging.current) return;
      const dy = (e.clientY || e.touches?.[0]?.clientY || 0) - startY.current;
      // 向上拖（dy负值）→ 增大面板；向下拖（dy正值）→ 缩小面板
      const newH = Math.max(120, Math.min(window.innerHeight * 0.8, startH.current - dy));
      setPanelHeight(newH);
    };
    const handleDragEnd = () => {
      if (dragging.current) {
        dragging.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };
    window.addEventListener('mousemove', handleDragMove);
    window.addEventListener('mouseup', handleDragEnd);
    window.addEventListener('touchmove', handleDragMove, { passive: true });
    window.addEventListener('touchend', handleDragEnd);
    return () => {
      window.removeEventListener('mousemove', handleDragMove);
      window.removeEventListener('mouseup', handleDragEnd);
      window.removeEventListener('touchmove', handleDragMove);
      window.removeEventListener('touchend', handleDragEnd);
    };
  }, []);

  // 鼠标移动 — 基于 viewBox 坐标计算
  const handleMouseMove = useCallback((e) => {
    if (!svgRef.current || klines.length === 0) return;
    const svg = svgRef.current;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const ctm = svg.getScreenCTM();
    if (!ctm) return;
    const svgPt = pt.matrixTransform(ctm.inverse());

    const W = 800;
    const padL = 50, padR = 20;
    const chartW = W - padL - padR;
    const n = klines.length;
    const gap = chartW / n;

    const idx = Math.round((svgPt.x - padL) / gap);
    if (idx < 0 || idx >= n) {
      setHoverIdx(null);
      return;
    }
    setHoverIdx(idx);
  }, [klines]);

  const handleMouseLeave = useCallback(() => {
    setHoverIdx(null);
  }, []);

  // === SVG绘制 ===
  const renderSVG = () => {
    if (klines.length === 0) return null;

    const W = 800;
    const H = 115;
    const padL = 50, padR = 20;
    const kTop = 5;
    const kBot = 75;
    const vTop = 78;
    const vBot = 105;
    const chartW = W - padL - padR;
    const kH = kBot - kTop;
    const vH = vBot - vTop;
    const n = klines.length;

    let minLow = Infinity, maxHigh = -Infinity, maxVol = 0;
    for (const k of klines) {
      if (k.low < minLow) minLow = k.low;
      if (k.high > maxHigh) maxHigh = k.high;
      if (k.volume > maxVol) maxVol = k.volume;
    }
    const priceRange = maxHigh - minLow || 1;
    const volRange = maxVol || 1;
    const candleW = Math.max(3, Math.min(8, chartW / n * 0.7));
    const gap = chartW / n;

    // MA
    const calcMA = (period) => {
      const result = [];
      for (let i = 0; i < n; i++) {
        if (i < period - 1) { result.push(null); continue; }
        let sum = 0;
        for (let j = i - period + 1; j <= i; j++) sum += klines[j].close;
        result.push(sum / period);
      }
      return result;
    };
    const ma5 = calcMA(5);
    const ma10 = calcMA(10);
    const ma20 = calcMA(20);

    const yPrice = (val) => kTop + kH * (1 - (val - minLow) / priceRange);
    const yVol = (val) => vBot - vH * (val / volRange);

    const elements = [];
    for (let i = 0; i < n; i++) {
      const k = klines[i];
      const x = padL + i * gap;
      const oY = yPrice(k.open);
      const cY = yPrice(k.close);
      const hY = yPrice(k.high);
      const lY = yPrice(k.low);
      const isUp = k.close >= k.open;
      const color = isUp ? '#f85149' : '#3fb950';
      elements.push(<line key={`wick-${i}`} x1={x} y1={hY} x2={x} y2={lY} stroke={color} strokeWidth={1} />);
      const bTop = Math.min(oY, cY);
      const bH = Math.max(Math.abs(cY - oY), 1);
      elements.push(<rect key={`body-${i}`} x={x - candleW / 2} y={bTop} width={candleW} height={bH} fill={color} />);
      elements.push(<rect key={`vol-${i}`} x={x - candleW / 2} y={yVol(k.volume)} width={candleW} height={vBot - yVol(k.volume)} fill={color} opacity={0.4} />);
    }

    const makePath = (arr, cls) => {
      const pts = [];
      for (let i = 0; i < n; i++) {
        if (arr[i] === null) continue;
        pts.push(`${i === 0 ? 'M' : 'L'}${padL + i * gap},${yPrice(arr[i])}`);
      }
      return pts.length ? <path d={pts.join(' ')} className={cls} /> : null;
    };
    if (makePath(ma5, 'kline-ma5')) elements.push(makePath(ma5, 'kline-ma5'));
    if (makePath(ma10, 'kline-ma10')) elements.push(makePath(ma10, 'kline-ma10'));
    if (makePath(ma20, 'kline-ma20')) elements.push(makePath(ma20, 'kline-ma20'));

    for (let i = 0; i <= 5; i++) {
      const val = minLow + priceRange * (1 - i / 5);
      const y = kTop + kH * (i / 5);
      elements.push(<line key={`ygl-${i}`} x1={padL - 5} y1={y} x2={W - padR} y2={y} stroke="#21262d" strokeWidth={0.5} />);
      elements.push(<text key={`ygt-${i}`} x={padL - 8} y={y + 3} textAnchor="end" fill="#8b949e" fontSize={9}>{val.toFixed(2)}</text>);
    }

    const xCount = Math.min(8, n);
    const xStep = Math.max(1, Math.floor(n / xCount));
    for (let i = 0; i < n; i += xStep) {
      const x = padL + i * gap;
      const d = klines[i].date;
      elements.push(<line key={`xgl-${i}`} x1={x} y1={vBot + 2} x2={x} y2={vBot + 6} stroke="#8b949e" strokeWidth={0.5} />);
      elements.push(<text key={`xgt-${i}`} x={x} y={vBot + 16} textAnchor="middle" fill="#8b949e" fontSize={9}>{d ? d.slice(5) : ''}</text>);
    }

    if (hoverIdx !== null && klines[hoverIdx]) {
      const k = klines[hoverIdx];
      const hx = padL + hoverIdx * gap;
      const isUp = k.close >= k.open;
      const hColor = isUp ? '#f85149' : '#3fb950';
      elements.push(
        <g key="crosshair" className="kline-crosshair">
          <line x1={hx} y1={kTop} x2={hx} y2={vBot} stroke="#8b949e" strokeWidth={1} strokeDasharray="3,3" />
          <circle cx={hx} cy={yPrice(k.close)} r={3} fill={hColor} />
        </g>
      );
    }

    return (
      <svg viewBox={`0 0 ${W} ${H}`} ref={svgRef}
        onMouseMove={handleMouseMove} onMouseLeave={handleMouseLeave}
        style={{ cursor: hoverIdx !== null ? 'crosshair' : 'default' }}>
        {elements}
      </svg>
    );
  };

  const renderTooltip = () => {
    if (hoverIdx === null || !klines[hoverIdx]) return null;
    const k = klines[hoverIdx];
    const isUp = k.close >= k.open;
    return (
      <div className="kline-tooltip">
        <span className="tt-date">{k.date}</span>
        <span>O: <span className="tt-open">{k.open.toFixed(2)}</span></span>
        <span>H: <span className="tt-high">{k.high.toFixed(2)}</span></span>
        <span>L: <span className="tt-low">{k.low.toFixed(2)}</span></span>
        <span>C: <span className={isUp ? 'tt-up' : 'tt-down'}>{k.close.toFixed(2)}</span></span>
        <span className="tt-vol">V: {(k.volume / 10000).toFixed(0)}万</span>
      </div>
    );
  };

  const maLegend = () => {
    if (klines.length < 20) return null;
    const last = klines[klines.length - 1];
    return (
      <div className="kline-ma-legend">
        <span><span style={{ color: '#d29922' }}>━</span> MA5</span>
        <span><span style={{ color: '#58a6ff' }}>━</span> MA10</span>
        <span><span style={{ color: '#bc8cff' }}>━</span> MA20</span>
        <span style={{ color: '#c9d1d9' }}>
          {last.date} C:{' '}
          <span style={{ color: last.close >= last.open ? '#f85149' : '#3fb950' }}>
            {last.close.toFixed(2)}
          </span>
        </span>
      </div>
    );
  };

  const dragHandle = (
    <div className="kline-drag-handle" onMouseDown={handleDragStart} onTouchStart={handleDragStart}>
      <div className="kline-drag-dots">
        <span></span><span></span><span></span><span></span>
      </div>
    </div>
  );

  if (!code) return null;

  return (
    <div className="kline-panel" ref={panelRef} style={{ height: panelHeight }}>
      {dragHandle}
      <div className="kline-header">
        <div className="kline-title">
          <span className="kline-name">{name || code}</span>
          <span className="kline-code">{code}</span>
          <span className="kline-sep">|</span>
          日K线
        </div>
        <div className="kline-timeframe">
          {maLegend()}
          <button className={`kline-tf-btn ${days === 60 ? 'active' : ''}`}
            onClick={() => setDays(60)}>60日</button>
          <button className={`kline-tf-btn ${days === 120 ? 'active' : ''}`}
            onClick={() => setDays(120)}>120日</button>
          <button className={`kline-tf-btn ${days === 250 ? 'active' : ''}`}
            onClick={() => setDays(250)}>250日</button>
        </div>
        <button className="kline-close-btn" onClick={onClose} title="关闭K线">✕</button>
      </div>

      {loading && <div className="kline-loading">⏳ 加载K线数据...</div>}
      {error && <div className="kline-error">❌ {error}</div>}

      {!loading && !error && klines.length > 0 && (
        <div className="kline-svg-wrap">
          {renderSVG()}
          {renderTooltip()}
        </div>
      )}
    </div>
  );
}
