# Release Point: download, build, measure, check, and write the page. Each step reads the previous step's output.
PY ?= python
SEASONS = 2025 2026

.PHONY: all data build analysis site test serve

all: build analysis site test

data:            ## Kalshi markets and trades, MLB play-by-play (both pitch timestamps), Savant pitch states (slow, polite)
	cd pipeline && "$(PY)" fetch_kalshi.py markets
	cd pipeline && "$(PY)" fetch_mlb.py $(SEASONS)
	cd pipeline && "$(PY)" fetch_savant.py $(SEASONS)
	cd pipeline && "$(PY)" fetch_kalshi.py trades $(SEASONS)

build:           ## tables: games, pitches with states and win expectancy, trades matched to games in home-team terms
	cd pipeline && "$(PY)" build_mlb.py $(SEASONS)
	cd pipeline && "$(PY)" build_savant.py $(SEASONS)
	cd pipeline && "$(PY)" build_trades.py $(SEASONS)

analysis:        ## the event study, every number with game-bootstrap intervals, and the simulated-market check
	cd pipeline && "$(PY)" events.py $(SEASONS)
	cd pipeline && "$(PY)" simulate.py
	cd pipeline && "$(PY)" analysis.py

site:            ## site data, the page and README filled from the outputs, the share card (needs Google Chrome)
	cd pipeline && "$(PY)" export.py
	cd pipeline && "$(PY)" story.py
	"$(PY)" tools/og.py

test:
	"$(PY)" -m pytest -q

serve:
	"$(PY)" -m http.server 8646 --directory site
