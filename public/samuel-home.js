(function () {
  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  function replaceExact(from, to) {
    document.querySelectorAll("h1,h2,h3,p,a,span,div").forEach(function (el) {
      if ((el.textContent || "").trim() === from) {
        el.textContent = to;
      }
    });
  }

  function removeStrayCodeText() {
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    var nodes = [];
    while (walker.nextNode()) {
      if ((walker.currentNode.nodeValue || "").trim() === "script>") {
        nodes.push(walker.currentNode);
      }
    }
    nodes.forEach(function (node) {
      node.parentNode.removeChild(node);
    });
  }

  function addStyles() {
    if (document.getElementById("sw-hub-style")) return;
    var style = document.createElement("style");
    style.id = "sw-hub-style";
    style.textContent = [
      "#sw-hub{background:#f5f1ea;color:#151515;padding:92px 6vw 76px;min-height:72vh}",
      "#sw-hub *{box-sizing:border-box}",
      "#sw-hub .wrap{max-width:1080px;margin:0 auto}",
      "#sw-hub .eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#766d63;margin:0 0 22px}",
      "#sw-hub h1{font-size:clamp(46px,8vw,96px);line-height:.92;margin:0 0 24px;letter-spacing:0;max-width:920px}",
      "#sw-hub .lead{font-size:clamp(18px,2.2vw,25px);line-height:1.42;max-width:790px;margin:0 0 34px;color:#36312b}",
      "#sw-hub .links{display:flex;gap:14px;flex-wrap:wrap;margin:0 0 58px}",
      "#sw-hub a.btn{border:1px solid #151515;color:#151515;text-decoration:none;padding:13px 17px;font-size:14px;font-weight:600;display:inline-flex}",
      "#sw-hub a.primary{background:#151515;color:#fff}",
      "#sw-hub .section{border-top:1px solid #cfc6b8;padding:30px 0}",
      "#sw-hub .section-title{font-size:14px;letter-spacing:.12em;text-transform:uppercase;margin:0 0 18px;color:#645c53}",
      "#sw-hub .bio{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(260px,.8fr);gap:38px}",
      "#sw-hub .bio p,#sw-hub li{font-size:16px;line-height:1.62;color:#3d3731}",
      "#sw-hub .bio p{margin:0 0 15px}",
      "#sw-hub .facts{display:grid;gap:14px}",
      "#sw-hub .fact{background:#fffaf3;border:1px solid #d7d0c4;padding:16px}",
      "#sw-hub .fact strong{display:block;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#756d63;margin-bottom:7px}",
      "#sw-hub .fact span{font-size:16px;color:#151515}",
      "#sw-hub .split{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:30px}",
      "#sw-hub .entry h3{font-size:22px;margin:0 0 7px}",
      "#sw-hub .entry p{font-size:15.5px;line-height:1.58;color:#3d3731;margin:0 0 10px}",
      "#sw-hub ul{padding-left:20px;margin:12px 0 0}",
      "#sw-hub .project{border-top:1px solid #cfc6b8;padding:26px 0 30px;display:grid;grid-template-columns:minmax(0,1fr) minmax(220px,320px);gap:30px}",
      "#sw-hub .project h2{font-size:30px;line-height:1.05;margin:0 0 10px}",
      "#sw-hub .project p{font-size:16px;line-height:1.58;margin:0;color:#3d3731}",
      "#sw-hub .tags{display:flex;gap:8px;flex-wrap:wrap;align-content:flex-start}",
      "#sw-hub .tag{border:1px solid #d4cabd;padding:6px 9px;font-size:12px;color:#5c534a;background:#fffaf3}",
      "#sw-hub .muted{color:#756d63}",
      "#sw-hub .contact{border-top:1px solid #cfc6b8;margin-top:10px;padding-top:26px;font-size:15px;color:#3d3731}",
      "#sw-hub .contact a{color:#151515;text-decoration:underline;text-underline-offset:3px}",
      "@media(max-width:760px){#sw-hub{padding:64px 22px}#sw-hub .project,#sw-hub .bio,#sw-hub .split{grid-template-columns:1fr;gap:18px}#sw-hub h1{font-size:48px}}"
    ].join("");
    document.head.appendChild(style);
  }

  function renderHub() {
    var path = window.location.pathname.replace(/\/$/, "") || "/";
    if (path !== "/" && path !== "/home") return;
    var main = document.querySelector("main") || document.querySelector('[role="main"]');
    if (!main || document.getElementById("sw-hub")) return;
    Array.prototype.forEach.call(main.children, function (child) {
      child.style.display = "none";
    });
    main.insertAdjacentHTML(
      "afterbegin",
      '<section id="sw-hub"><div class="wrap">' +
        '<p class="eyebrow">Projects / analytics / applied AI</p>' +
        "<h1>Samuel Wertheim Projects</h1>" +
        '<p class="lead">I am a Lehigh business student building practical software, sports analytics, and AI-assisted tools because I genuinely enjoy making ideas real.</p>' +
        '<div class="links">' +
          '<a class="btn primary" href="https://algoball.samuelwertheim.com/">Open AlgoBall</a>' +
          '<a class="btn" href="https://www.linkedin.com/in/samuel-wertheim/" target="_blank" rel="noopener noreferrer">LinkedIn</a>' +
          '<a class="btn" href="mailto:wertheimsamuel12123@gmail.com">Email</a>' +
        "</div>" +
        '<section class="section bio"><div>' +
          '<p class="section-title">About</p>' +
          '<p>I am interested in the intersection of finance, data, and AI. This site is a home base for the things I am building on my own time: projects that start as ideas I want to understand better, then become working products.</p>' +
          '<p>The emphasis is learning by doing. I am using AI as a creative and technical partner: to move faster, test ideas, write better code, pressure-test assumptions, and build things that would have been out of reach without these tools.</p>' +
          '<p>This is not a polished corporate portfolio pretending every experiment is a finished company. It is a live record of projects I care about, built by choice, curiosity, and repetition.</p>' +
        '</div><div class="facts">' +
          '<div class="fact"><strong>School</strong><span>Lehigh University College of Business</span></div>' +
          '<div class="fact"><strong>Focus</strong><span>Finance and Accounting major; History minor</span></div>' +
          '<div class="fact"><strong>Current work</strong><span>Northwell Health</span></div>' +
          '<div class="fact"><strong>Interests</strong><span>Markets, sports analytics, AI tools, data systems, history</span></div>' +
        '</div></section>' +
        '<section class="section split">' +
          '<div class="entry"><p class="section-title">Education</p><h3>Lehigh University College of Business</h3><p>Finance and Accounting major with a History minor. Activities include Investment Management Group, Investment Banking Club, AEPI, Scholars of Finance, and Dean\'s List.</p></div>' +
          '<div class="entry"><p class="section-title">Work</p><h3>Northwell Health</h3><p>Current professional experience listed on LinkedIn. This site connects that business background with hands-on technical building and AI-assisted project work.</p></div>' +
        '</section>' +
        '<section class="section"><p class="section-title">Selected Projects</p>' +
        '<article class="project">' +
          "<div><h2>AlgoBall</h2>" +
          '<p>Daily MLB betting-market analysis. AlgoBall builds its own pre-game moneyline probabilities, removes sportsbook vig, compares model price against market price, and highlights only the clearest model-vs-market divergences before games start.</p>' +
          '<p style="margin-top:16px"><a class="btn" href="https://algoball.samuelwertheim.com/">View live project</a></p></div>' +
          '<div class="tags"><span class="tag">Python</span><span class="tag">MLB Stats API</span><span class="tag">Odds API</span><span class="tag">Railway</span><span class="tag">Daily refresh</span></div>' +
        "</article>" +
        '<article class="project">' +
          "<div><h2>Next Project</h2>" +
          '<p class="muted">A second project is in progress. The goal is to keep building things I actually want to use, then add the best ones here as they become real.</p></div>' +
          '<div class="tags"><span class="tag">AI-assisted</span><span class="tag">In progress</span><span class="tag">Coming soon</span></div>' +
        "</article></section>" +
        '<section class="section split">' +
          '<div class="entry"><p class="section-title">How I build</p><h3>AI as leverage, not decoration</h3><p>I use AI to explore, code, debug, research, and iterate faster. The point is not to make projects look artificially impressive; the point is to get better at turning curiosity into working systems.</p></div>' +
          '<div class="entry"><p class="section-title">Stack so far</p><h3>Python, data, web, deployment</h3><p>Python, APIs, model logic, GitHub, Railway, static dashboards, lightweight web deployment, and the habit of testing whether an idea survives contact with real data.</p></div>' +
        '</section>' +
        '<p class="contact">Contact: <a href="mailto:wertheimsamuel12123@gmail.com">wertheimsamuel12123@gmail.com</a> / <a href="https://www.linkedin.com/in/samuel-wertheim/" target="_blank" rel="noopener noreferrer">LinkedIn</a></p>' +
      "</div></section>"
    );
  }

  ready(function () {
    document.title = "Samuel Wertheim Projects";
    removeStrayCodeText();
    replaceExact("Samuel Wertheim projects", "Samuel Wertheim");
    replaceExact("Your Site Title", "Samuel Wertheim");
    replaceExact("email@example.com", "wertheimsamuel12123@gmail.com");
    addStyles();
    renderHub();
  });
}());
