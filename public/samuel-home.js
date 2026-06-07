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

  function hideNativeHeaderBrand() {
    document.querySelectorAll("header a, header span, header div").forEach(function (el) {
      if ((el.textContent || "").trim() === "Samuel Wertheim") {
        el.style.display = "none";
      }
    });
  }

  function addStyles() {
    if (document.getElementById("sw-hub-style")) return;
    var style = document.createElement("style");
    style.id = "sw-hub-style";
    style.textContent = [
      "#sw-hub{background:#f8fafc;color:#111827;padding:84px 6vw 72px;min-height:72vh}",
      "#sw-hub *{box-sizing:border-box}",
      "#sw-hub .wrap{max-width:1080px;margin:0 auto}",
      "#sw-hub .eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#2563eb;margin:0 0 18px}",
      "#sw-hub h1{font-family:Georgia,'Times New Roman',serif;font-size:18px;font-weight:600;line-height:1.4;margin:0 0 14px;letter-spacing:0;max-width:900px;color:#000}",
      "#sw-hub .lead{font-size:clamp(18px,2.1vw,24px);line-height:1.42;max-width:760px;margin:0 0 30px;color:#334155}",
      "#sw-hub .welcome{max-width:840px;margin:0 0 34px;border-left:3px solid #2563eb;padding-left:20px}",
      "#sw-hub .welcome p{font-size:18px;line-height:1.64;color:#334155;margin:0}",
      "#sw-hub .links{display:flex;gap:14px;flex-wrap:wrap;margin:0 0 42px}",
      "#sw-hub a.btn{border:1px solid #111827;color:#111827;text-decoration:none;padding:13px 17px;font-size:14px;font-weight:600;display:inline-flex}",
      "#sw-hub a.primary{background:#111827;color:#fff}",
      "#sw-hub .tabs{display:flex;gap:8px;border-bottom:1px solid #dbe4ef;margin:0 0 12px}",
      "#sw-hub .tab{appearance:none;border:0;border-bottom:2px solid transparent;background:transparent;color:#64748b;padding:14px 2px 12px;margin:0 22px 0 0;font:inherit;font-size:15px;font-weight:650;cursor:pointer}",
      "#sw-hub .tab.active{color:#111827;border-bottom-color:#111827}",
      "#sw-hub .panel{display:none}",
      "#sw-hub .panel.active{display:block}",
      "#sw-hub .section{border-top:1px solid #dbe4ef;padding:26px 0}",
      "#sw-hub .section-title{font-size:14px;letter-spacing:.12em;text-transform:uppercase;margin:0 0 18px;color:#2563eb}",
      "#sw-hub .bio{max-width:900px}",
      "#sw-hub .bio p,#sw-hub li{font-size:16px;line-height:1.62;color:#334155}",
      "#sw-hub .bio p{margin:0 0 15px}",
      "#sw-hub .split{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:30px}",
      "#sw-hub .entry h3{font-size:22px;margin:0 0 7px}",
      "#sw-hub .entry p{font-size:15.5px;line-height:1.58;color:#334155;margin:0 0 10px}",
      "#sw-hub ul{padding-left:20px;margin:12px 0 0}",
      "#sw-hub .project{border-top:1px solid #dbe4ef;padding:28px 0 32px;display:grid;grid-template-columns:minmax(0,1fr) minmax(220px,320px);gap:30px}",
      "#sw-hub .project.featured{border-top:0;padding-top:24px}",
      "#sw-hub .project h2{font-size:32px;line-height:1.05;margin:0 0 10px}",
      "#sw-hub .project p{font-size:16px;line-height:1.58;margin:0;color:#334155}",
      "#sw-hub .project .note{margin-top:13px;color:#2563eb}",
      "#sw-hub .tags{display:flex;gap:8px;flex-wrap:wrap;align-content:flex-start}",
      "#sw-hub .tag{border:1px solid #bfdbfe;padding:6px 9px;font-size:12px;color:#1e3a8a;background:#eff6ff}",
      "#sw-hub .muted{color:#475569}",
      "#sw-hub .contact{border-top:1px solid #dbe4ef;margin-top:10px;padding-top:26px;font-size:15px;color:#334155}",
      "#sw-hub .contact a{color:#111827;text-decoration:underline;text-underline-offset:3px}",
      "@media(max-width:760px){#sw-hub{padding:62px 22px}#sw-hub .project,#sw-hub .split{grid-template-columns:1fr;gap:18px}#sw-hub .tabs{gap:0}#sw-hub .tab{margin-right:18px}}"
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
        '<p class="eyebrow">AI Projects</p>' +
        "<h1>Hello, I am Sam Wertheim.</h1>" +
        '<div class="welcome"><p>This site is purely for fun, engagement, and practice with AI so I can keep getting better at building things. Some projects go deep while some may be more shallow, but all of them are built on my own time because I enjoy the process. I am using this as a place to learn.</p></div>' +
        '<div class="links">' +
          '<a class="btn primary" href="https://algoball.samuelwertheim.com/">Open AlgoBall</a>' +
          '<a class="btn" href="https://www.linkedin.com/in/samuel-wertheim/" target="_blank" rel="noopener noreferrer">LinkedIn</a>' +
          '<a class="btn" href="mailto:wertheimsamuel12123@gmail.com">Email</a>' +
        "</div>" +
        '<div class="tabs" role="tablist" aria-label="Site sections">' +
          '<button class="tab active" type="button" data-tab="about" role="tab" aria-selected="true">About</button>' +
          '<button class="tab" type="button" data-tab="projects" role="tab" aria-selected="false">Projects</button>' +
        '</div>' +
        '<section class="panel active" data-panel="about" role="tabpanel">' +
        '<section class="section bio">' +
          '<p class="section-title">About</p>' +
          '<p>I am a finance and accounting major from Lehigh University with a deep interest in artificial intelligence, history, and the stock market. I am currently interning for a venture capital firm focused on research and private investments, which has pushed me to think more seriously about how ideas become companies, how capital gets allocated, and how technology changes the way people make decisions.</p>' +
          '<p>This site is a place for the projects I build on my own time. Some are more complete, some are lighter experiments, and some are just me following an idea far enough to see what it can become. The point is not to make every project sound bigger than it is. The point is to keep practicing, keep learning, and keep using AI and code to build things that interest me.</p>' +
        '</section>' +
        '<section class="section split">' +
          '<div class="entry"><p class="section-title">Why AI</p><h3>AI makes building feel wide open</h3><p>AI is incredible because it lowers the distance between having an idea and actually trying it. It helps with research, writing, coding, debugging, planning, and learning new concepts fast enough to keep momentum. Used well, it feels like a force multiplier: one person can explore more, build faster, and turn curiosity into something real.</p></div>' +
          '<div class="entry"><p class="section-title">Stack so far</p><h3>Python, data, web, deployment</h3><p>Python, APIs, model logic, GitHub, Railway, static dashboards, lightweight web deployment, and testing ideas against real data. The stack will keep changing as the projects get better.</p></div>' +
        '</section>' +
        '</section>' +
        '<section class="panel" data-panel="projects" role="tabpanel">' +
        '<article class="project featured">' +
          "<div><h2>AlgoBall</h2>" +
          '<p>Daily MLB betting-market analysis. AlgoBall builds its own pre-game moneyline probabilities, removes sportsbook vig, compares model price against market price, and highlights only the clearest model-vs-market divergences before games start.</p>' +
          '<p class="note">Built because baseball has deep public data, betting markets are hard to beat, and that makes the problem interesting.</p>' +
          '<p style="margin-top:16px"><a class="btn" href="https://algoball.samuelwertheim.com/">View live project</a></p></div>' +
          '<div class="tags"><span class="tag">Python</span><span class="tag">MLB Stats API</span><span class="tag">Odds API</span><span class="tag">Railway</span><span class="tag">Daily refresh</span><span class="tag">Sports analytics</span></div>' +
        "</article>" +
        '<article class="project">' +
          '<div><h2>History Heave</h2>' +
          '<p class="muted">A second project is in progress. The goal is to keep adding projects that are personal, useful, or just fun enough to be worth finishing.</p></div>' +
          '<div class="tags"><span class="tag">AI-assisted</span><span class="tag">In progress</span><span class="tag">Coming soon</span></div>' +
        "</article>" +
        '<article class="project">' +
          '<div><h2>What this site is for</h2><p class="muted">A public place to keep track of what I am learning and building. If something becomes real, useful, or interesting, it gets added here.</p></div>' +
          '<div class="tags"><span class="tag">Experiments</span><span class="tag">Learning by building</span><span class="tag">Personal projects</span></div>' +
        '</article></section>' +
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
    hideNativeHeaderBrand();
    addStyles();
    renderHub();
    hideNativeHeaderBrand();
  });
}());
