# -*- coding: utf-8 -*-
import streamlit as st

def inject_base_css():
    CSS = """
    <style>
      :root { --chip-gap:8px; }
      .block-container { padding-top: 1rem !important; padding-bottom: 2rem !important; }
      h2 { margin: 0.6rem 0 0.4rem 0 !important; }
      hr, .stDivider { margin: 0.6rem 0 !important; }
      /* 뉴스 타이틀 줄 간격 콤팩트 */
      .news-item { display:flex; justify-content:space-between; align-items:center;
                   padding:4px 8px; border-bottom:1px solid #1f2937; }
      .news-item a { text-decoration:none; }
      .news-time { color:#98a2b3; font-size:0.82rem; margin-left:10px; white-space:nowrap;}
      /* 퀵메뉴 (작게) */
      .quick-menu { position:fixed; right:10px; top:92px; width:160px; z-index:9999;
                    background:#0b1220; border:1px solid #223047; border-radius:14px; padding:8px; }
      .quick-menu h4 { margin:0 0 6px 6px; font-size:0.9rem; color:#dbe2ff; opacity:.9;}
      .qbtn { display:block; width:100%; text-align:left; margin:6px 0; padding:8px 10px;
              border:1px solid #2b3a55; border-radius:10px; background:#0f1420; color:#c7d2fe;
              font-size:0.86rem; }
      .qbtn:hover { border-color:#4c5f8a; background:#111a2a; }
      @media (max-width: 1100px) { .quick-menu { display:none; } }
    </style>
    """
    st.markdown(CSS, unsafe_allow_html=True)

def render_quick_menu():
    st.markdown("""
    <div class="quick-menu">
      <h4>Quick Menu</h4>
      <a class="qbtn" href="#sec-news">📰 최신 뉴스</a>
      <a class="qbtn" href="#sec-themes">🔥 테마 요약</a>
      <a class="qbtn" href="#sec-top5">🚀 유망 Top5</a>
    </div>
    """, unsafe_allow_html=True)
