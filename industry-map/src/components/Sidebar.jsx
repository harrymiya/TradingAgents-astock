import React, { useState, useEffect, useRef } from 'react';
import './Sidebar.css';
import ScreeningPanel from './ScreeningPanel';

const API_BASE = 'https://qt.gtimg.cn/q=';
const BATCH_SIZE = 30;
const CACHE_TTL = 300000; // 5分钟

export default function Sidebar({ industries, current, onSelect, selectedStock, onSelectScreening }) {
  const [industryHeat, setIndustryHeat] = useState({});
  const cacheRef = useRef(null);
  const [activeTab, setActiveTab] = useState('industry'); // industry | screening

  // 获取各行业实时涨跌幅（每个行业取前5只估算）
  useEffect(() => {
    const now = Date.now();
    if (cacheRef.current && (now - cacheRef.current.time) < CACHE_TTL) {
      setIndustryHeat(cacheRef.current.data);
      return;
    }

    const samples = {};
    for (const [name, info] of Object.entries(industries)) {
      if (name.startsWith('_')) continue;
      const codes = [];
      for (const ld of Object.values(info['环节'] || {})) {
        for (const c of (ld['股票'] || [])) {
          if (/^\d{6}$/.test(c) && codes.length < 5) {
            codes.push(c);
          }
        }
      }
      if (codes.length > 0) samples[name] = codes;
    }

    const allCodes = [...new Set(Object.values(samples).flat())];

    const fetchPrices = async () => {
      const results = {};
      for (let i = 0; i < allCodes.length; i += BATCH_SIZE) {
        const batch = allCodes.slice(i, i + BATCH_SIZE);
        const qtCodes = batch.map(c => (c.startsWith('6') ? 'sh' : 'sz') + c);
        try {
          const resp = await fetch(`${API_BASE}${qtCodes.join(',')}&_=${now}`);
          const buf = await resp.arrayBuffer();
          const decoder = new TextDecoder('gb18030');
          const text = decoder.decode(buf);
          for (const line of text.split(';')) {
            if (!line || !line.includes('~')) continue;
            const parts = line.split('~');
            const m = parts[0]?.match(/(\d{6})/);
            const code = m ? m[1] : '';
            if (!code) continue;
            results[code] = parseFloat(parts[32]) || 0;
          }
        } catch (e) {
          // silent
        }
      }

      const heat = {};
      for (const [name, codes] of Object.entries(samples)) {
        const chgs = codes.map(c => results[c] || 0);
        const avg = chgs.length > 0 ? chgs.reduce((a, b) => a + b, 0) / chgs.length : 0;
        heat[name] = { avgChg: Math.round(avg * 100) / 100, sampleCount: codes.length };
      }

      cacheRef.current = { data: heat, time: Date.now() };
      setIndustryHeat(heat);
    };

    fetchPrices();
  }, [industries]);

  // 排序+热度标记
  const heatSorted = React.useMemo(() => {
    const list = [];
    for (const [name, info] of Object.entries(industries)) {
      if (name.startsWith('_')) continue;
      let stocks = 0;
      const linksCount = Object.keys(info['环节']).length;
      for (const l of Object.values(info['环节'])) {
        stocks += l['股票'].length;
      }
      const heatInfo = industryHeat[name] || { avgChg: 0 };
      list.push({ name, links: linksCount, stocks, avgChg: heatInfo.avgChg });
    }
    list.sort((a, b) => b.avgChg - a.avgChg);
    return list;
  }, [industries, industryHeat]);

  const getHeatDot = (avgChg) => {
    if (avgChg > 1) return { color: '#ff6b6b', label: '热门' };
    if (avgChg > -1) return { color: '#6e7681', label: '中性' };
    return { color: '#58a6ff', label: '冷门' };
  };

  const currentInfo = industries[current];
  const currentStockCount = heatSorted.find(i => i.name === current)?.stocks || 0;

  const handleSelectScreening = (item) => {
    // 切换tab到产业链，并选中该股票
    setActiveTab('industry');
    if (onSelectScreening) {
      onSelectScreening(item);
    }
  };

  return (
    <div className="sidebar">
      {/* Tabs */}
      <div className="sidebar-tabs">
        <button
          className={`sidebar-tab ${activeTab === 'industry' ? 'active' : ''}`}
          onClick={() => setActiveTab('industry')}
        >
          🗺️ 产业链
        </button>
        <button
          className={`sidebar-tab ${activeTab === 'screening' ? 'active' : ''}`}
          onClick={() => setActiveTab('screening')}
        >
          🎯 选股
        </button>
      </div>

      {activeTab === 'industry' && (
        <>
          <div className="industry-list">
            {heatSorted.map(({ name, stocks, avgChg }) => {
              return (
                <button
                  key={name}
                  className={`industry-btn ${name === current ? 'active' : ''}`}
                  onClick={() => onSelect(name)}
                  title={`${name} — ${avgChg > 0 ? '+' : ''}${avgChg.toFixed(1)}% ${getHeatDot(avgChg).label}`}
                >
                  <span className="heat-dot" style={{ background: getHeatDot(avgChg).color }}></span>
                  <span className="btn-name">{name}</span>
                  <span className="heat-chg" style={{
                    color: avgChg > 0 ? '#ff6b6b' : avgChg < 0 ? '#51cf66' : '#8b949e'
                  }}>{avgChg > 0 ? '+' : ''}{avgChg.toFixed(1)}%</span>
                  <span className="badge">{stocks}家</span>
                </button>
              );
            })}
          </div>
          {currentInfo && (
            <div className="industry-desc">
              <p>{currentInfo['描述']}</p>
              <div className="desc-stats">
                <span>🏗️ {Object.keys(currentInfo['环节']).length}个环节</span>
                <span>📈 {currentStockCount}只股票</span>
              </div>
            </div>
          )}
        </>
      )}

      {activeTab === 'screening' && (
        <ScreeningPanel onSelectScreening={handleSelectScreening} />
      )}
    </div>
  );
}
