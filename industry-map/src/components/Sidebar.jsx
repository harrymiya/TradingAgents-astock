import React, { useState, useEffect, useRef } from 'react';
import './Sidebar.css';
import ScreeningPanel from './ScreeningPanel';

const API_BASE = 'https://qt.gtimg.cn/q=';
const BATCH_SIZE = 30;
const CACHE_TTL = 300000;

export default function Sidebar({ industries, current, onSelect }) {
  const [industryHeat, setIndustryHeat] = useState({});
  const cacheRef = useRef(null);
  const [activeTab, setActiveTab] = useState('industry');

  useEffect(() => {
    const now = Date.now();
    if (cacheRef.current && (now - cacheRef.current.time) < CACHE_TTL) {
      setIndustryHeat(cacheRef.current.data);
      return;
    }

    const samples = {};
    for (const [name, info] of Object.entries(industries)) {
      if (!info.sections) continue;
      const codes = [];
      for (const sec of info.sections) {
        for (const link of sec.links) {
          for (const c of (link.stocks || [])) {
            if (/^\d{6}$/.test(c) && codes.length < 5) codes.push(c);
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
        } catch (e) {}
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

  const heatSorted = React.useMemo(() => {
    const list = [];
    for (const [name, info] of Object.entries(industries)) {
      if (!info.sections) continue;
      let stockCount = 0;
      let linkCount = 0;
      for (const sec of info.sections) {
        linkCount += sec.links.length;
        for (const link of sec.links) {
          stockCount += (link.stocks || []).length;
        }
      }

      const heatInfo = industryHeat[name] || { avgChg: 0 };
      list.push({
        name, links: linkCount, stocks: stockCount,
        avgChg: heatInfo.avgChg,
        completeness: Math.min(100, Math.round((linkCount / 25) * 100)),
      });
    }
    list.sort((a, b) => {
      if (a.completeness === 0 && b.completeness > 0) return 1;
      if (b.completeness === 0 && a.completeness > 0) return -1;
      return b.avgChg - a.avgChg;
    });
    return list;
  }, [industries, industryHeat]);

  const getHeatDot = (avgChg) => {
    if (avgChg > 1) return { color: '#ff6b6b', label: '热门' };
    if (avgChg > -1) return { color: '#6e7681', label: '中性' };
    return { color: '#58a6ff', label: '冷门' };
  };

  const currentInfo = industries[current];
  let currentLinkCount = 0, currentStockCount = 0;
  if (currentInfo && currentInfo.sections) {
    for (const sec of currentInfo.sections) {
      currentLinkCount += sec.links.length;
      for (const link of sec.links) {
        currentStockCount += (link.stocks || []).length;
      }
    }
  }

  return (
    <div className="sidebar">
      <div className="sidebar-tabs">
        <button
          className={`sidebar-tab ${activeTab === 'industry' ? 'active' : ''}`}
          onClick={() => setActiveTab('industry')}
        >🗺️ 产业链</button>
        <button
          className={`sidebar-tab ${activeTab === 'screening' ? 'active' : ''}`}
          onClick={() => setActiveTab('screening')}
        >🎯 选股</button>
      </div>

      {activeTab === 'industry' && (
        <>
          <div className="industry-list">
            {heatSorted.map(({ name, stocks, avgChg, completeness }) => (
              <button
                  key={name}
                  className={`industry-btn ${name === current ? 'active' : ''}`}
                  title={`${name} — ${avgChg > 0 ? '+' : ''}${avgChg.toFixed(1)}% ${getHeatDot(avgChg).label}`}
                  onClick={() => onSelect(name)}
                >
                  <span className="heat-dot" style={{ background: getHeatDot(avgChg).color }}></span>
                  <span className="btn-name">{name}</span>
                  <span className="heat-chg" style={{
                    color: avgChg > 0 ? '#ff6b6b' : avgChg < 0 ? '#51cf66' : '#8b949e'
                  }}>{avgChg > 0 ? '+' : ''}{avgChg.toFixed(1)}%</span>
                  <span className={`completeness ${completeness >= 70 ? 'high' : completeness >= 40 ? 'mid' : 'low'}`}>
                    {completeness}%
                  </span>
                  <span className="badge">{stocks}家</span>
              </button>
            ))}
          </div>
          {currentInfo && currentInfo.sections && (
            <div className="industry-desc">
              <div className="desc-stats">
                <span>🏗️ {currentLinkCount}个环节</span>
                <span>📈 {currentStockCount}只股票</span>
              </div>
            </div>
          )}
        </>
      )}

      {activeTab === 'screening' && (
        <ScreeningPanel />
      )}
    </div>
  );
}
