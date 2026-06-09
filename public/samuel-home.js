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
      "#sw-hub .eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#64748b;margin:0 0 18px}",
      "#sw-hub h1{font-family:Georgia,'Times New Roman',serif;font-size:18px;font-weight:600;line-height:1.4;margin:0 0 14px;letter-spacing:0;max-width:900px;color:#000}",
      "#sw-hub .lead{font-size:clamp(18px,2.1vw,24px);line-height:1.42;max-width:760px;margin:0 0 30px;color:#334155}",
      "#sw-hub .welcome{max-width:880px;margin:0 0 34px}",
      "#sw-hub .welcome p{font-size:18px;line-height:1.68;color:#334155;margin:0 0 15px}",
      "#sw-hub .links{display:flex;gap:14px;flex-wrap:wrap;margin:0 0 42px}",
      "#sw-hub a.btn{border:1px solid #111827;color:#111827;text-decoration:none;padding:13px 17px;font-size:14px;font-weight:600;display:inline-flex}",
      "#sw-hub a.primary{background:#111827;color:#fff}",
      "#sw-hub .section{border-top:1px solid #dbe4ef;padding:26px 0}",
      "#sw-hub .section-title{font-size:14px;letter-spacing:.12em;text-transform:uppercase;margin:0 0 18px;color:#64748b}",
      "#sw-hub .stack-section .section-title{color:#16a34a}",
      "#sw-hub .stack-section{margin-top:8px}",
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
      "#sw-hub .project .note{margin-top:13px;color:#475569}",
      "#sw-hub .tags{display:flex;gap:8px;flex-wrap:wrap;align-content:flex-start}",
      "#sw-hub .tag{border:1px solid #dbe4ef;padding:6px 9px;font-size:12px;color:#334155;background:#f1f5f9}",
      "#sw-hub .muted{color:#475569}",
      "#sw-hub .contact{border-top:1px solid #dbe4ef;margin-top:10px;padding-top:26px;font-size:15px;color:#334155}",
      "#sw-hub .contact a{color:#111827;text-decoration:underline;text-underline-offset:3px}",
      "@media(max-width:760px){#sw-hub{padding:62px 22px}#sw-hub .project,#sw-hub .split{grid-template-columns:1fr;gap:18px}}"
    ].join("");
    document.head.appendChild(style);
  }

  function renderHub() {
    var path = window.location.pathname.replace(/\/$/, "") || "/";
    if (path !== "/" && path !== "/home") return;
    var main = document.querySelector("main") || document.querySelector('[role="main"]');
    if (!main) return;
    var existingHub = document.getElementById("sw-hub");
    if (existingHub) {
      existingHub.parentNode.removeChild(existingHub);
    }
    Array.prototype.forEach.call(main.children, function (child) {
      child.style.display = "none";
    });
    main.insertAdjacentHTML(
      "afterbegin",
      '<section id="sw-hub"><div class="wrap">' +
        "<h1>Hello, I&rsquo;m Sam Wertheim.</h1>" +
        '<div class="welcome">' +
          '<p>I created this site to share the projects I am building with AI. I am a finance and accounting major at Lehigh University, with interests in artificial intelligence, history, and the stock market. I am currently interning at a venture capital firm focused on research and private investments, with an emphasis on deep technology.</p>' +
          '<p>These projects are personal, but they are also practice: a way to turn curiosity into working products. Some are more developed than others, but each one helps me learn how to research, write, code, test, and explain ideas more clearly. This site is where I keep track of what I am building, what I am learning, and how I am improving over time.</p>' +
        '</div>' +
        '<div class="links">' +
          '<a class="btn" href="https://www.linkedin.com/in/samuel-wertheim/" target="_blank" rel="noopener noreferrer">LinkedIn</a>' +
          '<a class="btn" href="mailto:wertheimsamuel12123@gmail.com">Email</a>' +
        "</div>" +
        '<section class="section" aria-label="Projects">' +
        '<p class="section-title">Projects</p>' +
        '<article class="project featured">' +
          "<div><h2>AlgoBall</h2>" +
          '<p>A daily MLB betting-market analysis project. AlgoBall builds its own pre-game moneyline probabilities, removes sportsbook vig, compares the model&rsquo;s price with the market price, and highlights model-vs-market divergences before games start.</p>' +
          '<p class="note">Built because baseball has deep public data, and because efficient betting markets make the problem genuinely difficult and interesting.</p>' +
          '<p style="margin-top:16px"><a class="btn" href="https://algoball.samuelwertheim.com/">View live project</a></p></div>' +
          '<div class="tags"><span class="tag">Python</span><span class="tag">MLB Stats API</span><span class="tag">Odds API</span><span class="tag">Railway</span><span class="tag">Daily refresh</span><span class="tag">Sports analytics</span></div>' +
        "</article>" +
        '<article class="project">' +
          '<div><h2>History Heave</h2>' +
          '<p>A history dating game. Players see a historical clue, such as a ruler, weapon, battle, map scenario, building, or invention, and guess when it is from by selecting a range of years. Narrower ranges score more when they are correct; broad guesses score less.</p>' +
          '<p class="note">Built with open historical data, curated date ranges, and image licensing checked before use.</p>' +
          '<p style="margin-top:16px"><a class="btn" href="https://history-heave-production.up.railway.app/">View live project</a></p></div>' +
          '<div class="tags"><span class="tag">Python</span><span class="tag">Wikidata</span><span class="tag">Wikimedia Commons</span><span class="tag">Vanilla JS</span><span class="tag">Railway</span><span class="tag">History game</span></div>' +
        "</article>" +
        '<article class="project">' +
          '<div><h2>Hindsight Bias</h2>' +
          '<p>A history decision game about the &ldquo;I knew it all along&rdquo; effect. Each round drops the player into a real historical decision with only the context people had at the time, then reveals what actually happened and why the obvious answer was not obvious in the moment.</p>' +
          '<p class="note">Built with spoiler-free scenarios, server-side answer grading, neutral sourcing, and a vanilla JavaScript frontend deployed on Railway.</p>' +
          '<p style="margin-top:16px"><a class="btn" href="https://hindsight-bias-production.up.railway.app/">View live project</a></p></div>' +
          '<div class="tags"><span class="tag">History game</span><span class="tag">Decision-making</span><span class="tag">Python</span><span class="tag">Vanilla JS</span><span class="tag">Railway</span><span class="tag">Live project</span></div>' +
        "</article>" +
        '<article class="project">' +
          '<div><h2>Freedom Tell</h2>' +
          '<p>An open-source intelligence news project. Freedom Tell tracks public information, organizes signals from open sources, and turns scattered news and research into a clearer way to follow developing stories.</p>' +
          '<p class="note">Built as a research-focused news tool: collect public information, make sense of it, and present it clearly.</p>' +
          '<p style="margin-top:16px"><a class="btn" href="https://freedomtell-production.up.railway.app/">View live project</a></p></div>' +
          '<div class="tags"><span class="tag">OSINT</span><span class="tag">News</span><span class="tag">AI research</span><span class="tag">Open sources</span><span class="tag">Live project</span></div>' +
        "</article>" +
        '<article class="project">' +
          '<div><h2>VacayAI</h2>' +
          '<p>An AI vacation planner. VacayAI takes dates, a destination or region, and travel preferences, then builds a realistic day-by-day itinerary scored to the user&rsquo;s taste. It does not book the trip; it organizes flight, hotel, and activity links so the user can book independently.</p>' +
          '<p class="note">Built around preference scoring, itinerary structure, booking-link generation, and a simple Railway deployment.</p>' +
          '<p style="margin-top:16px"><a class="btn" href="https://vacayai-production.up.railway.app/">View live project</a></p></div>' +
          '<div class="tags"><span class="tag">AI planner</span><span class="tag">Travel</span><span class="tag">Python</span><span class="tag">Vanilla JS</span><span class="tag">Railway</span><span class="tag">Live project</span></div>' +
        "</article>" +
        '<article class="project">' +
          '<div><h2>Basketball Whiteboard</h2>' +
          '<p>A work-in-progress basketball strategy game. The idea is to make the player feel like a coach drawing on a whiteboard: control all five players from above, sketch movement paths, pass, shoot, and try to beat a reacting AI defense before the shot clock runs out.</p>' +
          '<p class="note">Currently being built as a browser game with a vanilla JavaScript Canvas frontend, a lightweight Python server, all-time player ratings, scrimmage mode, and an early career-mode structure.</p></div>' +
          '<div class="tags"><span class="tag">Work in progress</span><span class="tag">Basketball game</span><span class="tag">Canvas</span><span class="tag">Vanilla JS</span><span class="tag">Python</span><span class="tag">AI defense</span></div>' +
        "</article>" +
        '<article class="project">' +
          '<div><h2>What this site is for</h2><p class="muted">A public place to track what I am learning and building. When an idea becomes real, useful, or interesting enough to share, it belongs here.</p></div>' +
          '<div class="tags"><span class="tag">Experiments</span><span class="tag">Learning by building</span><span class="tag">Personal projects</span></div>' +
        '</article></section>' +
        '<section class="section stack-section">' +
          '<p class="section-title">Stack so far</p>' +
          '<div class="entry"><h3>Python, data, web, games, deployment</h3><p>Python, APIs, model logic, vanilla JavaScript, Canvas, browser-game mechanics, GitHub, Railway, static dashboards, lightweight web deployment, and testing against real data. The stack keeps changing as the projects become more ambitious.</p></div>' +
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
    hideNativeHeaderBrand();
    addStyles();
    renderHub();
    hideNativeHeaderBrand();
    var attempts = 0;
    var timer = window.setInterval(function () {
      attempts += 1;
      removeStrayCodeText();
      renderHub();
      hideNativeHeaderBrand();
      if (document.getElementById("sw-hub") || attempts >= 20) {
        window.clearInterval(timer);
      }
    }, 250);
  });
}());
