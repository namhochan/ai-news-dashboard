# -*- coding: utf-8 -*-
"""
앱 전역 스타일 + 퀵 메뉴 사이드바 렌더링
"""

import streamlit as st

# ---------------------------------------------------
# 전역 CSS (기본 폰트, 간격, 컬러)
# ---------------------------------------------------
GLOBAL_CSS = """
<style>
html, body, [class*="css"]  {
    font-family: 'Pretendard', 'Noto Sans KR', sans-serif;
    background-color: #0f1420;
    color: #e4e8f0;
    scroll-behavior: smooth;
}

h1, h2, h3, h4, h5, h6 {
    color: #e4e8f0;
    font-weight: 700;
}

section[data-testid="stSidebar"] {
    background-color: #0f1420 !important;
}

hr { border: 0; border-top: 1px solid #2b3a55; margin: 12px 0; }

[data-testid="stMarkdownContainer"] ul li {
    margin-bottom: 0.25rem;
}

button[kind="primary"] {
    border-radius: 8px !important;
    font-weight: 600 !important;
}

.stDataFrame { border-radius: 8px; overflow: hidden; }
</style>
"""

# ---------------------------------------------------
# 퀵 메뉴 CSS (작고 깔끔한 floating nav)
# ---------------------------------------------------
QUICKMENU_CSS = """
<style>
.quick-menu {
  position: fixed;
  top: 50%;
  right: 12px;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  gap: 6px;
  z-index: 9999;
}

.quick-btn {
  background: rgba(30, 41, 59, 0.8);
  border: 1px solid #334155;
  color: #c7d2fe;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 8px;
  border-radius: 8px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s ease-in-out;
  width: 120px;
  text-decoration: none;
}

.quick-btn:hover {
  background: #1e293b;
  transform: scale(1.05);
  color: #fff;
  border-color: #64748b;
}

@media (max-width: 768px) {
  .quick-menu {
    right: 5px;
  }
  .quick-btn {
    width: 95px;
    font-size: 11px;
    padding: 5px 6px;
  }
}
</style>
"""

# ---------------------------------------------------
# 퀵 메뉴 버튼 목록
# ---------------------------------------------------
MENU_ITEMS = [
    ("AI 뉴스 요약엔진", "#ai-summary"),
    ("AI 상승 확률", "#ai-risk"),
    ("유망 종목 Top5", "#ai-top5"),
    ("AI 종합 판단", "#ai-judge"),
    ("3일 예측", "#ai-forecast"),
    ("테마 관리자", "#theme-admin"),
]

# ---------------------------------------------------
# 렌더링 함수
# ---------------------------------------------------
def apply_global_style():
    """앱 전체 공통 스타일 적용"""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

def render_quick_menu():
    """화면 오른쪽에 작게 고정된 퀵 메뉴 렌더링"""
    st.markdown(QUICKMENU_CSS, unsafe_allow_html=True)
    btn_html = "".join(
        [f'<a class="quick-btn" href="{href}">{label}</a>' for label, href in MENU_ITEMS]
    )
    st.markdown(f"<div class='quick-menu'>{btn_html}</div>", unsafe_allow_html=True)
