import React from 'react';
import './Controls.css';

export default function Controls({
  colorMetric, onColorMetricChange,
  labelMode, onLabelModeChange,
  onRefresh, loading, lastUpdate
}) {
  return (
    <div className="controls">
      <label>着色指标:</label>
      <select value={colorMetric} onChange={e => onColorMetricChange(e.target.value)}>
        <option value="chg">今日涨幅</option>
        <option value="yearChg">年度涨幅</option>
        <option value="monthChg">月度涨幅</option>
        <option value="volume">成交量</option>
        <option value="amplitude">振幅</option>
      </select>

      <label>环节标签:</label>
      <select value={labelMode} onChange={e => onLabelModeChange(e.target.value)}>
        <option value="stock">股票名</option>
        <option value="link">环节名</option>
        <option value="both">环节+股票</option>
      </select>

      <button className="refresh-btn" onClick={onRefresh} disabled={loading}>
        {loading ? '⏳ 刷新中...' : '🔄 刷新数据'}
      </button>

      <div className="legend">
        <span className="legend-item">
          <span className="legend-color" style={{background: '#00c853'}}></span>涨&gt;5%
        </span>
        <span className="legend-item">
          <span className="legend-color" style={{background: '#2ea043'}}></span>涨3-5%
        </span>
        <span className="legend-item">
          <span className="legend-color" style={{background: '#8b949e'}}></span>±1%
        </span>
        <span className="legend-item">
          <span className="legend-color" style={{background: '#f85149'}}></span>跌3-5%
        </span>
        <span className="legend-item">
          <span className="legend-color" style={{background: '#7d1a2c'}}></span>跌&gt;5%
        </span>
      </div>

      <div className="update-time">🕐 {lastUpdate}</div>
    </div>
  );
}
