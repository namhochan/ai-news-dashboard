# -*- coding: utf-8 -*-
def inject_base_css() -> str:
    return """
    <style>
      :root{
        --gap:10px; --card:#10141d; --bd:#1e2a3d; --txt:#dfe7f5;
        --muted:#9aa7bd; --muted-2:#8ea3c9; --chip:#2b3a55; --panel:#0f1420;
        --speed: 25s; --up:#ee6666; --down:#6aa2ff; --shadow: 0 6px 16px rgba(0,0,0,.35);
      }
      .compact *{ line-height:1.3 }
      .k-caption{ color:var(--muted); font-size:12px; }

      .ticker-wrap{overflow:hidden;width:100%;border:1px solid #263042;border-radius:10px;background:var(--panel);}
      .ticker-track{display:flex;align-items:center;gap:16px;min-width:200%;will-change:transform;animation:ticker-scroll var(--speed) linear infinite;}
      @keyframes ticker-scroll{0%{transform:translateX(0);}100%{transform:translateX(-50%);}}
      .badge{display:inline-flex;align-items:center;gap:8px;background:var(--panel);border:1px solid var(--chip);color:#c7d2fe;padding:6px 10px;border-radius:8px;font-weight:700;white-space:nowrap;}
      .badge .name{color:#9fb3c8;font-weight:600}
      .badge .up{color:var(--up)} .badge .down{color:var(--down)} .sep{color:#44526b;padding:0 6px}

      .quick{position:fixed; right:12px; top:110px; z-index:9999;}
      .quick .card{background:#0b1020; border:1px solid #1f2a46; border-radius:14px; padding:10px; box-shadow:var(--shadow); width:168px;}
      .quick .h{color:#cdd9ff; font-weight:700; font-size:13px; margin:0 0 6px 2px;}
      .quick a{display:block; font-size:12px; padding:8px 10px; margin:6px 0; color:#e7efff; background:#0f1428; border:1px solid #243151; border-radius:10px; text-decoration:none}
      .quick a:hover{background:#132046}

      @media (max-width: 900px){
        .quick{ left:0; right:0; bottom:10px; top:auto; }
        .quick .card{ width:auto; display:flex; gap:8px; padding:8px; overflow:auto; }
        .quick .h{ display:none; }
        .quick a{ flex:0 0 auto; margin:0; }
      }

      .chip{display:inline-block; padding:3px 8px; border:1px solid var(--chip); border-radius:10px; font-size:12px; margin-right:6px; color:#bfd2ff}
      .news-row{margin:4px 0 8px 0}
      .news-meta{analysis
