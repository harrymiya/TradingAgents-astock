import React, { useState, useEffect, useRef, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import GraphCanvas from './components/GraphCanvas';
import Controls from './components/Controls';
import Tooltip from './components/Tooltip';
import DetailPanel from './components/DetailPanel';
import KlinePanel from './components/KlinePanel';
import frameworksData from './data/frameworks_data.json';
import stockNames from './data/stock_names.json';
import yearStartPrices from './data/year_start_prices.json';
import './App.css';

const API_BASE = 'https://qt.gtimg.cn/q=';
const BATCH_SIZE = 30;

function getInitParams() {
  const hash = window.location.hash.replace('#', '');
  const params = new URLSearchParams(hash);
  let savedMode = localStorage.getItem('layoutMode') || 'horizontal';
  if (params.get('mode') === 'horizontal' || params.get('mode') === 'force' || params.get('mode') === 'star') {
    savedMode = params.get('mode');
  }
  const keys = Object.keys(frameworksData);
  return {
    industry: params.get('industry') || (keys[0] || ''),
    metric: params.get('metric') || 'yearChg',
    layout: savedMode,
  };
}

function collectCodes(industry) {
  if (!industry || !industry.sections) return [];
  const codes = [];
  for (const sec of industry.sections) {
    for (const link of sec.links) {
      for (const c of (link.stocks || [])) {
        const code = typeof c === 'string' ? c : c.code;
        if (/^\d{6}$/.test(code)) codes.push(code);
      }
    }
  }
  return [...new Set(codes)];
}

async function batchFetchQtCodes(codes) {
  if (!codes || codes.length === 0) return {};
  const results = {};
  for (let i = 0; i < codes.length; i += BATCH_SIZE) {
    const batch = codes.slice(i, i + BATCH_SIZE);
    const qtCodes = batch.map(c => (c.startsWith('6') ? 'sh' : 'sz') + c);
    try {
      const resp = await fetch(`${API_BASE}${qtCodes.join(',')}&_=${Date.now()}`);
      const buf = await resp.arrayBuffer();
      const decoder = new TextDecoder('gb18030');
      const text = decoder.decode(buf);
      for (const line of text.split(';')) {
        if (!line.trim() || !line.includes('~')) continue;
        const parts = line.split('~');
        const rawCode = parts[0] || '';
        const codeMatch = rawCode.match(/(\d{6})/);
        const code = codeMatch ? codeMatch[1] : rawCode;
        if (!code) continue;
        const name = parts[1] || stockNames[code] || code;
        const price = parseFloat(parts[3]) || 0;
        const yearStart = yearStartPrices[code];
        const yearChg = yearStart ? (price - yearStart) / yearStart * 100 : 0;
        results[code] = {
          price: price,
          chg: parseFloat(parts[32]) || 0,
          yearChg: yearChg,
          volume: parseInt(parts[6]) || 0,
          amount: parseFloat(parts[37]) || 0,
          amplitude: (parseFloat(parts[33]) && parseFloat(parts[34])) ?
            ((parseFloat(parts[33]) - parseFloat(parts[34])) / parseFloat(parts[34]) * 100) : 0,
          pe: parseFloat(parts[39]) || 0,
          pb: parseFloat(parts[48]) || 0,
          name,
        };
      }
    } catch (e) {
      console.warn('Batch fetch error:', e);
    }
  }
  return results;
}

/** 拖拽条组件 */
function ResizeHandle({ target, sidebarRef, detailRef, setSidebarWidth, setDetailWidth }) {
  const handleRef = useRef(null);
  const dragging = useRef(false);
  const startX = useRef(0);
  const startW = useRef(0);

  const onMouseDown = useCallback((e) => {
    e.preventDefault();
    dragging.current = true;
    startX.current = e.clientX;
    startW.current = target === 'sidebar' ? sidebarRef.current : detailRef.current;
    handleRef.current?.classList.add('active');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [target, sidebarRef, detailRef]);

  useEffect(() => {
    const onMouseMove = (e) => {
      if (!dragging.current) return;
      const dx = e.clientX - startX.current;
      let newW;
      if (target === 'sidebar') {
        newW = Math.max(200, Math.min(startW.current + dx, 600));
        sidebarRef.current = newW;
        setSidebarWidth(newW);
      } else {
        newW = Math.max(220, Math.min(startW.current - dx, 600));
        detailRef.current = newW;
        setDetailWidth(newW);
      }
    };
    const onMouseUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      handleRef.current?.classList.remove('active');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [target, setSidebarWidth, setDetailWidth, sidebarRef, detailRef]);

  return (
    <div className="resize-handle" ref={handleRef} onMouseDown={onMouseDown} />
  );
}

export default function App() {
  const init = getInitParams();
  const [currentIndustry, setCurrentIndustry] = useState(init.industry);
  const [colorMetric, setColorMetric] = useState(init.metric);
  const [layoutMode, setLayoutMode] = useState(init.layout);
  const [stockPrices, setStockPrices] = useState({});
  const [tooltip, setTooltip] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(new Date().toLocaleTimeString('zh-CN'));
  const [selectedNode, setSelectedNode] = useState(null);
  const [klineStock, setKlineStock] = useState(null);
  const [detailHistory, setDetailHistory] = useState([]);
  const [analysisState, setAnalysisState] = useState({});

  // 左右栏宽度（默认值）
  const [sidebarWidth, setSidebarWidth] = useState(310);
  const [detailWidth, setDetailWidth] = useState(320);
  const sidebarRef = useRef(310);
  const detailRef = useRef(320);

  const graphRef = useRef(null);
  const appRef = useRef(null);

  const getQryCodes = useCallback(() => {
    return collectCodes(frameworksData[currentIndustry]);
  }, [currentIndustry]);

  const fetchPrices = useCallback(async () => {
    const codes = getQryCodes();
    if (codes.length === 0) {
      setLastUpdate(new Date().toLocaleTimeString('zh-CN'));
      return;
    }
    setLoading(true);
    const results = await batchFetchQtCodes(codes);
    setStockPrices(prev => ({ ...prev, ...results }));
    setLastUpdate(new Date().toLocaleTimeString('zh-CN'));
    setLoading(false);
  }, [getQryCodes]);

  useEffect(() => { fetchPrices(); }, [currentIndustry, fetchPrices]);

  const handleSelectStock = useCallback((item) => {
    const node = {
      id: item.code,
      code: item.code,
      name: item.name,
      type: 'stock',
      chg: item.chg || 0,
      price: item.close || 0,
      chain: item.chain,
      score_detail: item.score_detail,
      total_score: item.total_score,
      xies_comment: item.xies_comment,
      macro_comment: item.macro_comment,
      ma60: item.ma60,
      pos20: item.pos20,
      ma20: item.ma20,
      vr5: item.vr5,
      mcap: item.mcap,
      dd: item.dd,
    };
    setSelectedNode(node);
    setTooltip(null);
    setDetailHistory([]);
    if (node.code && /^\d{6}$/.test(node.code)) {
      setKlineStock({ code: node.code, name: node.name || node.code });
    }
  }, []);

  const handleNodeClick = useCallback((node) => {
    setSelectedNode(node);
    setTooltip(null);
    setDetailHistory([]);
    if (node && node.code && /^\d{6}$/.test(node.code)) {
      setKlineStock({ code: node.code, name: node.name || node.code });
    } else {
      setKlineStock(null);
    }
  }, []);

  const handleBack = useCallback(() => {
    setDetailHistory(prev => prev.slice(0, -1));
  }, []);

  const currentData = frameworksData[currentIndustry];

  return (
    <div className="app" ref={appRef}>
      <Sidebar
        industries={frameworksData}
        current={currentIndustry}
        onSelect={setCurrentIndustry}
        onSelectScreening={handleSelectStock}
        selectedCode={selectedNode?.code}
        onAnalysisUpdate={setAnalysisState}
        style={{ width: sidebarWidth, minWidth: 200 }}
      />
      <ResizeHandle target="sidebar" sidebarRef={sidebarRef} detailRef={detailRef} setSidebarWidth={setSidebarWidth} setDetailWidth={setDetailWidth} />
      <div className="main">
        <Controls
          colorMetric={colorMetric}
          onColorMetricChange={setColorMetric}
          layoutMode={layoutMode}
          onLayoutModeChange={setLayoutMode}
          onRefresh={fetchPrices}
          loading={loading}
          lastUpdate={lastUpdate}
        />
        <div className="graph-container" ref={graphRef}>
          <div className="graph-canvas-wrap">
            {currentData ? (
              <GraphCanvas
                layoutMode={layoutMode}
                industry={currentData}
                stockPrices={stockPrices}
                colorMetric={colorMetric}
                onTooltip={setTooltip}
                onNodeClick={handleNodeClick}
                selectedNode={selectedNode}
              />
            ) : (
              <div className="no-industry-hint">请选择产业链</div>
            )}
            {tooltip && (
              <Tooltip data={tooltip} onClose={() => setTooltip(null)} />
            )}
          </div>
        </div>
        {klineStock && (
          <KlinePanel
            code={klineStock.code}
            name={klineStock.name}
            onClose={() => setKlineStock(null)}
          />
        )}
      </div>
      <ResizeHandle target="detail" sidebarRef={sidebarRef} detailRef={detailRef} setSidebarWidth={setSidebarWidth} setDetailWidth={setDetailWidth} />
      <DetailPanel
        selectedNode={selectedNode}
        stockPrices={stockPrices}
        industryName={currentIndustry}
        industryData={frameworksData}
        onSelectStock={handleSelectStock}
        onBack={handleBack}
        history={detailHistory}
        analysisState={analysisState}
        style={{ width: detailWidth, minWidth: 220, maxWidth: 600 }}
      />
    </div>
  );
}
