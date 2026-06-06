# AlgoBall

A simple, honest, pre-game MLB model. Once a day, before games start, it builds
its own win probability for each game, compares that to the betting market's
moneyline, and surfaces the handful of games (usually 0-3) where it sees a real
edge. It runs once each morning, pre-game only. There are no servers to babysit.

## Running AlgoBall

### Run it yourself, right now (one command)

From the project folder, run:

```
PYTHONPATH=src python3 -m algoball
```

That fetches today's schedule, builds the model's odds, makes a single call to
the odds service, and writes the results to a web page at:

```
public/index.html
```

To see it, open that `public/index.html` file in any web browser (double-click
it, or in your browser choose File -> Open File and pick it). That page is the
finished product for the day.

Useful options:

```
PYTHONPATH=src python3 -m algoball --date 2026-06-06
PYTHONPATH=src python3 -m algoball --refresh-odds
PYTHONPATH=src python3 -m algoball --feature-season 2025
```

By default, odds are cached by date in `data/cache/odds_<date>.json`, so
re-running the same day does not spend another Odds API credit unless you pass
`--refresh-odds`.

Note: the program needs your odds service key to be available as `ODDS_API_KEY`.
Locally that lives in the project's `.env` file (one line: `ODDS_API_KEY=...`).
You set this once and never touch it again. (Never share or commit this key.)

The v1 runtime has no third-party dependencies. The only package in
`requirements.txt` is `pytest` for development tests.

### TO MAKE IT RUN ITSELF EVERY DAY

You only have to do this setup ONCE. After that, the page rebuilds itself every
morning before game time, with no action from you. Follow these steps in order:

1. **Create a GitHub repository.** Go to github.com, sign in (make a free
   account if you don't have one), click the **+** in the top-right, and choose
   **New repository**. Give it a name (for example `algoball`) and click
   **Create repository**.

2. **Push the code to that repository.** Upload this project's files to the new
   repository. GitHub shows the exact copy-paste commands on the empty
   repository page under "...or push an existing repository from the command
   line." Run those from this project folder. When it's done, refresh the
   GitHub page and you should see all the files, including the `.github` folder.

3. **Add your odds key as a repository secret.** In your repository on GitHub,
   click **Settings** (top menu) -> in the left sidebar open **Secrets and
   variables** -> **Actions** -> click **New repository secret**. For the
   **Name** type exactly:

   ```
   ODDS_API_KEY
   ```

   For the **Secret** (the value) paste your odds service key, then click **Add
   secret**. This keeps the key private; it is never shown on the public page.

4. **Turn on the website (GitHub Pages).** Still in **Settings**, open **Pages**
   in the left sidebar. Under **Build and deployment**, set **Source** to
   **GitHub Actions**. That's it - no other Pages settings are needed.

5. **(Optional) Do a first run now to check it.** Click the **Actions** tab at
   the top, choose **AlgoBall daily** on the left, then click **Run workflow**
   on the right. After a couple of minutes it should finish with a green check.
   Your live page URL appears under **Settings -> Pages** (and in the finished
   Actions run). Open it in a browser to confirm it looks right.

After this one-time setup, **the page updates automatically every morning,
before the first game starts.** You don't have to run anything by hand. If you
ever want to force an update, use the **Run workflow** button from step 5. To
see what it produced on a given day, just open your GitHub Pages URL in a
browser.
