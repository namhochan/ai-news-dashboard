# modules/style.py
# 전역 스타일 + 퀵 메뉴

def inject_base_css():
    return """
    <style>
      :root{ --gap:10px; --card: #10141d; --bd:#1e2a3d; --txt:#dfe7f5; }
      .compact *{ line-height:1.2 }
      .k-caption{ color:#9aa7bd; font-size:12px; }
      .ticker-wrap{overflow:hidden;width:100%;border:1px solid #263042;border-radius:10px;background:#0f1420;}
      .ticker-track{display:flex;gap:16px;align-items:center;width:max-content;will-change:transform;animation:ticker-scroll var(--speed,30s) linear infinite;}
      @keyframes ticker-scroll{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
      .badge{display:inline-flex;align-items:center;gap:8px;background:#0f1420;border:1px solid #2b3a55;color:#c7d2fe;padding:6px 10px;border-radius:8px;font-weight:700;white-space:nowrap;}
      .badge .name{color:#9fb3c8;font-weight:600}
      .badge .up{color:#e66}.badge .down{color:#6aa2ff}.sep{color:#44526b;padding:0 6px}
      .quick{position:fixed; right:12px; top:110px; z-index:9999;}
      .quick .card{background:#0b1020; border:1px solid #1f2a46; border-radius:14px; padding:10px; box-shadow:0 6px 16px rgba(0,0,0,.35); width:150px;}
      .quick .h{color:#cdd9ff; font-weight:700; font-size:13px; margin:0 0 6px 2px;}
      .quick a{display:block; font-size:12px; padding:8px 10px; margin:6px 0; color:#e7efff; background:#0f1428; border:1px solid #243151; border-radius:10px; text-decoration:none}
      .quick a:hover{background:#132046}
      .chip{display:inline-block; padding:3px 8px; border:1px solid #2b3a55; border-radius:10px; font-size:12px; margin-right:6px; color:#bfd2ff}
      .news-row{margin:4px 0 8px 0}
      .news-meta{color:#8ea3c9; font-size:12px}
    </style>
    """

def render_quick_menu():
    return """
    <div class="quick">
      <div class="card">
        <div class="h">Quick Menu</div>
        <a href="#sec-ticker">📊 시장 요약</a>
        <a href="#sec-news">📰 최신 뉴스</a>
        <a href="#sec-themes">🔥 테마 요약</a>
        <a href="#sec-top5">🚀 유망 Top5</a>
        <a href="#sec-judge">🧾 종합 판단</a>
      </div>
    </div>
    """
