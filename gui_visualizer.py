import sys
import os
import glob
import json
import pandas as pd
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QComboBox, QPushButton, QLabel, QTabWidget, QToolBar, 
                             QDialog, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QFrame, QCheckBox, QTextEdit, QSpinBox)
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QShortcut, QKeySequence, QColor, QFont

# --- PROFESSIONAL DARK THEME ---
DARK_THEME = """
QMainWindow, QDialog { background-color: #000000; }
QWidget { background-color: #000000; color: #D0D0D0; font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 12px; }
QToolBar { background-color: #0A0A0A; border-bottom: 1px solid #222; spacing: 12px; padding: 6px; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: #0A0A0A; padding: 8px 25px; border-right: 1px solid #111; color: #666; font-weight: bold; }
QTabBar::tab:selected { background: #111; color: #2196F3; border-bottom: 2px solid #2196F3; }
QComboBox { background-color: #111; border: 1px solid #333; border-radius: 4px; padding: 4px 10px; min-width: 130px; }
QPushButton { background-color: #2196F3; color: white; border: none; border-radius: 4px; padding: 6px 15px; font-weight: bold; }
QPushButton:hover { background-color: #1E88E5; }
QPushButton#selectorBtn { background-color: #111; border: 1px solid #333; color: #2196F3; }
QTableWidget { background-color: #050505; gridline-color: #111; border: none; }
QHeaderView::section { background-color: #0A0A0A; color: #555; padding: 4px; border: 1px solid #111; text-transform: uppercase; font-size: 10px; }
QCheckBox { spacing: 8px; font-weight: bold; color: #888; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #444; border-radius: 3px; background: #111; }
QCheckBox::indicator:checked { background: #2196F3; border-color: #2196F3; }
"""

import math

class TimeAxisItem(pg.AxisItem):
    def __init__(self, t_start, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.t_start = t_start
    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            try:
                dt = self.t_start + pd.to_timedelta(v, unit='s')
                strings.append(dt.strftime("%H:%M:%S"))
            except: strings.append("")
        return strings

class FloatingInspector(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.SubWindow | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(320, 420)
        self.setStyleSheet("background-color: rgba(5, 5, 5, 230); border: 1px solid #333; border-radius: 6px;")
        layout = QVBoxLayout(self)
        self.text = QTextEdit(); self.text.setReadOnly(True)
        self.text.setStyleSheet("background: transparent; border: none; color: #DDD;")
        layout.addWidget(self.text)
        self.hide(); self._drag_pos = None

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton: self._drag_pos = e.globalPosition().toPoint()
    def mouseMoveEvent(self, e):
        if self._drag_pos:
            delta = e.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta); self._drag_pos = e.globalPosition().toPoint()

class OptionChainDialog(QDialog):
    def __init__(self, parent, underlying, instruments):
        super().__init__(parent)
        self.setWindowTitle(f"Instrument Selector: {underlying}"); self.resize(900, 700)
        self.setStyleSheet(DARK_THEME)
        layout = QVBoxLayout(self); self.selected_key = None
        
        top = QHBoxLayout(); top.addWidget(QLabel("EXPIRY:"))
        self.expiry_combo = QComboBox()
        expiries = sorted(list(set(i['expiry'] for i in instruments if i['expiry'])))
        self.expiry_combo.addItems(expiries); self.expiry_combo.currentTextChanged.connect(self.populate)
        top.addWidget(self.expiry_combo); top.addStretch(); layout.addLayout(top)
        
        self.table = QTableWidget(); self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["CALL OPTION", "STRIKE", "PUT OPTION"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(self.select_item)
        layout.addWidget(self.table); self.instruments = instruments; self.populate()

    def populate(self):
        self.table.setRowCount(0); exp = self.expiry_combo.currentText()
        strikes = {}
        for i in self.instruments:
            if i['expiry'] != exp: continue
            s = i['strike']
            if s not in strikes: strikes[s] = {'CE': None, 'PE': None}
            strikes[s][i['type']] = i
            
        for s in sorted(strikes.keys()):
            row = self.table.rowCount(); self.table.insertRow(row)
            ce, pe = strikes[s]['CE'], strikes[s]['PE']
            if ce:
                it = QTableWidgetItem(ce['full_name']); it.setData(Qt.ItemDataRole.UserRole, ce['key'])
                it.setForeground(QColor("#00C853")); it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, 0, it)
            
            it_s = QTableWidgetItem(str(s)); it_s.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_s.setFont(QFont("Monospace", 10, QFont.Weight.Bold)); self.table.setItem(row, 1, it_s)
            
            if pe:
                it = QTableWidgetItem(pe['full_name']); it.setData(Qt.ItemDataRole.UserRole, pe['key'])
                it.setForeground(QColor("#FF1744")); it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, 2, it)

    def select_item(self, item):
        self.selected_key = item.data(Qt.ItemDataRole.UserRole)
        if self.selected_key: self.accept()

class VisualizerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ProOrderflow Visualizer v2.2"); self.resize(1600, 900)
        self.setStyleSheet(DARK_THEME)
        
        self.master_mapping = {}; self.underlyings = {}
        self.df = pd.DataFrame(); self.inst_df = pd.DataFrame()
        self.t_start = None; self.current_mouse_pos = None

        self.load_metadata(); self.init_ui(); self.init_shortcuts()
        self.refresh_instruments()

    def load_metadata(self):
        if not os.path.exists('complete.json'): return
        try:
            with open('complete.json', 'r') as f:
                for item in json.load(f):
                    key = item.get('instrument_key')
                    if not key: continue
                    sym = item.get('trading_symbol', '')
                    parts = sym.split()
                    meta = {'key': key, 'full_name': sym, 'underlying': item.get('name', 'OTHER'),
                            'type': 'CE' if ' CE ' in sym else ('PE' if ' PE ' in sym else 'EQ'),
                            'strike': 0, 'expiry': ''}
                    if meta['type'] in ['CE', 'PE'] and len(parts) >= 4:
                        try: meta['strike'] = float(parts[1]); meta['expiry'] = " ".join(parts[3:])
                        except: pass
                    self.master_mapping[key] = meta
        except Exception as e: print(f"Meta Error: {e}")

    def init_ui(self):
        toolbar = QToolBar(); toolbar.setMovable(False); self.addToolBar(toolbar)
        
        toolbar.addWidget(QLabel("FILE"))
        self.file_combo = QComboBox()
        self.file_combo.addItems([os.path.basename(f) for f in glob.glob('market_data_csv/*.csv')])
        self.file_combo.currentTextChanged.connect(self.refresh_instruments); toolbar.addWidget(self.file_combo)
        
        toolbar.addWidget(QLabel("UNDERLYING"))
        self.u_combo = QComboBox(); toolbar.addWidget(self.u_combo)
        
        self.sel_btn = QPushButton("SELECT INSTRUMENT"); self.sel_btn.setObjectName("selectorBtn")
        self.sel_btn.clicked.connect(self.open_selector); toolbar.addWidget(self.sel_btn)
        
        toolbar.addSeparator()
        self.cb_ltp = QCheckBox("LTP (1)"); self.cb_ltp.setChecked(True); self.cb_ltp.toggled.connect(self.sync_visibility); toolbar.addWidget(self.cb_ltp)
        self.cb_idx = QCheckBox("INDEX (2)"); self.cb_idx.setChecked(True); self.cb_idx.toggled.connect(self.sync_visibility); toolbar.addWidget(self.cb_idx)
        self.cb_bsm = QCheckBox("BSM"); self.cb_bsm.setChecked(False); self.cb_bsm.toggled.connect(self.sync_visibility); toolbar.addWidget(self.cb_bsm)
        
        toolbar.addWidget(QLabel("IV (%):"))
        self.iv_spin = QSpinBox(); self.iv_spin.setRange(1, 500); self.iv_spin.setValue(15); toolbar.addWidget(self.iv_spin)
        
        toolbar.addSeparator()
        self.scale_combo = QComboBox(); self.scale_combo.addItems(["Log", "Linear"]); toolbar.addWidget(self.scale_combo)
        
        load_btn = QPushButton("LOAD DATA"); load_btn.clicked.connect(self.load_data); toolbar.addWidget(load_btn)

        self.tabs = QTabWidget(); self.setCentralWidget(self.tabs)
        self.viz_tab = QWidget(); layout = QVBoxLayout(self.viz_tab); layout.setContentsMargins(0,0,0,0)
        
        self.t_axis = TimeAxisItem(pd.Timestamp.now(), orientation='bottom')
        self.pw = pg.PlotWidget(axisItems={'bottom': self.t_axis})
        self.pw.setBackground('#000000'); self.pw.showGrid(x=True, y=True, alpha=0.1)
        
        self.img = pg.ImageItem(); self.img.setZValue(-1); self.pw.addItem(self.img)
        # Disable interpolation for sharp pixel blocks
        self.pw.setAntialiasing(False)
        self.ltp_line = pg.PlotCurveItem(pen=pg.mkPen('#FFF', width=1.5), name="LTP"); self.ltp_line.setZValue(10); self.pw.addItem(self.ltp_line)
        self.bsm_line = pg.PlotCurveItem(pen=pg.mkPen('#E91E63', width=1.5, style=Qt.PenStyle.DotLine), name="BSM"); self.bsm_line.setZValue(11); self.pw.addItem(self.bsm_line)
        
        # Secondary Axis for Index
        self.p_idx = pg.ViewBox()
        self.pw.scene().addItem(self.p_idx)
        self.pw.getAxis('right').linkToView(self.p_idx)
        self.p_idx.setXLink(self.pw.getViewBox())
        self.idx_line = pg.PlotCurveItem(pen=pg.mkPen('#2196F3', width=1, style=Qt.PenStyle.DashLine)); self.p_idx.addItem(self.idx_line)
        
        def sync_views():
            self.p_idx.setGeometry(self.pw.getViewBox().sceneBoundingRect())
            self.p_idx.linkedViewChanged(self.pw.getViewBox(), self.p_idx.XAxis)
        self.pw.getViewBox().sigResized.connect(sync_views)
        self.pw.getViewBox().sigStateChanged.connect(sync_views)

        self.v_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#333'))
        self.h_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('#333'))
        self.pw.addItem(self.v_line); self.pw.addItem(self.h_line)
        
        # Measurement Tool
        self.measure_line = pg.PlotCurveItem(pen=pg.mkPen('#FFEB3B', width=2, style=Qt.PenStyle.DashLine))
        self.pw.addItem(self.measure_line)
        self.measure_start = None

        self.proxy = pg.SignalProxy(self.pw.scene().sigMouseMoved, rateLimit=60, slot=self.on_mouse)
        self.pw.scene().sigMouseClicked.connect(self.on_click)
        layout.addWidget(self.pw); self.tabs.addTab(self.viz_tab, "CHART")

        # IV Tab
        self.iv_tab = QWidget(); iv_layout = QVBoxLayout(self.iv_tab); iv_layout.setContentsMargins(0,0,0,0)
        self.iv_t_axis = TimeAxisItem(pd.Timestamp.now(), orientation='bottom')
        self.iv_pw = pg.PlotWidget(axisItems={'bottom': self.iv_t_axis})
        self.iv_pw.setBackground('#000000'); self.iv_pw.showGrid(x=True, y=True, alpha=0.1)
        self.iv_pw.setLabel('left', 'IV (%)', color='#888')
        self.iv_line = pg.PlotCurveItem(pen=pg.mkPen('#E91E63', width=1.5), name="IV")
        self.iv_pw.addItem(self.iv_line)
        iv_layout.addWidget(self.iv_pw)
        self.tabs.addTab(self.iv_tab, "IV")

        self.inspector = FloatingInspector(self); self.inspector.move(50, 100)

    @staticmethod
    def calc_iv(market_price, S, K, T, r, option_type='CE'):
        """Reverse-calculate Implied Volatility via bisection."""
        def bsm(sigma):
            if sigma <= 0 or T <= 0: return 0.0
            d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
            d2 = d1 - sigma * math.sqrt(T)
            def ncdf(x): return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
            if option_type == 'CE':
                return S * ncdf(d1) - K * math.exp(-r * T) * ncdf(d2)
            else:
                return K * math.exp(-r * T) * ncdf(-d2) - S * ncdf(-d1)

        if market_price <= 0 or S <= 0 or K <= 0: return np.nan
        lo, hi = 1e-6, 20.0
        if bsm(hi) < market_price: return np.nan   # price above theoretical max
        if bsm(lo) > market_price: return 1e-6     # below intrinsic: return ~0% IV
        for _ in range(200):
            mid = (lo + hi) / 2
            if bsm(mid) < market_price:
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-6:
                break
        return (lo + hi) / 2

    def on_click(self, ev):

        if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            pos = ev.scenePos()
            if self.pw.sceneBoundingRect().contains(pos):
                mp = self.pw.plotItem.vb.mapSceneToView(pos)
                if ev.button() == Qt.MouseButton.LeftButton:
                    self.measure_start = (mp.x(), mp.y())
                    self.measure_line.setData([mp.x(), mp.x()], [mp.y(), mp.y()])
                elif ev.button() == Qt.MouseButton.RightButton:
                    self.measure_start = None
                    self.measure_line.clear()
                    self.update_ins(mp.x(), mp.y())

    def init_shortcuts(self):
        QShortcut(QKeySequence('L'), self).activated.connect(self.load_data)
        QShortcut(QKeySequence('S'), self).activated.connect(self.open_selector)
        QShortcut(QKeySequence('V'), self).activated.connect(lambda: self.scale_combo.setCurrentIndex(1-self.scale_combo.currentIndex()))
        QShortcut(QKeySequence('D'), self).activated.connect(lambda: self.inspector.setVisible(not self.inspector.isVisible()))
        QShortcut(QKeySequence('1'), self).activated.connect(self.cb_ltp.toggle)
        QShortcut(QKeySequence('2'), self).activated.connect(self.cb_idx.toggle)
        QShortcut(QKeySequence('R'), self).activated.connect(self.reset_range)

    def refresh_instruments(self):
        f = os.path.join('market_data_csv', self.file_combo.currentText())
        if not os.path.exists(f): return
        try:
            keys = pd.read_csv(f, usecols=['instrument_key'])['instrument_key'].dropna().unique()
            self.underlyings = {}
            for k in keys:
                m = self.master_mapping.get(k, {'key': k, 'full_name': k, 'underlying': 'OTHER', 'type': 'EQ', 'strike': 0, 'expiry': 'N/A'})
                u = m['underlying']
                if u not in self.underlyings: self.underlyings[u] = []
                self.underlyings[u].append(m)
            self.u_combo.clear(); self.u_combo.addItems(sorted(self.underlyings.keys()))
        except: pass

    def open_selector(self):
        u = self.u_combo.currentText()
        if u in self.underlyings:
            dlg = OptionChainDialog(self, u, self.underlyings[u])
            if dlg.exec():
                self.selected_key = dlg.selected_key
                self.sel_btn.setText(f"SELECTED: {self.master_mapping.get(self.selected_key, {'full_name': self.selected_key})['full_name']}")

    def load_data(self):
        if not hasattr(self, 'selected_key'): return
        try:
            self.df = pd.read_csv(os.path.join('market_data_csv', self.file_combo.currentText()))
            self.df['timestamp'] = pd.to_datetime(self.df['timestamp']).dt.tz_localize(None).values.astype('datetime64[ns]')
            self.inst_df = self.df[self.df['instrument_key'] == self.selected_key].sort_values('timestamp').reset_index(drop=True)
            self.render()
        except Exception as e: print(f"Load error: {e}")

    def render(self):
        try:
            df = self.inst_df
            p_cols = [f'bid{i}_p' for i in range(1, 6)] + [f'ask{i}_p' for i in range(1, 6)]
            v_cols = [f'bid{i}_q' for i in range(1, 6)] + [f'ask{i}_q' for i in range(1, 6)]
            for c in p_cols + v_cols + ['ltp']: 
                if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')
            
            self.t_start = df['timestamp'].min(); self.t_axis.t_start = self.t_start
            t_sec = (df['timestamp'] - self.t_start).dt.total_seconds().values
            
            # LTP
            valid_ltp = df.dropna(subset=['ltp'])
            self.ltp_line.setData(t_sec[valid_ltp.index], valid_ltp['ltp'].values) if not valid_ltp.empty else self.ltp_line.clear()
            
            # Index Smart Overlay and BSM Calculation
            u_name = self.master_mapping.get(self.selected_key, {}).get('underlying')
            if u_name == 'NIFTY 50': u_name = 'Nifty 50'
            
            idx_key = next((k for k, v in self.master_mapping.items() if (v.get('underlying') == u_name or v.get('trading_symbol') == u_name) and 'INDEX' in k), None)
            if not idx_key and 'NIFTY' in (u_name or ''): idx_key = 'NSE_INDEX|Nifty 50'

            if idx_key:
                idf = self.df[self.df['instrument_key'] == idx_key].sort_values('timestamp')
                idf['ltp'] = pd.to_numeric(idf['ltp'], errors='coerce')
                valid_idx = idf.dropna(subset=['ltp'])
                
                if not valid_idx.empty:
                    idx_times = (valid_idx['timestamp'] - self.t_start.asm8).dt.total_seconds().values
                    idx_vals = valid_idx['ltp'].values
                    
                    # Normalize Index for Overlay
                    if not valid_ltp.empty:
                        ltp_vals = valid_ltp['ltp'].values
                        i_min, i_max = np.min(idx_vals), np.max(idx_vals)
                        l_min, l_max = np.min(ltp_vals), np.max(ltp_vals)
                        if i_max > i_min:
                            norm_idx = l_min + (idx_vals - i_min) / (i_max - i_min) * (l_max - l_min)
                            self.idx_line.setData(idx_times, norm_idx)
                            if self.idx_line not in self.pw.listDataItems():
                                self.p_idx.removeItem(self.idx_line); self.pw.addItem(self.idx_line)
                    
                    # Black-Scholes-Merton
                    meta = self.master_mapping.get(self.selected_key, {})
                    strike = meta.get('strike')
                    expiry_str = meta.get('expiry')
                    
                    if strike and expiry_str:
                        try:
                            # 1. Implied Volatility
                            iv_pct = self.iv_spin.value()
                            ann_vol = np.full(len(idx_vals), iv_pct / 100.0)
                            
                            if len(idx_vals) > 0:
                                
                                # 2. Time to Expiry (T in years)
                                exp_dt = pd.to_datetime(str(expiry_str) + f" {self.t_start.year} 15:30:00", errors='coerce')
                                if pd.isna(exp_dt):
                                    exp_dt = self.t_start + pd.DateOffset(days=30)
                                elif exp_dt < self.t_start:
                                    exp_dt = exp_dt + pd.DateOffset(years=1)
                                
                                T_all = (exp_dt - valid_idx['timestamp']).dt.total_seconds().values / 31536000.0
                                T_all = np.maximum(T_all, 1e-9) # Avoid division by zero
                                
                                # 3. BSM Formula (r=0.07 assumed)
                                r = 0.07; S = idx_vals; K = strike; sigma = ann_vol
                                
                                # NumPy doesn't have erf, use math.erf vectorized
                                v_erf = np.vectorize(math.erf)
                                def n_cdf(x): return 0.5 * (1.0 + v_erf(x / np.sqrt(2.0)))
                                
                                sigma = np.maximum(sigma, 1e-9) # Avoid division by zero
                                d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T_all) / (sigma*np.sqrt(T_all))
                                d2 = d1 - sigma*np.sqrt(T_all)
                                
                                if meta.get('type') == 'CE':
                                    bsm_prices = S * n_cdf(d1) - K * np.exp(-r*T_all) * n_cdf(d2)
                                else:
                                    bsm_prices = K * np.exp(-r*T_all) * n_cdf(-d2) - S * n_cdf(-d1)
                                
                                # Filter out NaN
                                mask = ~np.isnan(bsm_prices)
                                self.bsm_line.setData(idx_times[mask], bsm_prices[mask])

                                # --- Implied Volatility (reverse BSM from actual option LTP) ---
                                self.iv_t_axis.t_start = self.t_start
                                opt_type = meta.get('type', 'CE')
                                if not valid_ltp.empty:
                                    opt_times_sec = t_sec[valid_ltp.index]
                                    opt_prices = valid_ltp['ltp'].values
                                    # Interpolate index spot at each option tick timestamp
                                    interp_S = np.interp(opt_times_sec, idx_times, idx_vals)
                                    # T at each option tick
                                    T_opt = (exp_dt - valid_ltp['timestamp']).dt.total_seconds().values / 31536000.0
                                    T_opt = np.maximum(T_opt, 1e-9)
                                    # Calculate IV per tick
                                    calc_iv_vec = np.vectorize(self.calc_iv)
                                    iv_vals = calc_iv_vec(opt_prices, interp_S, float(strike), T_opt, r, opt_type)
                                    iv_mask = ~np.isnan(iv_vals) & (iv_vals >= 0) & (iv_vals < 5.0)
                                    self.iv_line.setData(opt_times_sec[iv_mask], iv_vals[iv_mask] * 100)
                                else:
                                    self.iv_line.clear()

                            else: self.bsm_line.clear(); self.iv_line.clear()
                        except Exception as e:
                            import traceback
                            print(f"BSM Calc Error:\n{traceback.format_exc()}"); self.bsm_line.clear(); self.iv_line.clear()
                    else: self.bsm_line.clear(); self.iv_line.clear()
                else: self.idx_line.clear(); self.bsm_line.clear(); self.iv_line.clear()
            else: self.idx_line.clear(); self.bsm_line.clear(); self.iv_line.clear()

            # Orderbook
            dd = df.dropna(subset=p_cols, how='all')
            if not dd.empty:
                all_p = pd.to_numeric(dd[p_cols].values.flatten(), errors='coerce')
                all_p = all_p[~np.isnan(all_p)]
                p_min, p_max = np.min(all_p), np.max(all_p)
                p_range = max(float(p_max - p_min), 0.05)
                
                # Dynamic RES_X to stay within GPU texture limits (usually 16384)
                MAX_W = 16000
                duration = t_sec[-1] if t_sec[-1] > 0 else 1
                RES_X = min(100, MAX_W / duration) 
                
                W, H = int(duration * RES_X) + 1, min(max(int(p_range / 0.05) + 1, 1000), 4000)
                img = np.full((W, H, 3), 20, dtype=np.uint8) # Slightly brighter background
                
                all_v = pd.to_numeric(dd[v_cols].values.flatten(), errors='coerce')
                all_v = all_v[all_v > 0]
                m_log, v_99 = (np.log1p(np.max(all_v)) if all_v.size else 1, np.percentile(all_v, 99) if all_v.size else 1)
                is_lin = self.scale_combo.currentText() == "Linear"

                def get_iv(v):
                    val = (min(v, v_99) / v_99) if is_lin else (np.log1p(v) / m_log)
                    return int(255 * max(0.1, val))

                timestamps = dd['timestamp'].values
                # Map each timestamp exactly to its pixel index
                sx_all = ((timestamps - self.t_start.asm8) / np.timedelta64(1, 's') * RES_X).astype(int)
                
                bp = {l: dd[f'bid{l}_p'].values for l in range(1, 6)}
                bq = {l: dd[f'bid{l}_q'].values for l in range(1, 6)}
                ap = {l: dd[f'ask{l}_p'].values for l in range(1, 6)}
                aq = {l: dd[f'ask{l}_q'].values for l in range(1, 6)}

                th_px = (0.05 / p_range) * (H - 1)
                half_th = max(0.6, th_px / 2) 

                for i in range(len(dd)):
                    sx = sx_all[i]
                    ex = sx_all[i+1] if i < len(dd)-1 else W
                    ex = min(max(sx + 1, ex), W)
                    if sx >= W: continue
                    
                    for l in range(1, 6):
                        # Bids
                        p, q = bp[l][i], bq[l][i]
                        if not np.isnan(p) and q > 0:
                            yc = (p - p_min) / p_range * (H - 1)
                            y0, y1 = int(yc - half_th), int(yc + half_th + 1)
                            y0, y1 = min(max(y0, 0), H-1), min(max(y1, 0), H)
                            if y1 > y0:
                                iv = get_iv(q)
                                # Fill the block
                                img[sx:ex, y0:y1, 1] = np.maximum(img[sx:ex, y0:y1, 1], iv)
                                # Visual boundary: darken the first pixel of the entry for alignment
                                if ex > sx: img[sx, y0:y1, 1] = iv // 2
                        
                        # Asks
                        p, q = ap[l][i], aq[l][i]
                        if not np.isnan(p) and q > 0:
                            yc = (p - p_min) / p_range * (H - 1)
                            y0, y1 = int(yc - half_th), int(yc + half_th + 1)
                            y0, y1 = min(max(y0, 0), H-1), min(max(y1, 0), H)
                            if y1 > y0:
                                iv = get_iv(q)
                                img[sx:ex, y0:y1, 0] = np.maximum(img[sx:ex, y0:y1, 0], iv)
                                if ex > sx: img[sx, y0:y1, 0] = iv // 2

                self.img.setImage(img.astype(np.uint8), autoLevels=False, levels=[0, 255])
                # Precision fix: setRect should match the pixel count exactly
                self.img.setRect(QRectF(0, p_min, W / RES_X, p_range))
            else: self.img.clear()
            
            self.sync_visibility(); self.reset_range()
        except Exception as e: print(f"Render error: {e}")

    def sync_visibility(self):
        self.ltp_line.setVisible(self.cb_ltp.isChecked())
        self.idx_line.setVisible(self.cb_idx.isChecked())
        self.bsm_line.setVisible(self.cb_bsm.isChecked())

    def reset_range(self):
        self.pw.autoRange()
        if self.cb_idx.isChecked() and not self.idx_line.getData()[0] is None:
            self.p_idx.autoRange()

    def on_mouse(self, evt):
        pos = evt[0]
        if self.pw.sceneBoundingRect().contains(pos):
            mp = self.pw.plotItem.vb.mapSceneToView(pos)
            self.v_line.setPos(mp.x()); self.h_line.setPos(mp.y())
            
            if self.measure_start:
                self.measure_line.setData([self.measure_start[0], mp.x()], [self.measure_start[1], mp.y()])
            
            if self.inspector.isVisible(): self.update_ins(mp.x(), mp.y())

    def update_ins(self, x, y):
        if self.inst_df.empty: return
        try:
            target = self.t_start + pd.to_timedelta(x, unit='s')
            # Use side='right' and subtract 1 to get the record ACTIVE at time x
            idx = np.searchsorted(self.inst_df['timestamp'].values, target.asm8.astype('datetime64[ns]'), side='right') - 1
            idx = min(max(idx, 0), len(self.inst_df)-1)
            r = self.inst_df.iloc[idx]
            
            h = f"<div style='font-size:12px;'><b style='color:#2196F3'>TIME:</b> {r['timestamp'].strftime('%H:%M:%S.%f')[:-3]}<br>"
            h += f"<b style='color:#2196F3'>PX:</b> {y:.2f} | <b style='color:#2196F3'>LTP:</b> {r.get('ltp','N/A')}<br>"
            
            if self.measure_start:
                dx = x - self.measure_start[0]
                dy = y - self.measure_start[1]
                pct = (dy / self.measure_start[1] * 100) if self.measure_start[1] != 0 else 0
                color = "#00C853" if dy >= 0 else "#FF1744"
                h += f"<div style='background:#111; padding:4px; margin:4px 0; border-left:3px solid {color};'>"
                h += f"<b style='color:#FFEB3B'>DELTA:</b> <span style='color:{color}'>{dy:+.2f} ({pct:+.3f}%)</span><br>"
                h += f"<b style='color:#FFEB3B'>TIME:</b> {abs(dx):.2f}s</div>"

            h += "<hr><table width='100%'>"
            for i in range(1, 6): h += f"<tr><td>{i}</td><td style='color:#00C853'>{int(r.get(f'bid{i}_q',0))}</td><td>{r.get(f'bid{i}_p',0):.2f}</td><td>{r.get(f'ask{i}_p',0):.2f}</td><td style='color:#FF1744'>{int(r.get(f'ask{i}_q',0))}</td></tr>"
            self.inspector.text.setHtml(h + "</table></div>")
        except: pass

if __name__ == "__main__":
    app = QApplication(sys.argv); viz = VisualizerApp(); viz.show(); sys.exit(app.exec())
