# modules/style.py
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st

KST = ZoneInfo("Asia/Seoul")

BASE_CSS = """
<style>
/* 전체 여백 컴팩트 */
.block-container { padding-top: 0.6rem; padding-bottom: 2rem; max-width: 1200px; }

/* 제목/본문 간격 축소 */
h2, h3 { margin: 0.4rem 0 0.6rem 0; }
hr { margin: 0.6rem 0; }

/* 컴팩트 표 */
.dataframe td, .dataframe th { padding: 6px 8px !important; font-size: 0.92rem; }

/* 퀵 메뉴: 더 작게, 우측 고정 */
.quick-nav {
  position: fixed; right: 10px; top: 90px; z-index: 9999;
  width: 150px; background: #0e1420; border: 1px solid #2b3a55;
  border-radius: 12px; padding: 8px; box-shadow: 0 6px 16px rgba(0,0,0,.35);
}
.quick-nav h4 { margin: 0 0 8px 0; font-size: 0.9rem; color: #c7d2fe; }
.quick-nav a {
  display: block; padding: 6px 8px; margin: 6px 0; border: 1px solid #2b3a55;
  border-radius: 8px; font-size: 0.86rem; color: #e5e7eb; text-decoration: none;
  background: #121a2a;
}
.quick-nav a:hover { background: #1a2337; }
.section-anchor { scroll-margin-top: 72px; } /* 앵커 이동 시 상단 여백 */
</style>
"""

def inject_base_css():
    st.markdown(BASE_CSS, unsafe_allow_html=True)

def render_quick_menu():
    html = """
    <div class="quick-nav">
      <h4>Quick Menu</h4>
      <a href="#mkt"  >📊 시장 요약</a>
      <a href="#news" >📰 최신 뉴스</a>
      <a href="#themes">🔥 테마 요약</a>
      <a href="#rise" >📈 상승 확률</a>
      <a href="#top5" >🚀 유망 Top5</a>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def kst_now_str():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S (KST)")
