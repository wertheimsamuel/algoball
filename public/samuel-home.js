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
      "#sw-hub{background:#f5f1ea;color:#151515;padding:84px 6vw 72px;min-height:72vh}",
      "#sw-hub *{box-sizing:border-box}",
      "#sw-hub .wrap{max-width:1080px;margin:0 auto}",
      "#sw-hub .eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#766d63;margin:0 0 18px}",
      "#sw-hub h1{font-size:clamp(48px,8vw,92px);line-height:.92;margin:0 0 22px;letter-spacing:0;max-width:900px}",
      "#sw-hub .lead{font-size:clamp(18px,2.1vw,24px);line-height:1.42;max-width:760px;margin:0 0 30px;color:#36312b}",
      "#sw-hub .links{display:flex;gap:14px;flex-wrap:wrap;margin:0 0 42px}",
      "#sw-hub a.btn{border:1px solid #151515;color:#151515;text-decoration:none;padding:13px 17px;font-size:14px;font-weight:600;display:inline-flex}",
      "#sw-hub a.primary{background:#151515;color:#fff}",
      "#sw-hub .tabs{display:flex;gap:8px;border-bottom:1px solid #cfc6b8;margin:0 0 12px}",
      "#sw-hub .tab{appearance:none;border:0;border-bottom:2px solid transparent;background:transparent;color:#71685e;padding:14px 2px 12px;margin:0 22px 0 0;font:inherit;font-size:15px;font-weight:650;cursor:pointer}",
      "#sw-hub .tab.active{color:#151515;border-bottom-color:#151515}",
      "#sw-hub .panel{display:none}",
      "#sw-hub .panel.active{display:block}",
      "#sw-hub .section{border-top:1px solid #cfc6b8;padding:26px 0}",
      "#sw-hub .section-title{font-size:14px;letter-spacing:.12em;text-transform:uppercase;margin:0 0 18px;color:#645c53}",
      "#sw-hub .bio{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(260px,.85fr);gap:34px}",
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
      "#sw-hub .project{border-top:1px solid #cfc6b8;padding:28px 0 32px;display:grid;grid-template-columns:minmax(0,1fr) minmax(220px,320px);gap:30px}",
      "#sw-hub .project.featured{border-top:0;padding-top:24px}",
      "#sw-hub .project h2{font-size:32px;line-height:1.05;margin:0 0 10px}",
      "#sw-hub .project p{font-size:16px;line-height:1.58;margin:0;color:#3d3731}",
      "#sw-hub .project .note{margin-top:13px;color:#645c53}",
      "#sw-hub .tags{display:flex;gap:8px;flex-wrap:wrap;align-content:flex-start}",
      "#sw-hub .tag{border:1px solid #d4cabd;padding:6px 9px;font-size:12px;color:#5c534a;background:#fffaf3}",
      "#sw-hub .muted{color:#756d63}",
      "#sw-hub .contact{border-top:1px solid #cfc6b8;margin-top:10px;padding-top:26px;font-size:15px;color:#3d3731}",
      "#sw-hub .contact a{color:#151515;text-decoration:underline;text-underline-offset:3px}",
      "@media(max-width:760px){#sw-hub{padding:62px 22px}#sw-hub .project,#sw-hub .bio,#sw-hub .split{grid-template-columns:1fr;gap:18px}#sw-hub h1{font-size:48px}#sw-hub .tabs{gap:0}#sw-hub .tab{margin-right:18px}}"
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
        '<p class="eyebrow">Projects / AI / finance / sports data</p>' +
        "<h1>Samuel Wertheim</h1>" +
        '<p class="lead">I use AI and code to build things I actually want to use: market tools, sports models, small experiments, and whatever idea keeps pulling me back.</p>' +
        '<div class="links">' +
          '<a class="btn primary" href="https://algoball.samuelwertheim.com/">Open AlgoBall</a>' +
          '<a class="btn" href="https://www.linkedin.com/in/samuel-wertheim/" target="_blank" rel="noopener noreferrer">LinkedIn</a>' +
          '<a class="btn" href="mailto:wertheimsamuel12123@gmail.com">Email</a>' +
        "</div>" +
        '<div class="tabs" role="tablist" aria-label="Site sections">' +
          '<button class="tab active" type="button" data-tab="projects" role="tab" aria-selected="true">Projects</button>' +
          '<button class="tab" type="button" data-tab="about" role="tab" aria-selected="false">About</button>' +
        '</div>' +
        '<section class="panel active" data-panel="projects" role="tabpanel">' +
        '<article class="project featured">' +
          "<div><h2>AlgoBall</h2>" +
          '<p>Daily MLB betting-market analysis. AlgoBall builds its own pre-game moneyline probabilities, removes sportsbook vig, compares model price against market price, and highlights only the clearest model-vs-market divergences before games start.</p>' +
          '<p class="note">Built because baseball has deep public data, betting markets are hard to beat, and that makes the problem interesting.</p>' +
          '<p style="margin-top:16px"><a class="btn" href="https://algoball.samuelwertheim.com/">View live project</a></p></div>' +
          '<div class="tags"><span class="tag">Python</span><span class="tag">MLB Stats API</span><span class="tag">Odds API</span><span class="tag">Railway</span><span class="tag">Daily refresh</span><span class="tag">Sports analytics</span></div>' +
        "</article>" +
        '<article class="project">' +
          '<div><h2>Next Build</h2>' +
          '<p class="muted">A second project is in progress. The goal is to keep adding projects that are personal, useful, or just fun enough to be worth finishing.</p></div>' +
          '<div class="tags"><span class="tag">AI-assisted</span><span class="tag">In progress</span><span class="tag">Coming soon</span></div>' +
        "</article>" +
        '<article class="project">' +
          '<div><h2>What this site is for</h2><p class="muted">A public place to keep track of what I am learning and building. If something becomes real, useful, or interesting, it gets added here.</p></div>' +
          '<div class="tags"><span class="tag">Experiments</span><span class="tag">Learning by building</span><span class="tag">Personal projects</span></div>' +
        '</article></section>' +
        '<section class="panel" data-panel="about" role="tabpanel">' +
        '<section class="section bio"><div>' +
          '<p class="section-title">About</p>' +
          '<p>I am a Lehigh business student interested in finance, data, sports, history, and the new ways AI can help people build faster.</p>' +
          '<p>This site is intentionally simple. I am not trying to make every experiment sound like a startup. I am using AI, code, and curiosity to build things I want to understand better.</p>' +
          '<p>The point is to get good at the process: research, design, build, test, break, fix, and keep going.</p>' +
        '</div><div class="facts">' +
          '<div class="fact"><strong>School</strong><span>Lehigh University College of Business</span></div>' +
          '<div class="fact"><strong>Focus</strong><span>Finance and Accounting major; History minor</span></div>' +
          '<div class="fact"><strong>Current work</strong><span>Northwell Health</span></div>' +
          '<div class="fact"><strong>Interests</strong><span>Markets, baseball analytics, AI coding tools, history</span></div>' +
        '</div></section>' +
        '<section class="section split">' +
          '<div class="entry"><p class="section-title">Education</p><h3>Lehigh University College of Business</h3><p>Finance and Accounting major with a History minor. Activities include Investment Management Group, Investment Banking Club, AEPI, Scholars of Finance, and Dean\'s List.</p></div>' +
          '<div class="entry"><p class="section-title">Work</p><h3>Northwell Health</h3><p>Current professional experience listed on LinkedIn. This site connects that business background with hands-on technical building and AI-assisted project work.</p></div>' +
        '</section>' +
        '<section class="section split">' +
          '<div class="entry"><p class="section-title">How I build</p><h3>AI as a real tool</h3><p>I use AI to research, code, debug, organize ideas, and move from a rough thought to a working product faster. The goal is not polish for polish\'s sake. It is learning through finished artifacts.</p></div>' +
          '<div class="entry"><p class="section-title">Stack so far</p><h3>Python, data, web, deployment</h3><p>Python, APIs, model logic, GitHub, Railway, static dashboards, lightweight web deployment, and testing ideas against real data.</p></div>' +
        '</section>' +
        '</section>' +
        '<p class="contact">Contact: <a href="mailto:wertheimsamuel12123@gmail.com">wertheimsamuel12123@gmail.com</a> / <a href="https://www.linkedin.com/in/samuel-wertheim/" target="_blank" rel="noopener noreferrer">LinkedIn</a></p>' +
      "</div></section>"
    );
    document.querySelectorAll("#sw-hub .tab").forEach(function (button) {
      button.addEventListener("click", function () {
        var target = button.getAttribute("data-tab");
        document.querySelectorAll("#sw-hub .tab").forEach(function (tab) {
          var active = tab === button;
          tab.classList.toggle("active", active);
          tab.setAttribute("aria-selected", active ? "true" : "false");
        });
        document.querySelectorAll("#sw-hub .panel").forEach(function (panel) {
          panel.classList.toggle("active", panel.getAttribute("data-panel") === target);
        });
      });
    });
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
