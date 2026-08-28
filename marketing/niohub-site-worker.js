/**
 * Cloudflare Worker — site institucional NIO HUB (HTML estático).
 *
 * Paleta alinhada ao tema escuro do app (`frontend/frontend/src/App.css`):
 * fundo #212121, cards #2F3238, primário #0D70B3.
 *
 * Conteúdo atualizado vs. produto recente: galeria no chatbot, inatividade na
 * automação, painel de atendimento — ver seções Início / Funcionalidades / FAQ.
 */

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const path = normalizePath(url.pathname);

    if (path === "/") {
      return htmlResponse(
        renderPage({
          title: "NIO HUB | Início",
          description:
            "Hub de tecnologia para provedores: atendimento inteligente, app do cliente, TR-069, integrações e automações.",
          activePage: "inicio",
          content: renderInicio(),
        }),
      );
    }

    if (path === "/sobre") {
      return htmlResponse(
        renderPage({
          title: "NIO HUB | Sobre Nós",
          description:
            "Trajetória e visão da NIO HUB como plataforma para provedores de internet.",
          activePage: "sobre",
          content: renderSobre(),
        }),
      );
    }

    if (path === "/funcionalidades") {
      return htmlResponse(
        renderPage({
          title: "NIO HUB | Funcionalidades",
          description:
            "Atendimento, aplicativo, integrações SGP/MK/IXC, TR-069, relatórios, automações e segurança.",
          activePage: "funcionalidades",
          content: renderFuncionalidades(),
        }),
      );
    }

    if (path === "/demonstracao") {
      return htmlResponse(
        renderPage({
          title: "NIO HUB | Demonstração",
          description: "Telas do aplicativo do cliente e do módulo técnico TR-069.",
          activePage: "demonstracao",
          content: renderDemonstracao(),
        }),
      );
    }

    if (path === "/faq") {
      return htmlResponse(
        renderPage({
          title: "NIO HUB | FAQ",
          description: "Perguntas frequentes sobre a plataforma NIO HUB para provedores.",
          activePage: "faq",
          content: renderFaq(),
        }),
      );
    }

    if (path === "/calculadora") {
      return htmlResponse(
        renderPage({
          title: "NIO HUB | Calculadora WhatsApp",
          description: "Estimativa de custo da API oficial do WhatsApp (Brasil).",
          activePage: "calculadora",
          content: renderCalculadora(),
        }),
      );
    }

    if (path === "/contato") {
      return htmlResponse(
        renderPage({
          title: "NIO HUB | Contato",
          description: "Fale com a equipe NIO HUB por e-mail ou WhatsApp.",
          activePage: "contato",
          content: renderContato(),
        }),
      );
    }

    return new Response("Página não encontrada", { status: 404 });
  },
};

function normalizePath(pathname) {
  if (!pathname || pathname === "") return "/";
  if (pathname.length > 1 && pathname.endsWith("/")) {
    return pathname.slice(0, -1);
  }
  return pathname;
}

function htmlResponse(body) {
  return new Response(body, {
    headers: {
      "Content-Type": "text/html; charset=UTF-8",
    },
  });
}

function renderPage({ title, description = "", activePage, content }) {
  const desc = description
    ? `<meta name="description" content="${escapeHtml(description)}" />`
    : "";
  return `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${escapeHtml(title)}</title>
  ${desc}
  <link rel="icon" type="image/png" href="https://i.imgur.com/MLwyaEt.png" />

  <style>
    :root{
      --bg-main:#212121;
      --bg-section:#1a1a1a;
      --bg-topbar:#353A40;
      --bg-topbar-2:#2F3238;
      --bg-card:#2F3238;
      --bg-card-2:#353A40;
      --bg-card-3:#3a4148;
      --border:#454B53;
      --text-main:#F5F7FA;
      --text-muted:#AEB6C2;
      --text-soft:#8b95a5;
      --primary:#0D70B3;
      --primary-hover:#2b8fd6;
      --primary-soft:rgba(13,112,179,.18);
      --accent-warm:#F59E0B;
      --success:#22C55E;
      --warning:#F59E0B;
      --danger:#EF4444;
      --shadow:0 18px 40px rgba(0,0,0,.45);
    }

    *{
      margin:0;
      padding:0;
      box-sizing:border-box;
      font-family:Arial, Helvetica, sans-serif;
    }

    html{ scroll-behavior:smooth; }

    body{
      background:
        radial-gradient(circle at top left, rgba(13,112,179,.14), transparent 30%),
        linear-gradient(180deg, var(--bg-main), #181818);
      color:var(--text-main);
      overflow-x:hidden;
    }

    a{ color:inherit; text-decoration:none; }
    img{ max-width:100%; display:block; }

    .container{
      width:min(1200px, calc(100% - 32px));
      margin:0 auto;
    }

    .nav{
      position:sticky;
      top:0;
      z-index:9999;
      background:linear-gradient(180deg, rgba(53,58,64,.97), rgba(47,50,56,.95));
      backdrop-filter:blur(12px);
      border-bottom:1px solid var(--border);
    }

    .nav-inner{
      min-height:84px;
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:24px;
    }

    .logo{
      display:flex;
      align-items:center;
      gap:14px;
      flex-shrink:0;
    }

    .logo img{
      width:56px;
      height:56px;
      object-fit:contain;
      border-radius:12px;
    }

    .logo-text{ display:flex; flex-direction:column; }
    .logo-text strong{
      font-size:28px;
      line-height:1;
      letter-spacing:.4px;
    }
    .logo-text span{
      margin-top:8px;
      font-size:11px;
      color:var(--text-soft);
      letter-spacing:2px;
    }

    .nav-links{
      display:flex;
      align-items:center;
      gap:30px;
      flex-wrap:wrap;
      justify-content:flex-end;
    }

    .nav-links a{
      color:var(--text-main);
      font-size:15px;
      transition:.25s;
      white-space:nowrap;
    }
    .nav-links a:hover{ color:var(--primary-hover); }
    .nav-links a.active{
      color:#dbeafe;
      font-weight:700;
    }

    .nav-cta{
      padding:11px 18px;
      border-radius:999px;
      border:1px solid rgba(13,112,179,.45);
      background:var(--primary-soft);
      color:#e8f4ff !important;
      font-weight:700;
    }

    .menu-toggle{
      display:none;
      background:transparent;
      border:1px solid var(--border);
      color:#fff;
      border-radius:12px;
      width:46px;
      height:46px;
      font-size:22px;
      cursor:pointer;
    }

    .page-hero{ padding:72px 0 34px; }

    .page-box{
      background:linear-gradient(180deg, var(--bg-card), var(--bg-card-2));
      border:1px solid var(--border);
      border-radius:28px;
      padding:38px;
      box-shadow:var(--shadow);
    }

    .badge{
      display:inline-flex;
      align-items:center;
      justify-content:center;
      padding:10px 16px;
      border-radius:999px;
      background:var(--primary-soft);
      border:1px solid rgba(13,112,179,.35);
      color:#cfe8ff;
      font-size:14px;
      font-weight:700;
      margin-bottom:18px;
    }

    .page-box h1{
      font-size:clamp(34px, 5vw, 64px);
      line-height:1.05;
      letter-spacing:-1.4px;
      margin-bottom:16px;
    }
    .page-box h1 span{ color:var(--primary-hover); }

    .page-line{
      width:145px;
      height:5px;
      border-radius:999px;
      background:linear-gradient(90deg, var(--primary), var(--primary-hover));
      margin-bottom:22px;
    }

    .page-box p.lead{
      color:#dce3ec;
      font-size:19px;
      line-height:1.85;
      max-width:920px;
    }

    .section{ padding:36px 0 82px; }

    .section-head{
      text-align:center;
      margin-bottom:34px;
    }
    .section-head h2{
      font-size:clamp(28px, 4vw, 50px);
      margin-bottom:12px;
      line-height:1.1;
    }
    .section-head h2 span{ color:var(--primary-hover); }
    .section-head p{
      max-width:860px;
      margin:0 auto;
      color:var(--text-muted);
      font-size:18px;
      line-height:1.85;
    }

    .hero-actions{
      display:flex;
      gap:14px;
      flex-wrap:wrap;
      margin-top:28px;
    }

    .btn{
      display:inline-flex;
      align-items:center;
      justify-content:center;
      min-width:190px;
      padding:14px 22px;
      border-radius:14px;
      font-weight:700;
      border:none;
      cursor:pointer;
      transition:.25s;
    }
    .btn-primary{
      background:var(--primary);
      color:#fff;
    }
    .btn-primary:hover{ background:var(--primary-hover); }
    .btn-secondary{
      background:transparent;
      border:1px solid var(--border);
      color:var(--text-main);
    }
    .btn-secondary:hover{
      border-color:var(--primary-hover);
      color:var(--primary-hover);
    }

    .grid-2{ display:grid; grid-template-columns:1fr 1fr; gap:22px; }
    .grid-3{ display:grid; grid-template-columns:repeat(3,1fr); gap:22px; }
    .grid-4{ display:grid; grid-template-columns:repeat(4,1fr); gap:18px; }

    .card{
      background:linear-gradient(180deg, var(--bg-card), var(--bg-card-2));
      border:1px solid var(--border);
      border-radius:24px;
      padding:28px;
      box-shadow:var(--shadow);
    }
    .card h3{ font-size:24px; margin-bottom:14px; }
    .card p{
      color:var(--text-muted);
      line-height:1.8;
      margin-bottom:14px;
    }
    .card ul{ list-style:none; }
    .card li{
      position:relative;
      padding-left:22px;
      color:#edf2f7;
      line-height:1.75;
      margin-bottom:10px;
    }
    .card li::before{
      content:"";
      position:absolute;
      left:0;
      top:10px;
      width:9px;
      height:9px;
      border-radius:50%;
      background:var(--primary-hover);
    }

    .icon{
      width:58px;
      height:58px;
      border-radius:16px;
      background:var(--primary-soft);
      display:flex;
      align-items:center;
      justify-content:center;
      font-size:28px;
      margin-bottom:18px;
    }

    .stat{
      background:linear-gradient(180deg, var(--bg-card), var(--bg-card-2));
      border:1px solid var(--border);
      border-radius:22px;
      padding:24px;
      box-shadow:var(--shadow);
    }
    .stat strong{ display:block; font-size:38px; margin-bottom:10px; }
    .stat p{ color:var(--text-muted); line-height:1.7; }

    .preview-card{
      background:rgba(255,255,255,.03);
      border:1px solid var(--border);
      border-radius:20px;
      padding:20px;
    }
    .preview-card h3{ font-size:20px; margin-bottom:12px; }
    .preview-card p{
      color:var(--text-muted);
      line-height:1.75;
      margin-bottom:14px;
    }

    .mini-metrics{
      display:grid;
      grid-template-columns:repeat(2,1fr);
      gap:12px;
    }
    .mini-metric{
      background:rgba(255,255,255,.04);
      border:1px solid var(--border);
      border-radius:16px;
      padding:14px;
    }
    .mini-metric span{
      display:block;
      font-size:12px;
      color:var(--text-soft);
      margin-bottom:8px;
    }
    .mini-metric strong{ font-size:24px; }

    .about-section{ position:relative; overflow:hidden; }
    .about-wrapper{ position:relative; padding-top:110px; }

    .about-floating-timeline{
      position:sticky;
      top:96px;
      z-index:30;
      max-width:320px;
      margin-left:auto;
      margin-right:18px;
      margin-bottom:-70px;
      background:linear-gradient(180deg, var(--bg-card), var(--bg-card-2));
      color:var(--text-main);
      border:1px solid var(--border);
      border-radius:18px;
      padding:22px 20px;
      transform:rotate(2deg);
      box-shadow:var(--shadow);
    }
    .about-floating-timeline h3{
      color:var(--primary-hover);
      font-size:22px;
      margin-bottom:10px;
    }
    .about-floating-timeline .dash{
      border-top:2px dashed var(--border);
      margin:10px 0 16px;
    }
    .about-floating-timeline .period{
      text-align:center;
      font-weight:800;
      margin-bottom:14px;
      color:var(--text-muted);
    }
    .read-progress{
      width:100%;
      height:10px;
      border-radius:999px;
      background:#3a4148;
      overflow:hidden;
      margin-bottom:12px;
    }
    .read-progress span{
      display:block;
      width:0%;
      height:100%;
      background:linear-gradient(90deg, var(--primary), var(--primary-hover));
      border-radius:999px;
      transition:width .18s linear;
    }
    .read-label{
      text-align:center;
      font-weight:800;
      color:var(--text-muted);
    }

    .about-cards{
      position:relative;
      max-width:1040px;
      margin:0 auto;
      padding-top:24px;
    }
    .about-cards::before{
      content:"";
      position:absolute;
      left:50%;
      top:0;
      bottom:0;
      width:3px;
      background:linear-gradient(180deg, var(--primary-hover), var(--primary));
      transform:translateX(-50%);
      opacity:.85;
    }

    .about-item{
      position:relative;
      width:50%;
      padding:0 38px 56px;
    }
    .about-item.left{ left:0; }
    .about-item.right{ left:50%; }

    .about-dot{
      position:absolute;
      top:16px;
      width:26px;
      height:26px;
      border-radius:50%;
      background:#dbe8f8;
      border:5px solid var(--primary);
      box-shadow:0 0 0 14px rgba(13,112,179,.22);
      z-index:2;
    }
    .about-item.left .about-dot{ right:-13px; }
    .about-item.right .about-dot{ left:-13px; }

    .year-pill{
      display:inline-block;
      padding:11px 18px;
      border-radius:18px;
      background:var(--primary);
      color:#fff;
      font-weight:800;
      font-size:18px;
      margin-bottom:18px;
    }

    .about-card{
      background:linear-gradient(180deg, var(--bg-card), var(--bg-card-2));
      border:1px solid var(--border);
      border-radius:26px;
      padding:30px 30px 28px;
      box-shadow:var(--shadow);
      position:relative;
    }
    .about-card::after{
      content:"";
      position:absolute;
      top:34px;
      width:18px;
      height:18px;
      background:var(--bg-card);
      border-top:1px solid var(--border);
      border-right:1px solid var(--border);
      transform:rotate(45deg);
    }
    .about-item.left .about-card::after{ right:-10px; }
    .about-item.right .about-card::after{ left:-10px; }

    .about-card h3{ font-size:24px; margin-bottom:16px; }
    .about-card p{
      color:#d8dee7;
      line-height:1.85;
      font-size:17px;
    }

    .app-carousel{
      position:relative;
      max-width:1100px;
      margin:0 auto 26px;
      overflow:hidden;
      border-radius:28px;
    }
    .carousel-track{
      display:flex;
      transition:transform .45s ease;
    }
    .carousel-slide{
      min-width:100%;
      background:linear-gradient(180deg, var(--bg-card), var(--bg-card-2));
      border:1px solid var(--border);
      border-radius:28px;
      padding:34px 22px 28px;
      text-align:center;
      box-shadow:var(--shadow);
      min-height:680px;
      display:flex;
      flex-direction:column;
      align-items:center;
      justify-content:flex-start;
    }
    .carousel-slide img{
      width:100%;
      max-width:340px;
      border-radius:24px;
      margin-bottom:20px;
      box-shadow:0 16px 34px rgba(0,0,0,.35);
      border:1px solid var(--border);
      object-fit:contain;
    }
    .carousel-slide h3{ font-size:28px; margin-bottom:12px; }
    .carousel-slide p{
      font-size:18px;
      max-width:760px;
      color:#dae1ea;
      line-height:1.75;
    }

    .slide-wide{ padding:34px 28px 30px; }
    .slide-wide .wide-image{
      width:100%;
      max-width:980px;
      height:450px;
      object-fit:contain;
      border-radius:22px;
      margin-bottom:24px;
      background:#1a1d22;
    }

    .carousel-btn{
      position:absolute;
      top:50%;
      transform:translateY(-50%);
      width:54px;
      height:54px;
      border:none;
      border-radius:50%;
      background:var(--primary);
      color:#fff;
      font-size:30px;
      font-weight:bold;
      cursor:pointer;
      z-index:20;
      box-shadow:0 10px 22px rgba(0,0,0,.28);
    }
    .carousel-btn.prev{ left:14px; }
    .carousel-btn.next{ right:14px; }

    .carousel-dots{
      display:flex;
      justify-content:center;
      gap:12px;
    }
    .dot{
      width:12px;
      height:12px;
      border-radius:50%;
      background:rgba(255,255,255,.22);
      cursor:pointer;
      transition:.25s;
    }
    .dot.active{
      background:var(--primary-hover);
      transform:scale(1.16);
    }

    .faq{
      display:grid;
      gap:14px;
      max-width:900px;
      margin:0 auto;
    }
    .faq-item{
      background:linear-gradient(180deg, var(--bg-card), var(--bg-card-2));
      border:1px solid var(--border);
      border-radius:20px;
      padding:22px;
      box-shadow:var(--shadow);
    }
    .faq-item h3{ font-size:20px; margin-bottom:10px; }
    .faq-item p{
      color:var(--text-muted);
      line-height:1.8;
    }

    .contact-box{
      background:
        radial-gradient(circle at top right, rgba(13,112,179,.2), transparent 28%),
        linear-gradient(180deg, var(--bg-card), var(--bg-card-2));
      border:1px solid var(--border);
      border-radius:28px;
      padding:42px;
      box-shadow:var(--shadow);
      text-align:center;
    }
    .contact-box h2{
      font-size:clamp(30px, 4vw, 54px);
      margin-bottom:16px;
    }
    .contact-box h2 span{ color:var(--primary-hover); }
    .contact-box p{
      max-width:820px;
      margin:0 auto 26px;
      color:var(--text-muted);
      line-height:1.85;
      font-size:18px;
    }

    .contact-line{
      display:flex;
      justify-content:center;
      gap:20px;
      flex-wrap:wrap;
      color:#dce8fa;
      margin-top:22px;
    }

    .pill-row{
      display:flex;
      flex-wrap:wrap;
      gap:10px;
      margin-top:22px;
    }
    .pill{
      font-size:13px;
      font-weight:700;
      padding:8px 14px;
      border-radius:999px;
      border:1px solid var(--border);
      background:rgba(13,112,179,.12);
      color:#dbeafe;
    }

    footer{
      border-top:1px solid var(--border);
      padding:30px 0 40px;
      background:rgba(0,0,0,.2);
    }
    .footer-inner{
      display:flex;
      justify-content:space-between;
      gap:20px;
      flex-wrap:wrap;
    }
    .footer-left strong{
      display:block;
      font-size:18px;
      margin-bottom:8px;
    }
    .footer-left span{
      display:block;
      color:var(--text-muted);
      line-height:1.65;
    }
    .footer-right{
      display:flex;
      gap:16px;
      flex-wrap:wrap;
    }
    .footer-right a{ color:var(--text-muted); }
    .footer-right a:hover{ color:var(--primary-hover); }

    .calc-input,
    .calc-select{
      width:100%;
      padding:12px;
      border-radius:10px;
      border:1px solid var(--border);
      background:var(--bg-card-3);
      color:var(--text-main);
      margin-bottom:10px;
    }

    @media(max-width:1050px){
      .grid-2,
      .grid-3,
      .grid-4{ grid-template-columns:1fr 1fr; }

      .about-cards::before{
        left:24px;
        transform:none;
      }
      .about-item,
      .about-item.left,
      .about-item.right{
        width:100%;
        left:0;
        padding-left:72px;
        padding-right:0;
      }
      .about-item.left .about-dot,
      .about-item.right .about-dot{
        left:10px;
        right:auto;
      }
      .about-item.left .about-card::after,
      .about-item.right .about-card::after{
        left:-10px;
        right:auto;
      }
      .about-floating-timeline{
        margin:0 auto 24px;
        position:sticky;
        top:92px;
        max-width:360px;
      }
    }

    @media(max-width:900px){
      .nav-links{
        display:none;
        width:100%;
        flex-direction:column;
        align-items:flex-start;
        padding:14px 0 8px;
        gap:16px;
      }
      .nav-links.open{ display:flex; }
      .menu-toggle{ display:block; }
      .nav-inner{ flex-wrap:wrap; }
    }

    @media(max-width:760px){
      .grid-2,
      .grid-3,
      .grid-4,
      .mini-metrics{ grid-template-columns:1fr; }

      .page-box,
      .contact-box{ padding:28px 20px; }

      .page-box p.lead,
      .section-head p,
      .contact-box p{ font-size:17px; }

      .carousel-slide{
        min-height:auto;
        padding:22px 14px 20px;
      }
      .carousel-slide img{ max-width:270px; }
      .slide-wide .wide-image{
        max-width:100%;
        height:auto;
      }
      .carousel-btn{
        width:44px;
        height:44px;
        font-size:24px;
      }
      .logo img{ width:46px; height:46px; }
      .logo-text strong{ font-size:24px; }
      .about-wrapper{ padding-top:90px; }
    }
  </style>
</head>
<body>

  <nav class="nav">
    <div class="container nav-inner">
      <a href="/" class="logo">
        <img src="https://i.imgur.com/MLwyaEt.png" alt="Logo NIO HUB">
        <div class="logo-text">
          <strong>NIO HUB</strong>
          <span>TECNOLOGIA</span>
        </div>
      </a>

      <button class="menu-toggle" type="button" onclick="toggleMenu()">☰</button>

      <div class="nav-links" id="navLinks">
        <a href="/" class="${activePage === "inicio" ? "active" : ""}">Início</a>
        <a href="/sobre" class="${activePage === "sobre" ? "active" : ""}">Sobre Nós</a>
        <a href="/funcionalidades" class="${activePage === "funcionalidades" ? "active" : ""}">Funcionalidades</a>
        <a href="/demonstracao" class="${activePage === "demonstracao" ? "active" : ""}">Demonstração</a>
        <a href="/faq" class="${activePage === "faq" ? "active" : ""}">FAQ</a>
        <a href="/calculadora" class="${activePage === "calculadora" ? "active" : ""}">Calculadora WhatsApp</a>
        <a href="/contato" class="nav-cta ${activePage === "contato" ? "active" : ""}">Falar com a equipe</a>
      </div>
    </div>
  </nav>

  ${content}

  <footer>
    <div class="container footer-inner">
      <div class="footer-left">
        <strong>NIO HUB TECNOLOGIA</strong>
        <span>CNPJ: 63.864.720/0001-15</span>
        <span>contato@niohub.com.br</span>
      </div>

      <div class="footer-right">
        <a href="/">Início</a>
        <a href="/sobre">Sobre Nós</a>
        <a href="/funcionalidades">Funcionalidades</a>
        <a href="/demonstracao">Demonstração</a>
        <a href="/faq">FAQ</a>
        <a href="/calculadora">Calculadora</a>
        <a href="/contato">Contato</a>
      </div>
    </div>
  </footer>

  <script>
    function toggleMenu(){
      const nav = document.getElementById("navLinks");
      if (nav) nav.classList.toggle("open");
    }

    const progressBar = document.getElementById("aboutProgressBar");
    const progressLabel = document.getElementById("aboutProgressLabel");
    const aboutSection = document.getElementById("sobre-page");

    function updateAboutProgress(){
      if(!aboutSection || !progressBar || !progressLabel) return;

      const rect = aboutSection.getBoundingClientRect();
      const sectionHeight = aboutSection.offsetHeight;
      const viewportHeight = window.innerHeight;
      const totalScrollable = sectionHeight - viewportHeight;

      let progress = 0;

      if(rect.top >= 0){
        progress = 0;
      } else if(totalScrollable <= 0){
        progress = 100;
      } else {
        progress = Math.min(100, Math.max(0, ((-rect.top) / totalScrollable) * 100));
      }

      const rounded = Math.round(progress);
      progressBar.style.width = rounded + "%";
      progressLabel.textContent = rounded + "% percorrido";
    }

    window.addEventListener("scroll", updateAboutProgress);
    window.addEventListener("resize", updateAboutProgress);
    window.addEventListener("load", updateAboutProgress);

    let slideAtual = 0;
    const totalSlides = 5;

    function atualizarCarousel(){
      const track = document.getElementById("carouselTrack");
      const dots = document.querySelectorAll(".dot");
      if(!track || !dots.length) return;

      track.style.transform = "translateX(-" + (slideAtual * 100) + "%)";
      dots.forEach(dot => dot.classList.remove("active"));
      if (dots[slideAtual]) dots[slideAtual].classList.add("active");
    }

    function moverCarousel(direcao){
      slideAtual += direcao;

      if(slideAtual < 0) slideAtual = totalSlides - 1;
      if(slideAtual >= totalSlides) slideAtual = 0;

      atualizarCarousel();
    }

    function irParaSlide(indice){
      slideAtual = indice;
      atualizarCarousel();
    }

    document.querySelectorAll(".nav-links a").forEach(link => {
      link.addEventListener("click", () => {
        const nav = document.getElementById("navLinks");
        if (nav) nav.classList.remove("open");
      });
    });
  </script>
</body>
</html>`;
}

function renderInicio() {
  return `
<section class="page-hero">
  <div class="container">
    <div class="page-box">
      <span class="badge">100% focado em provedores de internet</span>
      <h1>Absolutamente tudo o que o seu provedor precisa para <span>crescer com tecnologia</span></h1>
      <div class="page-line"></div>
      <p class="lead">
        A NIO HUB une atendimento inteligente, aplicativo do cliente, automações operacionais,
        integrações com sistemas do setor e gestão técnica em uma única plataforma para o seu provedor
        vender mais, operar melhor e atender com mais eficiência.
      </p>
      <div class="pill-row" aria-label="Destaques recentes da plataforma">
        <span class="pill">Painel de atendimento unificado</span>
        <span class="pill">Chatbot com galeria e mídia</span>
        <span class="pill">Automação com inatividade do cliente</span>
      </div>
      <div class="hero-actions">
        <a href="/contato" class="btn btn-primary">Quero conhecer</a>
        <a href="/funcionalidades" class="btn btn-secondary">Ver soluções</a>
      </div>
    </div>
  </div>
</section>

<section class="section">
  <div class="container">
    <div class="section-head">
      <span class="badge">Ecossistema completo</span>
      <h2>Uma plataforma feita para o <span>provedor moderno</span></h2>
      <p>
        Atendimento, aplicativo, integrações e gestão técnica em uma experiência única e profissional —
        com evolução contínua alinhada ao que você já usa no dia a dia no sistema.
      </p>
    </div>

    <div class="grid-4">
      <div class="stat">
        <strong>24/7</strong>
        <p>Atendimento automatizado disponível a qualquer hora.</p>
      </div>

      <div class="stat">
        <strong>1 só lugar</strong>
        <p>Centralização de atendimento, cliente e operação.</p>
      </div>

      <div class="stat">
        <strong>+ controle</strong>
        <p>Mais visão sobre processos, chamados e rotinas.</p>
      </div>

      <div class="stat">
        <strong>+ eficiência</strong>
        <p>Menos trabalho manual e mais produtividade.</p>
      </div>
    </div>
  </div>
</section>
`;
}

function renderSobre() {
  return `
<section class="page-hero about-section" id="sobre-page">
  <div class="container">
    <div class="about-wrapper">
      <div class="about-floating-timeline">
        <h3>Linha do Tempo ⏳</h3>
        <div class="dash"></div>
        <div class="period">Leitura da página Sobre Nós</div>
        <div class="read-progress">
          <span id="aboutProgressBar"></span>
        </div>
        <div class="read-label" id="aboutProgressLabel">0% percorrido</div>
      </div>

      <div class="page-box" style="margin-bottom:34px;">
        <span class="badge">Sobre Nós</span>
        <h1>A evolução da <span>NIO HUB</span></h1>
        <div class="page-line"></div>
        <p class="lead">
          Conheça os momentos que marcam a construção da nossa trajetória e a visão de criar um hub de tecnologia
          pensado para a realidade dos provedores de internet.
        </p>
      </div>

      <div class="about-cards">
        <div class="about-item left">
          <div class="about-dot"></div>
          <span class="year-pill">2025</span>
          <div class="about-card">
            <h3>Onde tudo começou</h3>
            <p>
              A NIO HUB foi fundada em 2025 com o propósito de criar soluções modernas para o mercado de provedores,
              começando por uma plataforma de atendimento mais inteligente, organizada e preparada para automações.
            </p>
          </div>
        </div>

        <div class="about-item right">
          <div class="about-dot"></div>
          <span class="year-pill">2025</span>
          <div class="about-card">
            <h3>Evolução do produto</h3>
            <p>
              O projeto evoluiu para além do atendimento, passando a incluir aplicativo do cliente, integrações com
              sistemas do setor, recursos de auditoria e automações operacionais para entregar mais valor ao provedor.
            </p>
          </div>
        </div>

        <div class="about-item left">
          <div class="about-dot"></div>
          <span class="year-pill">Hoje</span>
          <div class="about-card">
            <h3>Hub de tecnologia</h3>
            <p>
              A NIO HUB consolida seu posicionamento como uma marca ampla, preparada para unir atendimento inteligente,
              TR-069, aplicativo do cliente, integrações e novas soluções digitais em um ecossistema moderno,
              profissional e escalável para provedores de internet.
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>
`;
}

function renderFuncionalidades() {
  return `
<section class="page-hero">
  <div class="container">
    <div class="page-box">
      <span class="badge">Funcionalidades</span>
      <h1>Um sistema tudo-em-um para <span>vender, operar e fidelizar</span></h1>
      <div class="page-line"></div>
      <p class="lead">
        Recursos essenciais para modernizar o seu provedor, fortalecer o canal próprio e dar mais autonomia ao cliente —
        alinhados ao que você encontra hoje no painel NIO HUB.
      </p>
    </div>
  </div>
</section>

<section class="section">
  <div class="container">
    <div class="grid-3">
      <div class="card">
        <div class="icon">💬</div>
        <h3>Atendimento Inteligente</h3>
        <p>Automatize respostas, direcione demandas e registre interações com muito mais organização.</p>
        <ul>
          <li>Triagem automática com IA</li>
          <li>Painel de conversas e métricas</li>
          <li>Abertura de chamados</li>
          <li>Histórico completo de conversas</li>
        </ul>
      </div>

      <div class="card">
        <div class="icon">🖼</div>
        <h3>Chatbot e mídia</h3>
        <p>Primeira impressão forte: envie imagens da galeria do provedor e mensagens ricas na automação.</p>
        <ul>
          <li>Galeria de imagens do provedor</li>
          <li>Mensagem inicial com mídia</li>
          <li>Fluxos visíveis e auditáveis</li>
        </ul>
      </div>

      <div class="card">
        <div class="icon">⏱</div>
        <h3>Automação por inatividade</h3>
        <p>Reaja quando o cliente para de responder: lembretes e próximos passos sem depender da equipe 100% do tempo.</p>
        <ul>
          <li>Regras por tempo sem resposta</li>
          <li>Menos conversas esquecidas</li>
          <li>Mais consistência no funil</li>
        </ul>
      </div>

      <div class="card">
        <div class="icon">📱</div>
        <h3>Aplicativo do Cliente</h3>
        <p>Entregue uma experiência prática para o assinante acessar serviços sem depender de atendimento manual.</p>
        <ul>
          <li>Consulta de faturas</li>
          <li>PIX e segunda via</li>
          <li>Notas fiscais</li>
          <li>Acesso rápido aos serviços</li>
        </ul>
      </div>

      <div class="card">
        <div class="icon">📡</div>
        <h3>TR-069 e Integrações</h3>
        <p>Ganhe produtividade com gestão técnica e conexão com os sistemas mais usados do mercado.</p>
        <ul>
          <li>Gestão de ONTs e roteadores</li>
          <li>Provisionamento</li>
          <li>Integração com SGP, MK Auth e IXCSoft</li>
          <li>Mais controle operacional</li>
        </ul>
      </div>

      <div class="card">
        <div class="icon">📊</div>
        <h3>Relatórios e Indicadores</h3>
        <p>Entenda o que está acontecendo na operação e acompanhe métricas importantes com mais clareza.</p>
        <ul>
          <li>Tempo de resposta</li>
          <li>Satisfação</li>
          <li>Taxa de resolução</li>
          <li>Auditoria de processos</li>
        </ul>
      </div>

      <div class="card">
        <div class="icon">🛡</div>
        <h3>Segurança e Governança</h3>
        <p>Estruture sua operação com mais controle, rastreabilidade e proteção de dados.</p>
        <ul>
          <li>Controle de acessos</li>
          <li>Logs e histórico</li>
          <li>Mais governança operacional</li>
          <li>Boas práticas de conformidade</li>
        </ul>
      </div>

      <div class="card">
        <div class="icon">⚙</div>
        <h3>Automação Operacional</h3>
        <p>Menos tarefas manuais, mais velocidade e um fluxo mais inteligente no dia a dia do provedor.</p>
        <ul>
          <li>Rotinas automatizadas</li>
          <li>Padronização de processos</li>
          <li>Redução de retrabalho</li>
          <li>Mais produtividade</li>
        </ul>
      </div>
    </div>
  </div>
</section>
`;
}

function renderDemonstracao() {
  return `
<section class="page-hero">
  <div class="container">
    <div class="page-box">
      <span class="badge">Demonstração</span>
      <h1>Veja nossas soluções em <span>funcionamento</span></h1>
      <div class="page-line"></div>
      <p class="lead">
        Uma visão rápida do aplicativo do cliente e do sistema técnico da NIO HUB.
      </p>
    </div>
  </div>
</section>

<section class="section">
  <div class="container">
    <div class="app-carousel">
      <button type="button" class="carousel-btn prev" onclick="moverCarousel(-1)">‹</button>

      <div class="carousel-track" id="carouselTrack">
        <div class="carousel-slide">
          <img src="https://i.imgur.com/vUUG0Gq.jpeg" alt="Tela de login">
          <h3>Tela de Login</h3>
          <p>Um acesso moderno, limpo e profissional para os clientes do provedor.</p>
        </div>

        <div class="carousel-slide">
          <img src="https://i.imgur.com/2gaRAHh.jpeg" alt="Tela home">
          <h3>Tela Home</h3>
          <p>Painel central do app com navegação intuitiva e foco nas funções mais usadas pelos assinantes.</p>
        </div>

        <div class="carousel-slide">
          <img src="https://i.imgur.com/DXd7Rfg.jpeg" alt="Tela minhas faturas">
          <h3>Minhas Faturas</h3>
          <p>Visualização rápida de cobranças, histórico financeiro e segunda via de forma simples e organizada.</p>
        </div>

        <div class="carousel-slide">
          <img src="https://i.imgur.com/1XXCKJ6.jpeg" alt="Tela nota fiscal">
          <h3>Nota Fiscal</h3>
          <p>Consulta rápida e estruturada das notas fiscais, trazendo mais autonomia e transparência ao cliente.</p>
        </div>

        <div class="carousel-slide slide-wide">
          <img src="https://i.imgur.com/v1TLgPh.jpeg" alt="Sistema TR-069" class="wide-image">
          <h3>Sistema TR-069</h3>
          <p>Gerenciamento técnico avançado para equipamentos, provisionamento e monitoramento da rede.</p>
        </div>
      </div>

      <button type="button" class="carousel-btn next" onclick="moverCarousel(1)">›</button>
    </div>

    <div class="carousel-dots">
      <span class="dot active" onclick="irParaSlide(0)"></span>
      <span class="dot" onclick="irParaSlide(1)"></span>
      <span class="dot" onclick="irParaSlide(2)"></span>
      <span class="dot" onclick="irParaSlide(3)"></span>
      <span class="dot" onclick="irParaSlide(4)"></span>
    </div>
  </div>
</section>
`;
}

function renderFaq() {
  return `
<section class="page-hero">
  <div class="container">
    <div class="page-box">
      <span class="badge">Perguntas frequentes</span>
      <h1>Tudo que você precisa <span>saber</span></h1>
      <div class="page-line"></div>
      <p class="lead">
        Respostas rápidas para dúvidas comuns sobre a proposta da plataforma.
      </p>
    </div>
  </div>
</section>

<section class="section">
  <div class="container">
    <div class="faq">
      <div class="faq-item">
        <h3>A NIO HUB é só uma plataforma de atendimento?</h3>
        <p>
          Não. A proposta é ser um hub de tecnologia para provedores, reunindo atendimento, aplicativo do cliente,
          automações, integrações e gestão técnica em um mesmo ecossistema.
        </p>
      </div>

      <div class="faq-item">
        <h3>O chatbot suporta imagens e galeria?</h3>
        <p>
          Sim. É possível usar a galeria do provedor e enriquecer a primeira interação com mídia, alinhado à experiência
          que seus clientes já esperam em canais modernos.
        </p>
      </div>

      <div class="faq-item">
        <h3>Posso usar a plataforma para melhorar a operação do meu provedor?</h3>
        <p>
          Sim. O foco é exatamente ajudar provedores a terem mais organização, mais controle e uma experiência mais moderna
          tanto para a equipe quanto para o assinante.
        </p>
      </div>

      <div class="faq-item">
        <h3>A solução pode evoluir com novos módulos?</h3>
        <p>
          Sim. A visão da NIO HUB é trabalhar como uma marca ampla, preparada para crescer com novos produtos e novas necessidades do mercado.
        </p>
      </div>

      <div class="faq-item">
        <h3>Como falo com a equipe?</h3>
        <p>
          Você pode entrar em contato por e-mail ou WhatsApp para entender melhor as soluções e a melhor forma de implantação.
        </p>
      </div>
    </div>
  </div>
</section>
`;
}

function renderCalculadora() {
  return `
<section class="page-hero">
  <div class="container">
    <div class="page-box">
      <span class="badge">Calculadora WhatsApp</span>
      <h1>Calcule seu custo com a <span>API Oficial</span></h1>
      <div class="page-line"></div>
      <p class="lead">
        Estime rapidamente o custo em reais com base na quantidade de mensagens e no tipo de conversa.
      </p>
    </div>
  </div>
</section>

<section class="section">
  <div class="container" style="max-width:520px;">
    <div class="card">
      <h3 style="margin-bottom:14px;">Calculadora WhatsApp API (Brasil)</h3>

      <button type="button" class="btn btn-primary" style="width:100%;margin-bottom:10px;" onclick="atualizarDolar()">Atualizar cotação do dólar</button>
      <div id="cotacao" style="margin-bottom:12px;color:var(--text-main);"></div>

      <input id="qtd" class="calc-input" placeholder="Quantidade de mensagens" disabled>

      <select id="tipo" class="calc-select" disabled>
        <option value="0.0625">Marketing — USD 0.0625</option>
        <option value="0.0068">Utilidade — USD 0.0068</option>
        <option value="0.0068">Autenticação — USD 0.0068</option>
      </select>

      <button type="button" class="btn btn-primary" style="width:100%;" onclick="calcular()" id="btnCalc" disabled>Calcular</button>
      <div id="resultado" style="color:var(--text-main);line-height:1.8;margin-top:14px;"></div>

      <small style="display:block;margin-top:12px;opacity:.8;font-size:12px;color:var(--text-muted)">
        *Valores estimados com base na tabela oficial da Meta para o Brasil.
      </small>
    </div>
  </div>
</section>

<script>
let dolar = null;

async function atualizarDolar(){
  try {
    const r = await fetch("https://economia.awesomeapi.com.br/json/last/USD-BRL");
    if (!r.ok) throw new Error("Falha na cotação");
    const d = await r.json();
    dolar = Number(d.USDBRL.bid);
    document.getElementById("cotacao").innerText = "Dólar atual: R$ " + dolar.toFixed(2);
    document.getElementById("qtd").disabled = false;
    document.getElementById("tipo").disabled = false;
    document.getElementById("btnCalc").disabled = false;
  } catch (e) {
    document.getElementById("cotacao").innerText = "Não foi possível obter a cotação. Tente novamente.";
  }
}

function calcular(){
  if (dolar == null || Number.isNaN(dolar)) return;
  const raw = document.getElementById("qtd").value.replace(/\\./g,"").replace(",",".");
  const qtd = Number(raw);
  const usd = qtd * Number(document.getElementById("tipo").value);
  const brl = Number((usd * dolar).toFixed(2));

  document.getElementById("resultado").innerHTML =
    "Mensagens: " + qtd.toLocaleString("pt-BR") + "<br>" +
    "Total USD: " + usd.toFixed(2) + "<br>" +
    "Total BRL: R$ " + brl.toLocaleString("pt-BR",{minimumFractionDigits:2});
}
<\/script>
`;
}

function renderContato() {
  return `
<section class="page-hero">
  <div class="container">
    <div class="contact-box">
      <span class="badge">Pronto para começar?</span>
      <h2>Leve o seu provedor para um novo nível com a <span>NIO HUB</span></h2>
      <p>
        Fale com nossa equipe, conheça as soluções e veja como a NIO HUB pode ajudar sua operação
        a crescer com mais tecnologia, mais controle e uma experiência mais forte para seus clientes.
      </p>

      <div class="hero-actions" style="justify-content:center;">
        <a href="mailto:contato@niohub.com.br" class="btn btn-primary">Enviar e-mail</a>
        <a href="https://wa.me/559431981266" target="_blank" rel="noopener noreferrer" class="btn btn-secondary">Falar no WhatsApp</a>
      </div>

      <div class="contact-line">
        <span>📧 contato@niohub.com.br</span>
        <span>📱 (94) 3198-1266</span>
      </div>
    </div>
  </div>
</section>
`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
