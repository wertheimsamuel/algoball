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
      "#sw-hub .links{display:flex;gap:14px;flex-wrap:wrap;margin:0 0 66px}",
      "#sw-hub a.btn{border:1px solid #151515;color:#151515;text-decoration:none;padding:13px 17px;font-size:14px;font-weight:600;display:inline-flex}",
      "#sw-hub a.primary{background:#151515;color:#fff}",
      "#sw-hub .section-title{font-size:14px;letter-spacing:.12em;text-transform:uppercase;margin:0 0 18px;color:#645c53}",
      "#sw-hub .project{border-top:1px solid #cfc6b8;padding:26px 0 30px;display:grid;grid-template-columns:minmax(0,1fr) minmax(220px,320px);gap:30px}",
      "#sw-hub .project h2{font-size:30px;line-height:1.05;margin:0 0 10px}",
      "#sw-hub .project p{font-size:16px;line-height:1.58;margin:0;color:#3d3731}",
      "#sw-hub .tags{display:flex;gap:8px;flex-wrap:wrap;align-content:flex-start}",
      "#sw-hub .tag{border:1px solid #d4cabd;padding:6px 9px;font-size:12px;color:#5c534a;background:#fffaf3}",
      "#sw-hub .muted{color:#756d63}",
      "#sw-hub .contact{border-top:1px solid #cfc6b8;margin-top:10px;padding-top:26px;font-size:15px;color:#3d3731}",
      "#sw-hub .contact a{color:#151515;text-decoration:underline;text-underline-offset:3px}",
      "@media(max-width:760px){#sw-hub{padding:64px 22px}#sw-hub .project{grid-template-columns:1fr;gap:16px}#sw-hub h1{font-size:48px}}"
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
        '<p class="lead">A simple home base for the systems I am building: practical software, sports analytics, and AI-assisted tools that turn messy information into something useful.</p>' +
        '<div class="links">' +
          '<a class="btn primary" href="https://algoball.samuelwertheim.com/">Open AlgoBall</a>' +
          '<a class="btn" href="https://www.linkedin.com/in/samuel-wertheim/" target="_blank" rel="noopener noreferrer">LinkedIn</a>' +
          '<a class="btn" href="mailto:wertheimsamuel12123@gmail.com">Email</a>' +
        "</div>" +
        '<p class="section-title">Selected Projects</p>' +
        '<article class="project">' +
          "<div><h2>AlgoBall</h2>" +
          '<p>Daily MLB betting-market analysis. AlgoBall builds its own pre-game moneyline probabilities, removes sportsbook vig, compares model price against market price, and highlights only the clearest model-vs-market divergences before games start.</p>' +
          '<p style="margin-top:16px"><a class="btn" href="https://algoball.samuelwertheim.com/">View live project</a></p></div>' +
          '<div class="tags"><span class="tag">Python</span><span class="tag">MLB Stats API</span><span class="tag">Odds API</span><span class="tag">Railway</span><span class="tag">Daily refresh</span></div>' +
        "</article>" +
        '<article class="project">' +
          "<div><h2>Next Project</h2>" +
          '<p class="muted">A second project is in progress. This page is built so new work can be added cleanly as the portfolio grows.</p></div>' +
          '<div class="tags"><span class="tag">In progress</span><span class="tag">Coming soon</span></div>' +
        "</article>" +
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
