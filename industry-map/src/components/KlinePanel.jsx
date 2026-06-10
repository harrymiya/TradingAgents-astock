import React, { useState, useEffect, useRef, useCallback } from 'react';
import './KlinePanel.css';

const API_URL = '/api/kline';

/**
 * KlinePanel — 底部K线图组件
 * 根据选中公司代码拉取日线数据, 用纯SVG绘制
 * 支持60日/120日/250日切换, 鼠标悬停显示十字光标+Tooltip
 */
export default function KlinePanel({ code, name, onClose }) {
  const [klines, setKlines] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(120);
  const [hoverIdx, setHoverIdx] = useState(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const svgRef = useRef(null);
  const [chartRect, setChartRect] = useState(null);

  // 拉取K线数据
  useEffect(() => {
    if (!code) return;
    setLoading(true);
    setError(null);
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

  // 鼠标移动事件处理
  const handleMouseMove = useCallback((e) => {
    if (!svgRef.current || klines.length === 0) return;
    const rect = svgRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const svgWidth = rect.width;
    const padL = 50, padR = 20;
    const chartW = svgWidth - padL - padR;
    if (chartW <= 0) return;
    const idx = Math.round((x - padL) / chartW * (klines.length - 1));
    const clampedIdx = Math.max(0, Math.min(klines.length - 1, idx));
    setHoverIdx(clampedIdx);
    setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
    setChartRect(rect);
  }, [klines]);

  const handleMouseLeave = useCallback(() => {
    setHoverIdx(null);
  }, []);

  // 渲染SVG
  const renderSVG = () => {
    if (klines.length === 0) return null;

    const W = 800;  // viewBox width
    const H = 220;
    const padL = 50, padR = 20;
    const kPadL = 50, kPadR = 20;
    const kTop = 5;
    const kBot = 70;  // K线区域底部（留空间给成交量）
    const vTop = 75;  // 成交量区域顶部
    const vBot = 100; // 成交量区域底部
    const chartW = W - padL - padR;
    const kH = kBot - kTop;
    const vH = vBot - vTop;
    const n = klines.length;

    if (n === 0) return null;

    // 计算K线极值
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

    // 计算MA
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

    // 生成K线
    const candles = [];
    const volBars = [];
    for (let i = 0; i < n; i++) {
      const k = klines[i];
      const x = padL + i * gap;
      const openY = yPrice(k.open);
      const closeY = yPrice(k.close);
      const highY = yPrice(k.high);
      const lowY = yPrice(k.low);
      const isUp = k.close >= k.open;
      const color = isUp ? '#f85149' : '#3fb950';

      // 影线
      candles.push(
        <line key={`wick-${i}`} x1={x} y1={highY} x2={x} y2={lowY}
          stroke={color} strokeWidth={1} />
      );
      // 实体
      const bodyTop = Math.min(openY, closeY);
      const bodyH = Math.max(Math.abs(closeY - openY), 1);
      candles.push(
        <rect key={`body-${i}`} x={x - candleW / 2} y={bodyTop}
          width={candleW} height={bodyH} fill={color} />
      );

      // 成交量柱
      volBars.push(
        <rect key={`vol-${i}`} x={x - candleW / 2} y={yVol(k.volume)}
          width={candleW} height={vBot - yVol(k.volume)}
          fill={color} opacity={0.5} />
      );
    }

    // MA线路径
    const makePath = (arr, color, className) => {
      const pts = [];
      for (let i = 0; i < n; i++) {
        if (arr[i] === null) continue;
        const x = padL + i * gap;
        pts.push(`${i === 0 ? 'M' : 'L'}${x},${yPrice(arr[i])}`);
      }
      if (pts.length === 0) return null;
      return <path key={className} d={pts.join(' ')} className={className} />;
    };

    // Y轴刻度
    const yTicks = [];
    const yTickCount = 5;
    for (let i = 0; i <= yTickCount; i++) {
      const val = minLow + priceRange * (1 - i / yTickCount);
      const y = kTop + kH * (i / yTickCount);
      yTicks.push(
        <g key={`ytick-${i}`}>
          <line x1={padL - 5} y1={y} x2={W - padR} y2={y}
            stroke="#21262d" strokeWidth={0.5} />
          <text x={padL - 8} y={y + 3} textAnchor="end"
            fill="#8b949e" fontSize={9}>{val.toFixed(2)}</text>
        </g>
      );
    }

    // X轴刻度（显示部分日期）
    const xTicks = [];
    const xTickCount = Math.min(8, n);
    const step = Math.max(1, Math.floor(n / xTickCount));
    for (let i = 0; i < n; i += step) {
      const x = padL + i * gap;
      const d = klines[i].date;
      xTicks.push(
        <g key={`xtick-${i}`}>
          <line x1={x} y1={vBot + 2} x2={x} y2={vBot + 6}
            stroke="#8b949e" strokeWidth={0.5} />
          <text x={x} y={vBot + 16} textAnchor="middle"
            fill="#8b949e" fontSize={9}>
            {d ? d.slice(5) : ''}
          </text>
        </g>
      );
    }

    // 十字光标
    let crosshair = null;
    if (hoverIdx !== null && chartRect) {
      const hx = padL + hoverIdx * gap;
      const k2 = klines[hoverIdx];
      const isUp2 = k2.close >= k2.open;
      const hColor = isUp2 ? '#f85149' : '#3fb950';

      crosshair = (
        <g className="kline-crosshair">
          <line x1={hx} y1={kTop} x2={hx} y2={vBot}
            stroke="#8b949e" strokeWidth={1} strokeDasharray="3,3" />
          <circle cx={hx} cy={yPrice(k2.close)} r={3} fill={hColor} />
        </g>
      );
    }

    return (
      <svg viewBox={`0 0 ${W} ${H}`} ref={svgRef}
        onMouseMove={handleMouseMove} onMouseLeave={handleMouseLeave}
        style={{ cursor: hoverIdx !== null ? 'crosshair' : 'default' }}>
        {/* 价格刻度 */}
        {yTicks}

        {/* K线 */}
        {candles}

        {/* 成交量 */}
        {volBars}

        {/* MA线 */}
        {makePath(ma5, '#d29922', 'kline-ma5')}
        {makePath(ma10, '#58a6ff', 'kline-ma10')}
        {makePath(ma20, '#bc8cff', 'kline-ma20')}

        {/* 日期刻度 */}
        {xTicks}

        {/* 十字光标 */}
        {crosshair}
      </svg>
    );
  };

  // hover tooltip
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

  // 显示MA图例
  const maLegend = () => {
    if (klines.length < 20) return null;
    const last = klines[klines.length - 1];
    return (
      <div style={{ display: 'flex', gap: 12, fontSize: 11, color: '#8b949e', alignItems: 'center' }}>
        <span><span style={{ color: '#d29922' }}>●</span> MA5</span>
        <span><span style={{ color: '#58a6ff' }}>●</span> MA10</span>
        <span><span style={{ color: '#bc8cff' }}>●</span> MA20</span>
        <span style={{ color: '#c9d1d9' }}>
          {last.date} C:{' '}
          <span style={{ color: last.close >= last.open ? '#f85149' : '#3fb950' }}>
            {last.close.toFixed(2)}
          </span>
        </span>
      </div>
    );
  };

  if (!code) return null;

  return (
    <div className="kline-panel">
      <div className="kline-header">
        <div className="kline-title">
          <span className="kline-name">{name || code}</span>
          <span className="kline-code">{code}</span>
          <span style={{ margin: '0 8px', color: '#30363d' }}>|</span>
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
