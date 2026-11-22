"""Streamlit interface for the FullShelf inventory decision-support prototype."""

from __future__ import annotations

import hashlib
import html
import logging
import math
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from gemini_agent import (
    AgentError,
    answer_inventory_question,
    suggest_column_mapping,
)
from inventory_engine import (
    InventoryValidationError,
    analyze_inventory,
    inspect_inventory_file,
    list_workbook_sheets,
    suggest_inventory_sheet,
    validate_inventory_file,
)

APP_DIR = Path(__file__).resolve().parent
ASSETS_DIR = APP_DIR / "assets"
SAMPLE_PATH = APP_DIR / "data" / "sample_inventory.csv"
JOHANNESBURG = ZoneInfo("Africa/Johannesburg")

logging.basicConfig(level=logging.INFO)

NAV_ITEMS = [
    ("Dashboard", "dashboard"),
    ("Inventory", "inventory_2"),
    ("Priorities", "flag"),
    ("Assistant", "forum"),
]

SORT_OPTIONS = ["Urgency", "Name", "Inventory value", "Coverage"]
STATUS_LABELS = {
    "OUT OF STOCK": "Out of stock",
    "SHORTAGE RISK": "Shortage risk",
    "REORDER NOW": "Reorder now",
    "HEALTHY": "Healthy",
    "NO RECORDED DEMAND": "No demand",
}
STATUS_OPTIONS = list(STATUS_LABELS.values())
ATTENTION_STATUSES = ("OUT OF STOCK", "SHORTAGE RISK", "REORDER NOW")
STATUS_META = {
    "OUT OF STOCK": ("Out of stock", "danger", "Order now"),
    "SHORTAGE RISK": ("Shortage risk", "amber", "Below lead-time"),
    "REORDER NOW": ("Reorder now", "gold", "At reorder point"),
    "HEALTHY": ("Healthy", "green", "Covered for lead time"),
    "NO RECORDED DEMAND": ("No demand", "neutral", "Do not reorder"),
}
AVATAR_PALETTE = [
    ("#e8367d", "#000000"),
    ("#c21e56", "#ffffff"),
    ("#123e79", "#ffffff"),
    ("#8b5a2b", "#ffffff"),
    ("#f7a8c4", "#000000"),
    ("#d9a066", "#000000"),
]
SUGGESTIONS = [
    "Which products need restocking?",
    "What should I check after work today?",
    "Which products might run out before delivery?",
    "How much inventory value do I hold?",
]
FIELD_LABELS = {
    "product": "Product",
    "current_stock": "Stock",
    "avg_daily_sales": "Daily sales",
    "unit_cost": "Unit cost",
    "lead_time_days": "Lead time",
}

SVG_ICONS = {
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "box": '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
    "cart": '<circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/><path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "chevron": '<path d="m6 9 6 6 6-6"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    "spark": '<path d="m12 3 1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9Z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8Z"/>',
}

CSS = """
<style>
:root {
  /* Brand palette sampled from assets/logo.svg. */
  --fs-pink: #e8367d;
  --fs-pink-soft: #f7a8c4;
  --fs-pink-pale: #f9bfd5;
  --fs-deep-pink: #c21e56;
  --fs-navy: #123e79;
  --fs-brown: #8b5a2b;
  --fs-tan: #d9a066;

  --fs-ink: #000000;
  --fs-paper: #ffffff;
  --fs-blue: var(--fs-pink);
  --fs-red: var(--fs-deep-pink);
  --fs-lime: var(--fs-navy);
  --fs-yellow: var(--fs-tan);
  --fs-gold: var(--fs-pink-soft);
  --fs-gray: #f2f2f2;
  --fs-line: #000000;
  --fs-muted: #666666;
  --fs-teal: #000000;
  --fs-teal-deep: #000000;
  --fs-cream: #ffffff;
  --fs-card: #ffffff;
}
html, body, .stApp { font-family: Arial, "Helvetica Neue", Helvetica, sans-serif; }
.stApp :where(h1,h2,h3,h4,h5,h6,p,div,li,td,th,label,input,textarea,button,a) { font-family: inherit; }
html { -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
.stApp, [data-testid="stAppViewContainer"] { background: var(--fs-paper); }
[data-testid="stHeader"], [data-testid="stToolbar"], footer { display: none; }
.block-container { padding: 1.15rem 2.4rem 3rem 2.4rem; max-width: 1500px; margin: 0 auto; }

/* Sidebar */
section[data-testid="stSidebar"] {
  background: #000000;
  width: 252px !important;
  min-width: 252px !important;
  border-right: 1.5px solid #000000;
}
section[data-testid="stSidebar"] > div,
[data-testid="stSidebarContent"] { background: transparent; }
[data-testid="stSidebarContent"] { padding: 0 !important; }
[data-testid="stSidebarUserContent"] { padding: 0 10px 20px 10px; }
[data-testid="stSidebarHeader"] { padding: 0; height: 0; min-height: 0; }
[data-testid="stSidebarCollapseButton"] { display: none; }
.fs-brand { padding: 16px 8px 24px 8px; }
.fs-brand-name { color: #ffffff; font-size: 23px; font-weight: 900; letter-spacing: -0.8px; }
.fs-brand-logo {
  display: block; width: 100%; height: auto;
  background: #f7f8f7; padding: 8px 6px 2px;
}
.fs-logo { width: 34px; height: 34px; flex: 0 0 34px; }
section[data-testid="stSidebar"] .stButton { margin: 2px 0; }
section[data-testid="stSidebar"] .stButton > button {
  width: 100%;
  min-height: 46px;
  background: transparent;
  border: none;
  box-shadow: none;
  color: #ffffff;
  padding: 10px 14px;
  border-radius: 0;
  justify-content: flex-start;
  gap: 12px;
  text-align: left;
  text-transform: none;
  letter-spacing: normal;
  font-weight: 700;
  transition: background .18s ease-in-out, color .18s ease-in-out, transform .18s ease-in-out;
}
section[data-testid="stSidebar"] .stButton > button > div {
  justify-content: flex-start;
  text-align: left;
  width: auto;
  flex: 1 1 auto;
  min-width: 0;
}
section[data-testid="stSidebar"] .stButton > button p {
  text-align: left;
  text-transform: none;
  letter-spacing: normal;
}
section[data-testid="stSidebar"] .stButton > button:hover {
  background: #ffffff;
  color: #000000;
  transform: translateX(4px);
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background: var(--fs-blue);
  color: #000000;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
  background: #ffffff;
  color: #000000;
}
section[data-testid="stSidebar"] .stButton > button > span:first-child { margin-right: 0 !important; }
section[data-testid="stSidebar"] .stButton > button p { font-size: 15px; font-weight: 700; line-height: 1.2; }
section[data-testid="stSidebar"] .stButton > button[kind="primary"] p { font-weight: 900; }
section[data-testid="stSidebar"] .stButton > button [data-testid="stIconMaterial"] { font-size: 20px; color: inherit; }
.fs-side-status {
  margin-top: 20px; padding: 14px; border-radius: 0;
  background: #111111; border: 1px solid #333333;
  color: #b3b3b3; font-size: 12px; line-height: 1.5;
}
.fs-side-status strong {
  display: block; color: #ffffff; font-size: 12.5px; font-weight: 900;
  margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  letter-spacing: -0.1px;
}
.fs-side-note {
  color: #8a8a8a; font-size: 9.5px; font-weight: 700; margin-top: 8px;
  text-transform: uppercase; letter-spacing: .09em;
}
.fs-side-gap { height: 22px; }

/* Top bar */
.fs-topicons { display: flex; align-items: center; justify-content: flex-end; gap: 10px; padding-top: 0; }
[data-testid="stMarkdown"]:has(.fs-topicons) { height: 46px; display: flex; align-items: center; justify-content: flex-end; }
.fs-iconbtn {
  width: 44px; height: 44px; border-radius: 0; background: #ffffff;
  border: 1.5px solid #000000; display: flex; align-items: center;
  justify-content: center; color: #000000;
  transition: background .18s ease-in-out, color .18s ease-in-out, transform .18s ease-in-out;
}
.fs-iconbtn:hover { background: #000000; color: #ffffff; transform: translateY(-2px); }
.fs-iconbtn.active { background: var(--fs-blue); border-color: #000000; color: #000000; }
.fs-profile {
  display: flex; align-items: center; gap: 9px; background: #ffffff;
  border: 1.5px solid #000000; border-radius: 0;
  padding: 4px 12px 4px 4px; color: #000000; font-size: 12px;
  font-weight: 800; white-space: nowrap; text-transform: uppercase; letter-spacing: .04em;
  transition: transform .18s ease-in-out, box-shadow .18s ease-in-out;
}
.fs-profile:hover { transform: translate(-2px, -2px); box-shadow: 4px 4px 0 var(--fs-blue); }
.fs-avatar {
  width: 32px; height: 32px; border-radius: 0;
  background: var(--fs-blue); color: #000000;
  display: flex; align-items: center; justify-content: center;
  font-size: 10.5px; font-weight: 900; letter-spacing: .02em;
}
.fs-chevron { color: #000000; display: flex; }
.fs-top-icon { flex: 0 0 auto; }
[data-testid="stHorizontalBlock"]:has(.fs-top-icon) { align-items: center; gap: 10px; }
.st-key-topbar_row [data-testid="stColumn"] { align-items: center; justify-content: center; }
.st-key-topbar_row [data-testid="stColumn"]:has(.fs-profile) { align-items: flex-end; }
.st-key-theme_light [data-testid="stButton"] button,
.st-key-theme_dark [data-testid="stButton"] button {
  width: 44px !important; min-width: 44px !important; height: 44px !important;
  min-height: 44px !important; padding: 0 !important; border-radius: 0 !important;
  border: 1.5px solid var(--fs-line) !important;
  background: var(--fs-card) !important; color: var(--fs-ink) !important;
  box-shadow: none !important; transform: none !important;
  display: inline-flex !important; align-items: center !important;
  justify-content: center !important;
}
.st-key-theme_light [data-testid="stButton"] button p,
.st-key-theme_dark [data-testid="stButton"] button p { display: none !important; }
.st-key-theme_light [data-testid="stButton"] button [data-testid="stIconMaterial"],
.st-key-theme_dark [data-testid="stButton"] button [data-testid="stIconMaterial"] {
  color: inherit !important; font-size: 20px !important;
}
.st-key-theme_light [data-testid="stButton"] button[kind="primary"],
.st-key-theme_dark [data-testid="stButton"] button[kind="primary"] {
  background: var(--fs-blue) !important; color: #000000 !important;
  border-color: var(--fs-line) !important;
}
.st-key-theme_light [data-testid="stButton"] button:hover,
.st-key-theme_dark [data-testid="stButton"] button:hover {
  background: var(--fs-ink) !important; color: var(--fs-card) !important;
  transform: translateY(-2px) !important; box-shadow: none !important;
}
@media (max-width: 1350px) {
  .fs-iconbtn:nth-child(2), .fs-iconbtn:nth-child(4) { display: none; }
  .fs-profile { padding: 4px; gap: 0; }
  .fs-profile > span:not(.fs-avatar) { display: none; }
  .st-key-topbar_row [data-testid="stColumn"]:nth-child(1),
  .st-key-topbar_row [data-testid="stColumn"]:nth-child(2) {
    display: none;
  }
}

/* Search */
div[data-testid="stTextInput"] { position: relative; max-width: 520px; }
div[data-testid="stTextInput"] div[data-baseweb="input"] {
  background: #ffffff !important; border: 1.5px solid #000000 !important;
  border-radius: 0 !important; min-height: 46px; padding: 0 48px 0 16px;
  box-shadow: none !important;
  transition: box-shadow .18s ease-in-out, transform .18s ease-in-out;
}
div[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within {
  box-shadow: 4px 4px 0 var(--fs-blue); transform: translate(-1px, -1px);
}
div[data-testid="stTextInput"] div[data-baseweb="input"] > div { border: none !important; background: transparent !important; }
div[data-testid="stTextInput"] input { color: #000000; font-size: 13px; font-weight: 700; background: transparent !important; }
div[data-testid="stTextInput"] input::placeholder { color: #666666; font-weight: 700; }
div[data-testid="stTextInput"]::after {
  content: ""; position: absolute; right: 17px; top: 50%; width: 18px; height: 18px;
  transform: translateY(-50%);
  background: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="%23000000" stroke-width="2.2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>') no-repeat center/contain;
  opacity: 1; pointer-events: none;
}

/* Header */
.fs-page-title,
h1.fs-page-title {
  color: var(--fs-navy) !important; font-size: clamp(32px, 3.4vw, 56px);
  line-height: .98; font-weight: 900; letter-spacing: -0.04em;
  margin: 0 !important; padding: 0 !important;
  animation: fs-rise .45s cubic-bezier(.16,1,.3,1) backwards;
}
[data-testid="stHorizontalBlock"]:has(.fs-page-title) { margin-bottom: 10px; }
[data-testid="stMarkdown"]:has(.fs-page-title) [data-testid="stMarkdownContainer"],
[data-testid="stMarkdown"]:has(.fs-topicons) [data-testid="stMarkdownContainer"] {
  margin-bottom: 0 !important;
}
[data-testid="stPopover"] { height: fit-content !important; align-self: flex-start; }
[data-testid="stPopover"] > div[aria-haspopup="true"] { height: fit-content !important; display: flex; }
[data-testid="stPopoverButton"] {
  height: 44px !important; min-height: 44px !important; max-height: 44px !important;
  width: auto !important; align-self: flex-end !important;
  white-space: nowrap !important; display: inline-flex !important; gap: 6px !important;
  background: #ffffff !important; border: 1.5px solid #000000 !important;
  border-radius: 0 !important; color: #000000 !important;
  font-size: 11px !important; font-weight: 800 !important; box-shadow: none !important;
  padding: 0 12px !important; text-transform: uppercase; letter-spacing: .05em;
  transition: background .18s ease-in-out, color .18s ease-in-out, transform .18s ease-in-out, box-shadow .18s ease-in-out;
}
[data-testid="stPopoverButton"] p {
  color: inherit !important; font-size: 11px !important;
  font-weight: 800 !important; white-space: nowrap !important;
  text-transform: uppercase !important; letter-spacing: .05em !important;
}
[data-testid="stPopoverButton"]:hover {
  border-color: #000000 !important; background: #000000 !important;
  color: #ffffff !important; transform: translate(-2px, -2px);
  box-shadow: 4px 4px 0 var(--fs-blue);
}
[data-testid="stPopoverButton"]:hover p { color: #ffffff !important; }
[data-testid="stPopoverButton"] [data-testid="stIconMaterial"] { font-size: 18px !important; color: inherit !important; }
[data-testid="stPopoverButton"]:hover [data-testid="stIconMaterial"] { color: #ffffff !important; }
[data-baseweb="popover"] > div {
  border-radius: 0 !important; border: 1.5px solid #000000 !important;
  transform-origin: top center;
  animation: fs-pop-in .2s cubic-bezier(.16,1,.3,1) backwards;
}
[data-testid="stRadio"] label p { font-weight: 700 !important; font-size: 12.5px !important; }
[data-testid="stMultiSelect"] [data-baseweb="tag"] { border-radius: 0 !important; background: #000000 !important; font-weight: 700; }
[data-testid="stMultiSelect"] [data-baseweb="tag"] span { color: #ffffff !important; }
[data-testid="stHorizontalBlock"]:has(.fs-page-title) > [data-testid="stColumn"]:first-child {
  flex: 1 1 auto !important; width: auto !important; min-width: 0 !important;
}
[data-testid="stHorizontalBlock"]:has(.fs-page-title) > [data-testid="stColumn"]:not(:first-child) {
  flex: 0 0 auto !important; width: auto !important; min-width: 0 !important;
}
@media (max-width: 1100px) {
  [data-testid="stHorizontalBlock"]:has(.fs-page-title) {
    flex-wrap: wrap; row-gap: 12px; justify-content: flex-end;
  }
  [data-testid="stHorizontalBlock"]:has(.fs-page-title) > [data-testid="stColumn"]:first-child {
    flex: 1 0 100% !important; width: 100% !important; min-width: 100% !important;
  }
}

/* Cards */
.fs-card {
  background: #ffffff; border: 1.5px solid #000000; border-radius: 0;
  padding: 20px 22px; min-width: 0;
  transition: transform .22s ease-in-out, box-shadow .22s ease-in-out;
}
.fs-card:hover { transform: translate(-3px, -3px); box-shadow: 7px 7px 0 var(--fs-blue); }
.fs-card-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin-bottom: 16px;
}
.fs-card-head h3 { margin: 0; color: #000000; font-size: 15px; font-weight: 800; letter-spacing: -0.02em; }
.fs-card-tools { display: flex; align-items: center; gap: 10px; }
.fs-card-note { color: #666666; font-size: 9.5px; font-weight: 800; text-transform: uppercase; letter-spacing: .08em; }
.fs-dots { color: #000000; letter-spacing: 2px; font-size: 18px; line-height: 1; font-weight: 900; }

/* Dashboard grid */
.fs-dash {
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
  grid-template-rows: auto auto; gap: 24px;
}
.fs-hero { grid-column: 1; grid-row: 1; }
.fs-bars-card { grid-column: 2; grid-row: 1; }
.fs-gauge-card { grid-column: 3; grid-row: 1; }
.fs-overview { grid-column: 1; grid-row: 2; }
.fs-priorities { grid-column: 2 / span 2; grid-row: 2; }
.fs-dash > .fs-card { animation: fs-rise .5s cubic-bezier(.16,1,.3,1) backwards; }
.fs-dash > .fs-card:nth-child(2) { animation-delay: .06s; }
.fs-dash > .fs-card:nth-child(3) { animation-delay: .12s; }
.fs-dash > .fs-card:nth-child(4) { animation-delay: .18s; }
.fs-dash > .fs-card:nth-child(5) { animation-delay: .24s; }
@media (max-width: 1150px) {
  .fs-dash { grid-template-columns: 1fr; }
  .fs-hero, .fs-bars-card, .fs-gauge-card, .fs-overview, .fs-priorities {
    grid-column: auto; grid-row: auto;
  }
}

/* Hero */
.fs-hero {
  position: relative; overflow: hidden; min-height: 250px;
  background: #000000; border-color: #000000;
}
.fs-hero::before {
  content: ""; position: absolute; width: 250px; height: 250px; right: -78px; bottom: -96px;
  border-radius: 50%; background: var(--fs-blue);
}
.fs-hero::after {
  content: ""; position: absolute; left: 0; top: 0;
  width: 6px; height: 100%; background: var(--fs-red);
}
.fs-hero-top {
  position: relative; z-index: 1; display: flex; align-items: flex-start;
  justify-content: space-between; flex-wrap: wrap; gap: 12px; row-gap: 10px;
}
.fs-hero-value { color: #ffffff; font-size: clamp(32px, 3vw, 42px); font-weight: 900; letter-spacing: -0.035em; line-height: 1; overflow-wrap: anywhere; }
.fs-hero-label { position: relative; z-index: 1; color: rgba(255,255,255,.68); font-size: 10px; font-weight: 700; margin-top: 8px; text-transform: uppercase; letter-spacing: .1em; }
.fs-hero-pills { display: flex; flex-direction: column; align-items: flex-end; gap: 7px; }
.fs-pill-soft {
  background: transparent; border: 1px solid rgba(255,255,255,.55);
  border-radius: 0; padding: 5px 9px; font-size: 9px; font-weight: 800;
  color: #ffffff; white-space: nowrap; text-transform: uppercase; letter-spacing: .07em;
}
.fs-hero-bottom {
  position: absolute; z-index: 1; left: 22px; bottom: 20px;
  display: flex; align-items: center; gap: 10px;
}
.fs-badge-dark {
  background: var(--fs-blue); color: #000000; border-radius: 0;
  padding: 6px 10px; font-size: 9px; font-weight: 900; white-space: nowrap;
  text-transform: uppercase; letter-spacing: .07em;
}
.fs-hero-sub { color: rgba(255,255,255,.62); font-size: 10px; font-weight: 600; }

/* Bars */
.fs-bars {
  height: 190px; display: flex; align-items: flex-end; justify-content: space-between;
  gap: 8px; padding: 6px 2px 0;
}
.fs-bar-group {
  flex: 1; height: 100%; display: flex; flex-direction: column;
  align-items: center; justify-content: flex-end; gap: 8px; min-width: 0;
}
.fs-bar-pair { height: 100%; width: 100%; display: flex; align-items: flex-end; justify-content: center; gap: 5px; }
.fs-bar { width: 12px; border-radius: 0; min-height: 7px; transform-origin: bottom center; animation: fs-grow .8s cubic-bezier(.16,1,.3,1) backwards; }
.fs-bar.teal { background: #000000; }
.fs-bar.gold { background: var(--fs-blue); }
.fs-bar-group:nth-child(2) .fs-bar { animation-delay: .05s; }
.fs-bar-group:nth-child(3) .fs-bar { animation-delay: .1s; }
.fs-bar-group:nth-child(4) .fs-bar { animation-delay: .15s; }
.fs-bar-group:nth-child(5) .fs-bar { animation-delay: .2s; }
.fs-bar-group:nth-child(6) .fs-bar { animation-delay: .25s; }
.fs-bar-label { color: #000000; font-size: 9px; font-weight: 800; white-space: nowrap; letter-spacing: .03em; }
.fs-legend { display: flex; gap: 14px; margin-top: 12px; color: #666666; font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .07em; }
.fs-legend i { display: inline-block; width: 9px; height: 9px; border-radius: 0; margin-right: 5px; vertical-align: -1px; }
.fs-legend .teal { background: #000000; }
.fs-legend .gold { background: var(--fs-blue); }

/* Gauge */
.fs-gauge-wrap { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 200px; }
.fs-gauge-svg { width: 100%; max-width: 230px; height: auto; overflow: visible; animation: fs-pop .65s .12s cubic-bezier(.16,1,.3,1) backwards; }
.fs-gauge-value-text { font-size: 27px; font-weight: 900; fill: #000000; letter-spacing: -1px; }
.fs-gauge-label-text { font-size: 8px; fill: #666666; font-weight: 700; letter-spacing: .03em; }
.fs-gauge-pill { margin-top: 2px; }

/* KPI tiles */
.fs-overview { display: flex; flex-direction: column; }
.fs-mini-grid { flex: 1; display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; gap: 12px; }
.fs-mini {
  border: 1.5px solid #000000; border-radius: 0; padding: 13px 14px 12px;
  display: flex; flex-direction: column; justify-content: space-between; min-height: 112px;
  background: #ffffff;
  transition: background .2s ease-in-out, transform .2s ease-in-out, box-shadow .2s ease-in-out;
}
.fs-mini:hover { background: var(--fs-blue); transform: translate(-3px, -3px); box-shadow: 5px 5px 0 #000000; }
.fs-mini-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.fs-mini-icon {
  width: 36px; height: 36px; border-radius: 0; background: #000000;
  color: #ffffff; display: flex; align-items: center; justify-content: center;
}
.fs-mini-badge { border-radius: 0; padding: 3px 7px; font-size: 8.5px; font-weight: 900; white-space: nowrap; text-transform: uppercase; letter-spacing: .06em; }
.fs-mini-badge.green { background: var(--fs-lime); color: #ffffff; }
.fs-mini-badge.red { background: var(--fs-red); color: #ffffff; }
.fs-mini-badge.amber { background: var(--fs-yellow); color: #000000; }
.fs-mini-badge.neutral { background: #000000; color: #ffffff; }
.fs-mini-value { color: #000000; font-size: 27px; font-weight: 900; line-height: 1; letter-spacing: -0.04em; }
.fs-mini-label { color: #666666; font-size: 9.5px; font-weight: 800; margin-top: 5px; text-transform: uppercase; letter-spacing: .06em; }

/* Priority list */
.fs-list { display: flex; flex-direction: column; }
.fs-row {
  display: grid; grid-template-columns: minmax(0, 1.8fr) 1.15fr .62fr .78fr;
  gap: 10px; align-items: center; padding: 12px 0; border-top: 1px solid #e5e5e5;
  transition: background .18s ease-in-out, padding-left .18s ease-in-out, box-shadow .18s ease-in-out;
  animation: fs-row-in .32s cubic-bezier(.16,1,.3,1) backwards;
}
.fs-row:nth-child(2) { animation-delay: .03s; }
.fs-row:nth-child(3) { animation-delay: .06s; }
.fs-row:nth-child(4) { animation-delay: .09s; }
.fs-row:nth-child(5) { animation-delay: .12s; }
.fs-row:nth-child(6) { animation-delay: .15s; }
.fs-row:nth-child(7) { animation-delay: .18s; }
.fs-row:nth-child(8) { animation-delay: .21s; }
.fs-row:hover { background: var(--fs-gray); padding-left: 10px; box-shadow: inset 4px 0 0 var(--fs-blue); }
.fs-row:first-child { border-top: none; padding-top: 0; }
.fs-row:last-child { padding-bottom: 0; }
.fs-row-main { display: flex; align-items: center; gap: 11px; min-width: 0; }
.fs-prod-icon {
  border-radius: 0; display: flex; align-items: center; justify-content: center;
  font-size: 11.5px; font-weight: 900; flex: 0 0 auto; letter-spacing: .01em;
}
.fs-row-title { color: #000000; font-size: 12.5px; font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.fs-row-meta { color: #666666; font-size: 9.5px; font-weight: 600; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.fs-status { display: inline-block; border-radius: 0; padding: 3px 7px; font-size: 8.5px; font-weight: 900; white-space: nowrap; text-transform: uppercase; letter-spacing: .05em; }
.fs-status.danger { background: var(--fs-red); color: #ffffff; }
.fs-status.amber { background: var(--fs-yellow); color: #000000; }
.fs-status.gold { background: var(--fs-gold); color: #000000; }
.fs-status.green { background: var(--fs-lime); color: #ffffff; }
.fs-status.neutral { background: #e5e5e5; color: #000000; }
.fs-row-strong { color: #000000; font-size: 12.5px; font-weight: 900; white-space: nowrap; letter-spacing: -0.01em; }
.fs-row-col { min-width: 0; }
.fs-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  text-align: center; min-height: 180px; color: #666666; font-size: 12px; font-weight: 600; gap: 8px;
}
.fs-empty-icon {
  width: 48px; height: 48px; border-radius: 0; background: var(--fs-blue);
  display: flex; align-items: center; justify-content: center; color: #000000;
}

/* Table */
.fs-table-wrap { max-height: 640px; overflow: auto; border-radius: 0; }
.fs-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 11.5px; }
.fs-table th {
  position: sticky; top: 0; background: #ffffff; text-align: left; color: #000000;
  font-size: 9px; text-transform: uppercase; letter-spacing: .08em; font-weight: 900;
  padding: 0 10px 10px; border-bottom: 1.5px solid #000000; white-space: nowrap; z-index: 1;
}
.fs-table td { padding: 11px 10px; border-bottom: 1px solid #e5e5e5; color: #000000; white-space: nowrap; font-weight: 600; }
.fs-table tr:last-child td { border-bottom: none; }
.fs-table tbody tr {
  transition: background .15s ease-in-out;
  animation: fs-fade-in .3s cubic-bezier(.16,1,.3,1) backwards;
}
.fs-table tbody tr:nth-child(2) { animation-delay: .03s; }
.fs-table tbody tr:nth-child(3) { animation-delay: .06s; }
.fs-table tbody tr:nth-child(4) { animation-delay: .09s; }
.fs-table tbody tr:nth-child(5) { animation-delay: .12s; }
.fs-table tbody tr:nth-child(6) { animation-delay: .15s; }
.fs-table tbody tr:nth-child(7) { animation-delay: .18s; }
.fs-table tbody tr:nth-child(8) { animation-delay: .21s; }
.fs-table tbody tr:nth-child(9) { animation-delay: .24s; }
.fs-table tbody tr:nth-child(10) { animation-delay: .27s; }
.fs-table tbody tr:hover td { background: var(--fs-gray); }
.fs-table tbody tr:hover td:first-child { box-shadow: inset 4px 0 0 var(--fs-blue); }
.fs-table .num { font-variant-numeric: tabular-nums; }
.fs-table .prod { display: flex; align-items: center; gap: 9px; font-weight: 800; }
.fs-table .prod .fs-prod-icon { width: 32px; height: 32px; font-size: 10px; }
.fs-table .muted { color: #666666; }

/* Streamlit widgets */
div[data-testid="stButton"] > button,
div[data-testid="stDownloadButton"] > button {
  border-radius: 0; min-height: 44px; font-size: 11.5px; font-weight: 800;
  border: 1.5px solid #000000; background: #ffffff; color: #000000; box-shadow: none;
  text-transform: uppercase; letter-spacing: .05em;
  transition: background .18s ease-in-out, color .18s ease-in-out, transform .18s ease-in-out, box-shadow .18s ease-in-out;
}
div[data-testid="stButton"] > button:active,
div[data-testid="stDownloadButton"] > button:active,
[data-testid="stPopoverButton"]:active,
[data-testid="stFileUploaderDropzone"] button:active,
[data-testid="stChatInput"] button:active,
section[data-testid="stSidebar"] .stButton > button:active {
  transform: scale(.97) !important;
  transition-duration: .12s !important;
}
div[data-testid="stButton"] > button:hover,
div[data-testid="stDownloadButton"] > button:hover {
  background: #000000; color: #ffffff; border-color: #000000;
  transform: translate(-2px, -2px); box-shadow: 4px 4px 0 var(--fs-blue);
}
div[data-testid="stButton"] > button[kind="primary"] {
  background: #000000; border-color: #000000; color: #ffffff;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
  background: var(--fs-blue); border-color: #000000; color: #000000;
  transform: translate(-2px, -2px); box-shadow: 4px 4px 0 #000000;
}
div[data-testid="stButton"] > button:disabled,
div[data-testid="stDownloadButton"] > button:disabled { opacity: .35; }
[data-testid="stDownloadButton"] > button { white-space: nowrap; padding-left: 10px; padding-right: 10px; }
@media (max-width: 1100px) {
  [data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stButton"] > button,
  [data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stDownloadButton"] > button,
  .st-key-import_card div[data-testid="stButton"] > button,
  .st-key-import_card div[data-testid="stDownloadButton"] > button {
    font-size: 11px; letter-spacing: .02em; padding-left: 8px; padding-right: 8px;
  }
  .st-key-import_card div[data-testid="stButton"] > button p,
  .st-key-import_card div[data-testid="stDownloadButton"] > button p {
    font-size: 11px !important; line-height: 1.2 !important; letter-spacing: .02em !important;
  }
}
div[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stVerticalBlock"].st-key-import_card {
  background: #ffffff; border: 1.5px solid #000000 !important; border-radius: 0 !important;
}
[data-testid="stFileUploader"] { background: var(--fs-gray); border: 1.5px dashed #000000; border-radius: 0; padding: 10px 12px; }
[data-testid="stFileUploader"] section { border: none; background: transparent; }
[data-testid="stFileUploaderDropzone"] { background: transparent; border: none; }
[data-testid="stFileUploader"] label { color: #000000; font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: .06em; }
[data-testid="stFileUploaderDropzone"] button { border-radius: 0 !important; border: 1.5px solid #000000 !important; font-weight: 800 !important; }
[data-testid="stAlert"] { border-radius: 0; border: 1.5px solid #000000; }
.fs-flash {
  background: var(--fs-lime); color: #ffffff; border: 1.5px solid #000000;
  border-radius: 0; padding: 11px 16px; font-size: 12px; font-weight: 800;
  margin-bottom: 14px; animation: fs-confirm .45s cubic-bezier(.16,1,.3,1) backwards;
}
.fs-flash.error { background: var(--fs-red); color: #ffffff; border-color: #000000; }
.fs-footnote { color: #666666; font-size: 10px; font-weight: 600; margin-top: 16px; letter-spacing: .01em; }

/* Chat */
[data-testid="stChatMessage"] {
  background: #ffffff; border: 1.5px solid #000000; border-radius: 0;
  padding: 12px 16px; margin-bottom: 10px;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background: #000000; border-color: #000000; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) li { color: #ffffff; }
[data-testid="stChatMessageAvatarUser"] { background: var(--fs-blue) !important; color: #000000 !important; border-radius: 0 !important; }
[data-testid="stChatMessageAvatarAssistant"] { background: #000000 !important; color: #ffffff !important; border-radius: 0 !important; }
[data-testid="stChatInput"] { background: #ffffff; border: 1.5px solid #000000; border-radius: 0; transition: box-shadow .18s ease-in-out; }
[data-testid="stChatInput"]:focus-within { box-shadow: 4px 4px 0 var(--fs-blue); }
[data-testid="stChatInput"] textarea { font-size: 13px; color: #000000; font-weight: 600; }
.fs-chat-head { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.fs-chat-avatar {
  width: 44px; height: 44px; border-radius: 0; background: var(--fs-blue); color: #000000;
  display: flex; align-items: center; justify-content: center; flex: 0 0 44px;
}
.fs-chat-head h3 { margin: 0; color: #000000; font-size: 19px; font-weight: 900; letter-spacing: -0.02em; }
.fs-chat-head p { margin: 3px 0 0; color: #666666; font-size: 11px; font-weight: 600; }
.fs-suggest-label { color: #666666; font-size: 9.5px; text-transform: uppercase; letter-spacing: .1em; font-weight: 900; margin: 14px 0 8px; }

/* Empty state */
.fs-empty-hero { text-align: center; padding: 54px 30px; }
.fs-empty-hero h2 { color: #000000; font-size: clamp(32px, 4vw, 52px); font-weight: 900; letter-spacing: -0.045em; line-height: 1; margin: 18px 0 10px; }
.fs-empty-hero p { color: #444444; font-size: 13px; font-weight: 600; max-width: 520px; margin: 0 auto; line-height: 1.6; }
.fs-empty-hero .fs-empty-icon { width: 62px; height: 62px; margin: 0 auto; background: var(--fs-blue); }

/* Help */
.fs-help-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; }
.fs-help-wide { grid-column: 1 / -1; }
@media (max-width: 1000px) { .fs-help-grid { grid-template-columns: 1fr; } }
.fs-help-list { margin: 0; padding-left: 18px; color: #333333; font-size: 12.5px; font-weight: 600; line-height: 1.7; }
.fs-help-list li { margin-bottom: 7px; }
.fs-help-list li::marker { color: var(--fs-blue); }
.fs-help-card h3 { font-size: 15px; }

/* Motion */
@keyframes fs-rise {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes fs-grow {
  from { transform: scaleY(0); }
  to { transform: scaleY(1); }
}
@keyframes fs-pop {
  from { opacity: 0; transform: scale(.94); }
  to { opacity: 1; transform: scale(1); }
}
@keyframes fs-row-in {
  from { transform: translateY(6px); }
  to { transform: translateY(0); }
}
@keyframes fs-fade-in {
  from { transform: translateY(4px); }
  to { transform: translateY(0); }
}
@keyframes fs-pop-in {
  from { opacity: 0; transform: scale(.95); }
  to { opacity: 1; transform: scale(1); }
}
@keyframes fs-confirm {
  0% { opacity: 0; transform: scale(.96); }
  55% { opacity: 1; transform: scale(1.02); }
  100% { opacity: 1; transform: scale(1); }
}
@media (prefers-reduced-motion: reduce) {
  .fs-dash > .fs-card, .fs-bar, .fs-gauge-svg, .fs-row,
  .fs-table tbody tr, [data-baseweb="popover"] > div,
  .fs-flash, .fs-page-title { animation: none !important; }
  * { transition: none !important; }
}
</style>
"""

DARK_CSS = """
<style>
/* Night mode: invert the light palette and rotate hues back so the brand blue,
   pink, red, lime, and yellow stay recognisable. The sidebar applies the same
   filter again so its original black styling is preserved. */
html { filter: invert(1) hue-rotate(180deg); background: #ffffff; }
section[data-testid="stSidebar"] { filter: invert(1) hue-rotate(180deg); }
</style>
"""


def _logo_svg(name: str, css_class: str) -> str:
    """Inline a logo asset so it inherits Streamlit's layout without extra requests."""
    try:
        markup = (ASSETS_DIR / name).read_text(encoding="utf-8").strip()
    except OSError:
        logging.exception("Could not read logo asset %s", name)
        return ""
    return markup.replace("<svg ", f'<svg class="{css_class}" ', 1)


def _icon(name: str, size: int = 18) -> str:
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        f'stroke-linejoin="round">{SVG_ICONS[name]}</svg>'
    )


def _h(value: Any) -> str:
    return html.escape(str(value), quote=True)


_INTER_TAG_WHITESPACE = re.compile(r">\s+<")


def _minify_html(markup: str) -> str:
    """Collapse whitespace between tags so Markdown never treats markup as code."""
    return _INTER_TAG_WHITESPACE.sub("><", markup.strip())


def _render_html(markup: str) -> None:
    st.markdown(_minify_html(markup), unsafe_allow_html=True)


def _render_sidebar_html(markup: str) -> None:
    st.sidebar.markdown(_minify_html(markup), unsafe_allow_html=True)


def _money(value: Decimal | float | int | None) -> str:
    if value is None:
        return "—"
    return f"R{float(value):,.2f}"


def _days(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f} d"


def _now_johannesburg() -> datetime:
    return datetime.now(JOHANNESBURG)


def _format_timestamp(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%d %b %Y, %H:%M %Z")


def _read_sample_file() -> bytes | None:
    try:
        return SAMPLE_PATH.read_bytes()
    except OSError:
        logging.exception("Could not read the sample inventory file")
        return None


def _set_active_inventory(
    file_data: bytes,
    display_name: str,
    sheet_name: str | None = None,
    column_mapping: dict[str, Any] | None = None,
) -> None:
    inventory = validate_inventory_file(
        file_data, display_name, sheet_name, column_mapping
    )
    mapping_key = "|".join(
        f"{field}={column_mapping.get(field, '')}"
        for field in FIELD_LABELS
    ) if column_mapping else ""
    fingerprint_source = (
        file_data
        + b"\0"
        + (sheet_name or "").encode("utf-8")
        + b"\0"
        + mapping_key.encode("utf-8")
    )
    fingerprint = hashlib.sha256(fingerprint_source).hexdigest()
    if fingerprint != st.session_state.get("dataset_id"):
        st.session_state.chat_messages = []
    timestamp = _now_johannesburg()
    st.session_state.inventory = inventory
    st.session_state.analysis = analyze_inventory(
        inventory, timestamp.isoformat(timespec="seconds")
    )
    st.session_state.uploaded_at = timestamp
    st.session_state.dataset_id = fingerprint
    st.session_state.source_name = display_name
    st.session_state.column_mapping = inventory.attrs.get("column_mapping") or {}
    st.session_state.ignored_columns = inventory.attrs.get("ignored_columns") or []
    st.session_state.worksheet_name = inventory.attrs.get("sheet_name")
    st.session_state.skipped_total_rows = (
        inventory.attrs.get("skipped_total_rows") or []
    )


def _activate_inventory(
    file_data: bytes,
    display_name: str,
    message: str,
    sheet_name: str | None = None,
    column_mapping: dict[str, Any] | None = None,
) -> None:
    try:
        _set_active_inventory(file_data, display_name, sheet_name, column_mapping)
    except InventoryValidationError as exc:
        st.session_state.flash_error = str(exc)
    else:
        st.session_state.flash = message
        st.session_state.page = "Dashboard"
        st.session_state.pending_mapping = None
    st.rerun()


def _avatar(name: str, size: int = 40) -> str:
    digest = hashlib.md5(name.encode("utf-8")).hexdigest()
    background, foreground = AVATAR_PALETTE[int(digest[:2], 16) % len(AVATAR_PALETTE)]
    initials = "".join(part[0] for part in name.split()[:2]).upper() or "?"
    return (
        f'<div class="fs-prod-icon" style="width:{size}px;height:{size}px;'
        f'background:{background};color:{foreground}">{_h(initials)}</div>'
    )


def _status_badge(status: str) -> str:
    label, css_class, _ = STATUS_META.get(status, (status.title(), "neutral", ""))
    return f'<span class="fs-status {css_class}">{_h(label)}</span>'


def _render_topbar() -> None:
    with st.container(key="topbar_row"):
        bell_col, calendar_col, light_col, dark_col, profile_col = st.columns(
            [0.5, 0.5, 0.5, 0.5, 1.9], gap="small", vertical_alignment="center"
        )
        with bell_col:
            _render_html(f'<div class="fs-iconbtn fs-top-icon">{_icon("bell")}</div>')
        with calendar_col:
            _render_html(f'<div class="fs-iconbtn fs-top-icon">{_icon("calendar")}</div>')
        theme = st.session_state.get("theme", "light")
        with light_col:
            if st.button(
                "",
                icon=":material/light_mode:",
                key="theme_light",
                type="primary" if theme == "light" else "secondary",
                help="Switch to light mode",
                width="stretch",
            ):
                st.session_state.theme = "light"
                st.rerun()
        with dark_col:
            if st.button(
                "",
                icon=":material/dark_mode:",
                key="theme_dark",
                type="primary" if theme == "dark" else "secondary",
                help="Switch to night mode",
                width="stretch",
            ):
                st.session_state.theme = "dark"
                st.rerun()
        with profile_col:
            _render_html(
                f"""
                <div class="fs-profile">
                  <div class="fs-avatar">SO</div>
                  <span>Store owner</span>
                  <span class="fs-chevron">{_icon("chevron", 14)}</span>
                </div>
                """
            )


def _sidebar_button(label: str, page: str, icon: str) -> None:
    active = st.session_state.page == page
    if st.sidebar.button(
        label,
        icon=f":material/{icon}:",
        type="primary" if active else "secondary",
        width="stretch",
        key=f"nav_{page.lower().replace(' ', '_')}",
    ):
        st.session_state.page = page
        st.rerun()


def _render_sidebar() -> None:
    brand_logo = _logo_svg("logo.svg", "fs-brand-logo")
    if not brand_logo:
        brand_logo = '<span class="fs-brand-name">FullShelf</span>'
    _render_sidebar_html(
        f"""
        <div class="fs-brand">
          {brand_logo}
        </div>
        """
    )
    for label, icon in NAV_ITEMS:
        _sidebar_button(label, label, icon)

    source = st.session_state.source_name or "No inventory loaded"
    uploaded = _format_timestamp(st.session_state.uploaded_at)
    _render_sidebar_html(
        f"""
        <div class="fs-side-status">
          <strong>{_h(source)}</strong>
          <div>{_h(uploaded)}</div>
          <div class="fs-side-note">Session-only · not saved</div>
        </div>
        <div class="fs-side-gap"></div>
        """
    )
    _sidebar_button("Help Center", "Help Center", "help")


def _render_page_header(controls: bool) -> tuple[str, list[str]]:
    page = st.session_state.page
    if controls:
        title_col, sort_col, filter_col = st.columns(
            [3, 1, 1], vertical_alignment="center"
        )
        with title_col:
            st.markdown(f'<h1 class="fs-page-title">{_h(page)}</h1>', unsafe_allow_html=True)
        with sort_col:
            with st.popover("Sort by", icon=":material/swap_vert:"):
                st.radio(
                    "Sort by",
                    SORT_OPTIONS,
                    key="sort_by",
                    label_visibility="collapsed",
                )
        with filter_col:
            selected = st.session_state.get("status_filter", STATUS_OPTIONS)
            with st.popover(
                f"Filter by ({len(selected)})",
                icon=":material/filter_list:",
            ):
                st.multiselect(
                    "Status",
                    STATUS_OPTIONS,
                    default=STATUS_OPTIONS,
                    key="status_filter",
                    label_visibility="collapsed",
                )
    else:
        st.markdown(f'<h1 class="fs-page-title">{_h(page)}</h1>', unsafe_allow_html=True)

    sort_by = st.session_state.get("sort_by", "Urgency")
    selected_statuses = list(st.session_state.get("status_filter", STATUS_OPTIONS))
    return sort_by, selected_statuses


def _filter_and_sort(
    products: list[dict],
    search_query: str,
    selected_statuses: list[str],
    sort_by: str,
) -> list[dict]:
    query = search_query.strip().casefold()
    allowed = {
        status
        for status, label in STATUS_LABELS.items()
        if label in selected_statuses
    }
    filtered = [
        product
        for product in products
        if (not query or query in product["product"].casefold())
        and product["status"] in allowed
    ]
    if sort_by == "Name":
        filtered.sort(key=lambda product: product["product"].casefold())
    elif sort_by == "Inventory value":
        filtered.sort(key=lambda product: product["inventory_value"], reverse=True)
    elif sort_by == "Coverage":
        filtered.sort(
            key=lambda product: (
                product["stock_coverage_days"] is None,
                product["stock_coverage_days"] or 0,
            )
        )
    return filtered


def _short_label(name: str) -> str:
    clean = "".join(character for character in name if character.isalnum())
    return (clean[:5] or "?").upper()


def _chart_products(products: list[dict], limit: int = 6) -> list[dict]:
    if len(products) <= limit:
        return products
    attention = [p for p in products if p["status"] in ATTENTION_STATUSES]
    rest = [p for p in products if p["status"] not in ATTENTION_STATUSES]
    return (attention + rest)[:limit]


def _hero_card(summary: dict) -> str:
    attention = (
        summary["out_of_stock_count"]
        + summary["shortage_risk_count"]
        + summary["reorder_now_count"]
    )
    average = summary.get("average_stock_coverage_days")
    average_text = (
        f"Average cover {average:.1f} days"
        if average is not None
        else "Coverage not estimable"
    )
    return f"""
    <div class="fs-card fs-hero">
      <div class="fs-hero-top">
        <div>
          <div class="fs-hero-value">{_money(summary['total_inventory_value'])}</div>
          <div class="fs-hero-label">Inventory value at cost</div>
        </div>
        <div class="fs-hero-pills">
          <span class="fs-pill-soft">{summary['total_stock_units']:,} units</span>
          <span class="fs-pill-soft">{attention} at risk</span>
        </div>
      </div>
      <div class="fs-hero-bottom">
        <span class="fs-badge-dark">{summary['total_products']} products</span>
        <span class="fs-hero-sub">{_h(average_text)}</span>
      </div>
    </div>
    """


def _bar_chart_card(products: list[dict]) -> str:
    selected = _chart_products(products)
    if not selected:
        return f"""
        <div class="fs-card fs-bars-card">
          <div class="fs-card-head"><h3>Stock Coverage</h3><span class="fs-dots">•••</span></div>
          <div class="fs-empty"><div class="fs-empty-icon">{_icon("search", 22)}</div>No products match this view.</div>
        </div>
        """
    max_days = max(
        [1.0]
        + [float(product["lead_time_days"]) for product in selected]
        + [float(product["stock_coverage_days"] or 0) for product in selected]
    )
    groups = []
    for product in selected:
        coverage = float(product["stock_coverage_days"] or 0)
        coverage_height = max(7, round(coverage / max_days * 100))
        lead_height = max(7, round(float(product["lead_time_days"]) / max_days * 100))
        tip = (
            f"{product['product']}: {coverage:.1f} days cover vs "
            f"{product['lead_time_days']} day lead time"
        )
        groups.append(
            f"""
            <div class="fs-bar-group" title="{_h(tip)}">
              <div class="fs-bar-pair">
                <div class="fs-bar teal" style="height:{coverage_height}%"></div>
                <div class="fs-bar gold" style="height:{lead_height}%"></div>
              </div>
              <span class="fs-bar-label">{_h(_short_label(product['product']))}</span>
            </div>
            """
        )
    return f"""
    <div class="fs-card fs-bars-card">
      <div class="fs-card-head"><h3>Stock Coverage</h3><span class="fs-dots">•••</span></div>
      <div class="fs-bars">{''.join(groups)}</div>
      <div class="fs-legend">
        <span><i class="teal"></i>Coverage</span>
        <span><i class="gold"></i>Lead time</span>
      </div>
    </div>
    """


def _gauge_card(summary: dict) -> str:
    total = summary["total_products"]
    attention = (
        summary["out_of_stock_count"]
        + summary["shortage_risk_count"]
        + summary["reorder_now_count"]
    )
    no_risk = max(total - attention, 0)
    percentage = round(no_risk / total * 100) if total else 0
    segments = 30
    filled = round(percentage / 100 * segments)
    ticks = []
    for index in range(segments):
        angle = math.pi - (index / (segments - 1)) * math.pi
        x1 = 110 + 76 * math.cos(angle)
        y1 = 106 - 76 * math.sin(angle)
        x2 = 110 + 90 * math.cos(angle)
        y2 = 106 - 90 * math.sin(angle)
        color = "#e8367d" if index < filled else "#e5e5e5"
        ticks.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="8" stroke-linecap="round"/>'
        )
    return f"""
    <div class="fs-card fs-gauge-card">
      <div class="fs-card-head"><h3>Inventory Health</h3><span class="fs-dots">•••</span></div>
      <div class="fs-gauge-wrap">
        <svg class="fs-gauge-svg" viewBox="0 0 220 128" role="img" aria-label="{percentage}% without stockout risk">
          {''.join(ticks)}
          <text x="110" y="82" text-anchor="middle" class="fs-gauge-value-text">{percentage}%</text>
          <text x="110" y="98" text-anchor="middle" class="fs-gauge-label-text">{no_risk} of {total} products</text>
          <text x="110" y="109" text-anchor="middle" class="fs-gauge-label-text">without stockout risk</text>
        </svg>
        <span class="fs-mini-badge amber fs-gauge-pill">{attention} at risk</span>
      </div>
    </div>
    """


def _overview_card(summary: dict) -> str:
    out_of_stock = summary["out_of_stock_count"]
    shortage = summary["shortage_risk_count"]
    return f"""
    <div class="fs-card fs-overview">
      <div class="fs-card-head"><h3>Inventory Overview</h3><span class="fs-dots">•••</span></div>
      <div class="fs-mini-grid">
        <div class="fs-mini">
          <div class="fs-mini-top">
            <span class="fs-mini-icon">{_icon("grid", 18)}</span>
            <span class="fs-mini-badge green">Current</span>
          </div>
          <div>
            <div class="fs-mini-value">{summary['total_products']:,}</div>
            <div class="fs-mini-label">Products tracked</div>
          </div>
        </div>
        <div class="fs-mini">
          <div class="fs-mini-top">
            <span class="fs-mini-icon">{_icon("box", 18)}</span>
            <span class="fs-mini-badge neutral">At cost</span>
          </div>
          <div>
            <div class="fs-mini-value">{summary['total_stock_units']:,}</div>
            <div class="fs-mini-label">Units on hand</div>
          </div>
        </div>
        <div class="fs-mini">
          <div class="fs-mini-top">
            <span class="fs-mini-icon">{_icon("cart", 18)}</span>
            <span class="fs-mini-badge {'red' if out_of_stock else 'green'}">{'Urgent' if out_of_stock else 'Clear'}</span>
          </div>
          <div>
            <div class="fs-mini-value">{out_of_stock:,}</div>
            <div class="fs-mini-label">Out of stock</div>
          </div>
        </div>
        <div class="fs-mini">
          <div class="fs-mini-top">
            <span class="fs-mini-icon">{_icon("alert", 18)}</span>
            <span class="fs-mini-badge {'amber' if shortage else 'green'}">{'Watch' if shortage else 'Clear'}</span>
          </div>
          <div>
            <div class="fs-mini-value">{shortage:,}</div>
            <div class="fs-mini-label">Shortage risk</div>
          </div>
        </div>
      </div>
    </div>
    """


def _priority_rows(products: list[dict], limit: int | None = None) -> str:
    rows = products[:limit] if limit else products
    if not rows:
        return (
            '<div class="fs-empty"><div class="fs-empty-icon">'
            + _icon("box", 20)
            + "</div>No products need attention in this view.</div>"
        )
    markup = []
    for product in rows:
        _, _, note = STATUS_META.get(product["status"], ("", "neutral", ""))
        markup.append(
            f"""
            <div class="fs-row">
              <div class="fs-row-main">
                {_avatar(product['product'], 40)}
                <div style="min-width:0">
                  <div class="fs-row-title">{_h(product['product'])}</div>
                  <div class="fs-row-meta">Lead time {product['lead_time_days']} d · {_money(product['unit_cost'])}/unit</div>
                </div>
              </div>
              <div class="fs-row-col">
                {_status_badge(product['status'])}
                <div class="fs-row-meta">{_h(note)}</div>
              </div>
              <div class="fs-row-col">
                <div class="fs-row-strong">{_days(product['stock_coverage_days'])}</div>
                <div class="fs-row-meta">Coverage</div>
              </div>
              <div class="fs-row-col">
                <div class="fs-row-strong">{_money(product['inventory_value'])}</div>
                <div class="fs-row-meta">At cost</div>
              </div>
            </div>
            """
        )
    return '<div class="fs-list">' + "".join(markup) + "</div>"


def _priority_card(products: list[dict]) -> str:
    attention = [product for product in products if product["status"] in ATTENTION_STATUSES]
    return f"""
    <div class="fs-card fs-priorities">
      <div class="fs-card-head">
        <h3>Inventory Priorities</h3>
        <div class="fs-card-tools">
          <span class="fs-card-note">{len(attention)} open</span>
          <span class="fs-dots">•••</span>
        </div>
      </div>
      {_priority_rows(attention, limit=5)}
    </div>
    """


def _dashboard_html(summary: dict, products: list[dict]) -> str:
    return (
        '<div class="fs-dash">'
        + _hero_card(summary)
        + _bar_chart_card(products)
        + _gauge_card(summary)
        + _overview_card(summary)
        + _priority_card(products)
        + "</div>"
    )


def _inventory_table_card(products: list[dict]) -> str:
    if not products:
        return f"""
        <div class="fs-card">
          <div class="fs-card-head"><h3>Full inventory</h3><span class="fs-card-note">0 products</span></div>
          <div class="fs-empty"><div class="fs-empty-icon">{_icon("box", 20)}</div>No products match this view.</div>
        </div>
        """
    rows = []
    for product in products:
        rows.append(
            f"""
            <tr>
              <td><div class="prod">{_avatar(product['product'], 32)}<span>{_h(product['product'])}</span></div></td>
              <td class="num">{product['current_stock']:,}</td>
              <td class="num">{product['avg_daily_sales']:,.2f}</td>
              <td class="num">{product['lead_time_days']} d</td>
              <td class="num">{_days(product['stock_coverage_days'])}</td>
              <td class="num">{product['lead_time_demand']:,.1f}</td>
              <td class="num">{product['reorder_point']:,.1f}</td>
              <td class="num">{_money(product['unit_cost'])}</td>
              <td class="num">{_money(product['inventory_value'])}</td>
              <td>{_status_badge(product['status'])}</td>
            </tr>
            """
        )
    return f"""
    <div class="fs-card">
      <div class="fs-card-head"><h3>Full inventory</h3><span class="fs-card-note">{len(products)} products</span></div>
      <div class="fs-table-wrap">
        <table class="fs-table">
          <thead>
            <tr>
              <th>Product</th><th>Stock</th><th>Daily sales</th><th>Lead time</th>
              <th>Coverage</th><th>Lead-time demand</th><th>Reorder point</th>
              <th>Unit cost</th><th>Value</th><th>Status</th>
            </tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </div>
    """


def _priority_list_card(products: list[dict], title: str) -> str:
    attention = [product for product in products if product["status"] in ATTENTION_STATUSES]
    return f"""
    <div class="fs-card">
      <div class="fs-card-head">
        <h3>{_h(title)}</h3>
        <span class="fs-card-note">{len(attention)} open</span>
      </div>
      {_priority_rows(attention)}
    </div>
    """


def _empty_dashboard() -> None:
    _render_html(
        f"""
        <div class="fs-card fs-empty-hero">
          <div class="fs-empty-icon">{_icon("box", 28)}</div>
          <h2>Know what to reorder next</h2>
          <p>Load the fictional sample or upload a CSV, XLSX, or XLS file to see inventory value at cost, days of
          cover, and the products that need attention before the next delivery.</p>
        </div>
        """
    )
    left, right = st.columns(2)
    with left:
        if st.button("Load sample data", type="primary", width="stretch"):
            sample = _read_sample_file()
            if sample is None:
                st.session_state.flash_error = "The sample inventory file is not available."
                st.rerun()
            _activate_inventory(
                sample, "Fictional sample inventory", "Fictional sample data loaded."
            )
    with right:
        if st.button("Go to Inventory", width="stretch"):
            st.session_state.page = "Inventory"
            st.rerun()


def _no_data_card(message: str) -> None:
    _render_html(
        f"""
        <div class="fs-card fs-empty-hero">
          <div class="fs-empty-icon">{_icon("box", 28)}</div>
          <h2>Inventory not loaded</h2>
          <p>{_h(message)}</p>
        </div>
        """
    )
    left, middle, right = st.columns([1, 1, 1])
    with middle:
        if st.button("Open Inventory", type="primary", width="stretch"):
            st.session_state.page = "Inventory"
            st.rerun()


def _render_dashboard(
    summary: dict,
    products: list[dict],
    search_query: str,
    selected_statuses: list[str],
    sort_by: str,
) -> None:
    filtered = _filter_and_sort(products, search_query, selected_statuses, sort_by)
    _render_html(_dashboard_html(summary, filtered))
    _render_html(
        '<div class="fs-footnote">Inventory value is estimated at supplier cost, not selling '
        "price, revenue, or profit. “Uploaded at” records when the file entered this session, "
        "not a verified stock count.</div>"
    )


def _mapping_note() -> str | None:
    mapping = st.session_state.get("column_mapping") or {}
    if not mapping:
        return None
    worksheet = st.session_state.get("worksheet_name")
    ignored = st.session_state.get("ignored_columns") or []
    skipped = st.session_state.get("skipped_total_rows") or []
    renamed = [
        field
        for field in FIELD_LABELS
        if field in mapping and mapping[field] != field
    ]

    notes: list[str] = []
    if worksheet:
        notes.append(f"Worksheet '{worksheet}'.")
    if renamed:
        parts = [
            f"{FIELD_LABELS.get(field, field)} ← {mapping[field]}"
            for field in FIELD_LABELS
            if field in renamed
        ]
        notes.append("Columns mapped: " + " · ".join(parts) + ".")
    elif worksheet:
        notes.append("Columns matched the FullShelf template.")
    if ignored:
        notes.append("Ignored: " + ", ".join(ignored) + ".")
    if skipped:
        notes.append(f"Skipped {len(skipped)} total row(s).")
    return " ".join(notes) if notes else None


PLACEHOLDER_OPTION = "— Choose a column —"


def _preview_frame(report: dict[str, Any]) -> pd.DataFrame | None:
    rows = report.get("sample_rows") or []
    headers = report.get("headers") or []
    if not rows or not headers:
        return None
    labels: list[str] = []
    seen: dict[str, int] = {}
    for index, header in enumerate(headers):
        label = header or f"Column {index + 1}"
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            label = f"{label} ({seen[label]})"
        labels.append(label)
    return pd.DataFrame(rows, columns=labels)


def _render_pending_mapping() -> None:
    pending = st.session_state.get("pending_mapping")
    if not pending:
        return
    report = pending["report"]
    headers = report.get("headers") or []
    options = [PLACEHOLDER_OPTION] + [header for header in headers if header]
    fingerprint = hashlib.sha256(
        pending["file_data"]
        + b"\0"
        + (pending.get("sheet_name") or "").encode("utf-8")
    ).hexdigest()[:12]

    with st.container(border=True, key=f"mapping_card_{fingerprint}"):
        _render_html(
            """
            <div class="fs-card-head" style="margin-bottom:8px">
              <h3>Check column mapping</h3>
              <span class="fs-card-note">Nothing is calculated until you confirm</span>
            </div>
            """
        )
        if report.get("problems"):
            _render_html(
                f'<div class="fs-flash error">{_h(" ".join(report["problems"]))}</div>'
            )
        if report.get("missing_fields"):
            labels = ", ".join(
                FIELD_LABELS.get(field, field) for field in report["missing_fields"]
            )
            _render_html(
                f'<div class="fs-flash error">Choose a source column for: '
                f"{_h(labels)}.</div>"
            )

        location = f"Header row {report.get('header_row', '—')}"
        if report.get("sheet_name"):
            location = f"Worksheet '{report['sheet_name']}' · {location}"
        preview = _preview_frame(report)
        if preview is not None:
            _render_html(
                f'<div class="fs-footnote" style="margin:6px 0 4px">'
                f"{_h(location)} · first {len(preview)} data row(s)</div>"
            )
            st.dataframe(preview, width="stretch", hide_index=True)

        # Suggestions are staged on the previous run and applied here, before the
        # selectboxes exist, because Streamlit forbids writing to a widget key
        # after that widget has been instantiated.
        prefill_key = f"mapping_prefill_{fingerprint}"
        staged = st.session_state.pop(prefill_key, None)
        if isinstance(staged, dict):
            for field, column in staged.items():
                if field in FIELD_LABELS and column in options:
                    st.session_state[f"map_{fingerprint}_{field}"] = column

        selections: dict[str, str] = {}
        for field, label in FIELD_LABELS.items():
            key = f"map_{fingerprint}_{field}"
            suggested = report.get("suggested_mapping", {}).get(field)
            default = PLACEHOLDER_OPTION
            if isinstance(suggested, int) and 0 <= suggested < len(headers):
                if headers[suggested] in options:
                    default = headers[suggested]
            if key in st.session_state and st.session_state[key] not in options:
                st.session_state[key] = PLACEHOLDER_OPTION
            help_text = (
                "Suggested by the deterministic matcher. Change it if it is wrong."
                if default != PLACEHOLDER_OPTION
                else "Pick the column that holds this field."
            )
            if key in st.session_state:
                selections[field] = st.selectbox(
                    label, options, key=key, help=help_text
                )
            else:
                selections[field] = st.selectbox(
                    label,
                    options,
                    index=options.index(default),
                    key=key,
                    help=help_text,
                )

        remaining = [
            FIELD_LABELS[field]
            for field, value in selections.items()
            if value == PLACEHOLDER_OPTION
        ]
        chosen = [value for value in selections.values() if value != PLACEHOLDER_OPTION]
        duplicated = sorted({value for value in chosen if chosen.count(value) > 1})
        if remaining:
            _render_html(
                f'<div class="fs-footnote">Still needed: {_h(", ".join(remaining))}.</div>'
            )
        if duplicated:
            _render_html(
                f'<div class="fs-footnote">Each field needs a different column. '
                f"Used more than once: {_h(', '.join(duplicated))}.</div>"
            )

        error_key = f"mapping_error_{fingerprint}"
        mapping_error = st.session_state.pop(error_key, None)
        if mapping_error:
            _render_html(f'<div class="fs-flash error">{_h(mapping_error)}</div>')
        note_key = f"mapping_ai_note_{fingerprint}"
        ai_error_key = f"mapping_ai_error_{fingerprint}"
        ai_note = st.session_state.get(note_key)
        if ai_note:
            _render_html(f'<div class="fs-footnote">{_h(ai_note)}</div>')
        ai_error = st.session_state.pop(ai_error_key, None)
        if ai_error:
            _render_html(f'<div class="fs-flash error">{_h(ai_error)}</div>')

        consent = st.checkbox(
            "Send the column headings and up to 3 sample rows to Gemini for "
            "suggestions. The file itself is not sent, and nothing is loaded until "
            "you confirm.",
            key=f"mapping_consent_{fingerprint}",
        )
        ai_col, use_col, cancel_col = st.columns([1.35, 1.05, 0.75])
        with ai_col:
            if st.button(
                "Suggest with Gemini",
                width="stretch",
                disabled=not consent,
                key=f"mapping_suggest_{fingerprint}",
                help="You must tick the consent box first.",
            ):
                try:
                    with st.spinner("Asking Gemini for column suggestions…"):
                        suggestions = suggest_column_mapping(
                            headers, report.get("sample_rows") or []
                        )
                except AgentError as exc:
                    st.session_state[ai_error_key] = str(exc)
                else:
                    prefill = {
                        field: suggestion.get("column")
                        for field, suggestion in suggestions.items()
                        if field in FIELD_LABELS
                        and suggestion.get("column") in options
                    }
                    if prefill:
                        st.session_state[prefill_key] = prefill
                        st.session_state[note_key] = (
                            f"Gemini suggested {len(prefill)} column(s). Review the "
                            "selections before continuing."
                        )
                    else:
                        st.session_state[note_key] = (
                            "Gemini did not suggest a matching column. Choose the "
                            "columns manually."
                        )
                st.rerun()
        with use_col:
            if st.button(
                "Use this mapping",
                type="primary",
                width="stretch",
                disabled=bool(remaining or duplicated),
                key=f"mapping_use_{fingerprint}",
            ):
                _activate_inventory(
                    pending["file_data"],
                    pending["display_name"],
                    "Inventory validated with your column mapping.",
                    sheet_name=pending.get("sheet_name"),
                    column_mapping=selections,
                )
        with cancel_col:
            if st.button(
                "Cancel",
                width="stretch",
                key=f"mapping_cancel_{fingerprint}",
            ):
                st.session_state.pending_mapping = None
                st.rerun()


def _render_inventory(
    analysis: dict | None,
    search_query: str,
    selected_statuses: list[str],
    sort_by: str,
) -> None:
    sample_bytes = _read_sample_file()
    with st.container(border=True, key="import_card"):
        _render_html(
            f"""
            <div class="fs-card-head" style="margin-bottom:8px">
              <h3>Import inventory</h3>
              <span class="fs-card-note">CSV, XLSX, or XLS · up to 5 MB · 1,000 products</span>
            </div>
            """
        )
        uploaded_file = st.file_uploader(
            "Upload inventory file",
            type=["csv", "xlsx", "xls"],
            label_visibility="collapsed",
        )
        sheet_name: str | None = None
        workbook_error: str | None = None
        if uploaded_file is not None:
            suffix = Path(uploaded_file.name).suffix.casefold()
            if suffix in (".xlsx", ".xls"):
                file_data = uploaded_file.getvalue()
                try:
                    sheets = list_workbook_sheets(file_data, uploaded_file.name)
                except InventoryValidationError as exc:
                    sheets = []
                    workbook_error = str(exc)
                if workbook_error:
                    _render_html(
                        f'<div class="fs-flash error">{_h(workbook_error)}</div>'
                    )
                elif len(sheets) > 1:
                    try:
                        suggested = suggest_inventory_sheet(
                            file_data, uploaded_file.name
                        )
                    except InventoryValidationError:
                        suggested = None
                    if suggested not in sheets:
                        suggested = sheets[0]
                    selector_key = (
                        "worksheet_selector_"
                        + hashlib.sha256(file_data).hexdigest()[:12]
                    )
                    sheet_name = st.selectbox(
                        "Worksheet",
                        sheets,
                        index=sheets.index(suggested),
                        key=selector_key,
                        help="Choose the worksheet that holds your stock table.",
                    )
                elif sheets:
                    sheet_name = sheets[0]
        upload_col, sample_col, download_col = st.columns([1.15, 0.9, 1.0])
        with upload_col:
            if st.button(
                "Validate and use",
                type="primary",
                width="stretch",
                disabled=uploaded_file is None or workbook_error is not None,
            ):
                file_data = uploaded_file.getvalue()
                try:
                    report = inspect_inventory_file(
                        file_data, uploaded_file.name, sheet_name
                    )
                except InventoryValidationError as exc:
                    st.session_state.flash_error = str(exc)
                    st.rerun()
                if report["is_ready"]:
                    confirmed = {
                        field: report["headers"][index]
                        for field, index in report["suggested_mapping"].items()
                    }
                    _activate_inventory(
                        file_data,
                        uploaded_file.name,
                        "Inventory validated and loaded for this session.",
                        sheet_name=sheet_name,
                        column_mapping=confirmed,
                    )
                else:
                    st.session_state.pending_mapping = {
                        "file_data": file_data,
                        "display_name": uploaded_file.name,
                        "sheet_name": sheet_name,
                        "report": report,
                    }
                    st.session_state.page = "Inventory"
                    st.rerun()
        with sample_col:
            if st.button(
                "Load sample",
                width="stretch",
                disabled=sample_bytes is None,
            ):
                if sample_bytes is None:
                    st.session_state.flash_error = (
                        "The sample inventory file is not available."
                    )
                    st.rerun()
                _activate_inventory(
                    sample_bytes,
                    "Fictional sample inventory",
                    "Fictional sample data loaded.",
                )
        with download_col:
            st.download_button(
                "Download sample",
                data=sample_bytes or b"",
                file_name="sample_inventory.csv",
                mime="text/csv",
                width="stretch",
                disabled=sample_bytes is None,
            )
        if analysis is not None:
            _render_html(
                f'<div class="fs-footnote" style="margin-top:10px">Current dataset: '
                f"{_h(st.session_state.source_name or 'Inventory')} · "
                f"{_h(_format_timestamp(st.session_state.uploaded_at))}</div>"
            )
            mapping_note = _mapping_note()
            if mapping_note:
                _render_html(
                    f'<div class="fs-footnote" style="margin-top:6px">'
                    f"{_h(mapping_note)}</div>"
                )

    _render_pending_mapping()

    if analysis is None:
        _no_data_card(
            "Upload a CSV, XLSX, or XLS file, or load the sample, to see the full inventory."
        )
        return

    products = _filter_and_sort(
        analysis["products"], search_query, selected_statuses, sort_by
    )
    _render_html(_inventory_table_card(products))


def _render_priorities(
    analysis: dict | None,
    search_query: str,
    selected_statuses: list[str],
    sort_by: str,
) -> None:
    if analysis is None:
        _no_data_card("Load inventory to see which products need attention.")
        return
    products = _filter_and_sort(
        analysis["summary"]["attention_products"],
        search_query,
        selected_statuses,
        sort_by,
    )
    _render_html(_priority_list_card(products, "All priorities"))


def _render_assistant(analysis: dict | None) -> None:
    if analysis is None:
        _no_data_card("Load inventory before asking the assistant.")
        return

    _render_html(
        f"""
        <div class="fs-card fs-chat-head">
          <div class="fs-chat-avatar">{_icon("spark", 20)}</div>
          <div>
            <h3>Ask StockWhisperer</h3>
            <p>Answers use this session's Python-calculated inventory. It cannot place orders.</p>
          </div>
        </div>
        """
    )

    for message in st.session_state.chat_messages:
        avatar = "🧑" if message["role"] == "user" else "📦"
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])

    pending = st.session_state.pop("pending_question", None)
    if not st.session_state.chat_messages and not pending:
        st.markdown('<div class="fs-suggest-label">Try asking</div>', unsafe_allow_html=True)
        columns = st.columns(2)
        for index, prompt in enumerate(SUGGESTIONS):
            with columns[index % 2]:
                if st.button(prompt, key=f"suggest_{index}", width="stretch"):
                    st.session_state.pending_question = prompt
                    st.rerun()

    typed = st.chat_input("Ask about this inventory...")
    question = pending or typed
    if not question:
        return

    st.session_state.chat_messages.append({"role": "user", "content": question})
    try:
        with st.spinner("Checking your inventory with StockWhisperer..."):
            answer = answer_inventory_question(
                question,
                analysis,
                history=st.session_state.chat_messages[:-1],
            )
        st.session_state.chat_messages.append({"role": "assistant", "content": answer})
    except AgentError as exc:
        st.session_state.chat_messages.append(
            {"role": "assistant", "content": f"AI assistant unavailable: {exc}"}
        )
    except Exception:
        logging.exception("Unexpected StockWhisperer UI error")
        st.session_state.chat_messages.append(
            {
                "role": "assistant",
                "content": (
                    "AI assistant unavailable: The inventory analysis is available, but the "
                    "AI assistant could not connect. Please check your Gemini configuration "
                    "or try again."
                ),
            }
        )
    st.rerun()


def _help_html() -> str:
    return """
    <div class="fs-help-grid">
      <div class="fs-card fs-help-card">
        <div class="fs-card-head"><h3>How FullShelf decides</h3></div>
        <ul class="fs-help-list">
          <li>Python, not the AI model, calculates coverage, lead-time demand, reorder points, status, priority, and inventory value.</li>
          <li>Priority is a deterministic urgency heuristic: out of stock first, then the largest lead-time coverage shortfall, then items exactly at their reorder point.</li>
          <li>The assistant explains those calculations. It does not perform arithmetic or invent products.</li>
          <li>Tool results are read from this session's validated dataset, so the dashboard and chat use the same facts.</li>
        </ul>
      </div>
      <div class="fs-card fs-help-card">
        <div class="fs-card-head"><h3>Assumptions</h3></div>
        <ul class="fs-help-list">
          <li>Average daily demand is supplied by you and is only a rough estimate for regular demand.</li>
          <li>Reorder point equals average daily demand multiplied by the estimated supplier lead time. Safety stock is zero.</li>
          <li>Lead times are estimates, and outstanding supplier orders or backorders are not tracked.</li>
          <li>Selling price, margin, supplier minimums, and profitability are not represented.</li>
        </ul>
      </div>
      <div class="fs-card fs-help-card">
        <div class="fs-card-head"><h3>Limits</h3></div>
        <ul class="fs-help-list">
          <li>No advanced forecasting, seasonality, or intermittent-demand model is applied.</li>
          <li>There is no validated purchase optimiser or budget allocation engine.</li>
          <li>No real-time POS, supplier, or inventory connection is present.</li>
          <li>“Uploaded at” records when the file entered this session; it is not a verified stock-count time.</li>
        </ul>
      </div>
      <div class="fs-card fs-help-card">
        <div class="fs-card-head"><h3>Data &amp; privacy</h3></div>
        <ul class="fs-help-list">
          <li>Uploaded data and chat are held in Streamlit session state only. A browser reload may clear them.</li>
          <li>There is no database or cross-session inventory store.</li>
          <li>Only your question, recent chat messages, and the computed figures the assistant requests are sent to Gemini. If you explicitly consent, column headings and up to three sample rows may also be sent for mapping suggestions. The full file is never transmitted.</li>
          <li>The assistant never receives your API key in a prompt, and tracebacks are not shown in the interface.</li>
          <li>AI output supports human review. Check important business decisions against your own records.</li>
        </ul>
      </div>
      <div class="fs-card fs-help-card fs-help-wide">
        <div class="fs-card-head"><h3>Terms of use</h3></div>
        <ul class="fs-help-list">
          <li>FullShelf is a decision-support prototype, not accounting, legal, or financial advice.</li>
          <li>The fictional sample exists for demonstration only and does not describe a real business.</li>
          <li>You are responsible for checking stock counts, lead times, and supplier orders before purchasing.</li>
          <li>FullShelf does not place orders, process payments, or guarantee stock availability.</li>
        </ul>
      </div>
    </div>
    """


st.set_page_config(
    page_title="FullShelf · Inventory",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(CSS, unsafe_allow_html=True)

for key, default in (
    ("page", "Dashboard"),
    ("inventory", None),
    ("analysis", None),
    ("uploaded_at", None),
    ("dataset_id", None),
    ("source_name", None),
    ("column_mapping", {}),
    ("ignored_columns", []),
    ("worksheet_name", None),
    ("skipped_total_rows", []),
    ("pending_mapping", None),
    ("chat_messages", []),
    ("pending_question", None),
    ("theme", "light"),
):
    if key not in st.session_state:
        st.session_state[key] = default

if st.session_state.theme == "dark":
    st.markdown(DARK_CSS, unsafe_allow_html=True)

_render_sidebar()

flash = st.session_state.pop("flash", None)
if flash:
    st.markdown(f'<div class="fs-flash">{_h(flash)}</div>', unsafe_allow_html=True)
flash_error = st.session_state.pop("flash_error", None)
if flash_error:
    st.markdown(f'<div class="fs-flash error">{_h(flash_error)}</div>', unsafe_allow_html=True)

search_col, icons_col = st.columns([2.05, 1.15], vertical_alignment="center")
with search_col:
    search_query = st.text_input(
        "Search",
        placeholder="Find inventory, orders or reports",
        label_visibility="collapsed",
        key="search_query",
    )
with icons_col:
    _render_topbar()

page = st.session_state.page
controls = page in ("Dashboard", "Inventory", "Priorities")
sort_by, selected_statuses = _render_page_header(controls)

analysis = st.session_state.analysis
if page == "Dashboard":
    if analysis is None:
        _empty_dashboard()
    else:
        _render_dashboard(
            analysis["summary"],
            analysis["products"],
            search_query,
            selected_statuses,
            sort_by,
        )
elif page == "Inventory":
    _render_inventory(analysis, search_query, selected_statuses, sort_by)
elif page == "Priorities":
    _render_priorities(analysis, search_query, selected_statuses, sort_by)
elif page == "Assistant":
    _render_assistant(analysis)
else:
    _render_html(_help_html())
