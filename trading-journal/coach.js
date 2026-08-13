/* AI Coach analysis — generated from the account's realized-trade record.
   Regenerate against fresh data with:  python ai_coach.py
   Figures are informational only, not tax or investment advice. */
window.COACH = {
  generatedAt: "2026-08-13",
  model: "claude-opus-4-8",
  grade: "Breakeven — fixable",
  verdict:
    "You're a disciplined-enough trader with a real edge that's being erased by three specific, mechanical leaks. Your average winner ($33.55) beats your average loser ($27.05), which is the hard part — but your 43.7% win rate sits just under the 44.6% you need to break even, so tiny behavioral changes flip the whole account green. This isn't a strategy problem; it's a rules problem. The single biggest lever: you bleed almost all of your losses in the 12–1pm ET lunch chop. Cut that window and the same trading history turns from −$150 into roughly +$420.",
  leaks: [
    { title: "The 1pm ET hour is a black hole",
      html: "Your 1:00pm ET hour alone is <b>−$464</b> across 44 trades; noon adds another <b>−$106</b>. Midday chop punishes a momentum scalper. <span class='impact'>Avoiding 12–1pm ET recovers ~$570.</span>" },
    { title: "You size up at exactly the wrong time",
      html: "1- and 3-contract trades are green, but your <b>6–9 and 10+ lots lose money</b> — 10+ wins just 29%. Your conviction is inverted: you bet biggest on your worst trades. <span class='impact'>Capping size at 3 alone flips you to +$79.</span>" },
    { title: "You tilt after losses",
      html: "The trade right after a loss averages <b>−$3.59</b>, versus <b>+$3.90</b> after a win. Losses are dragging the next click. <span class='impact'>A one-trade cool-off lifts your win rate past 51%.</span>" },
    { title: "Thursday & Friday give it all back",
      html: "Mon–Wed are net positive (Tue leads at +$316); <b>Thu (−$404) and Fri (−$300)</b> erase the week. Late-week trading is a net drain on this record." },
  ],
  plan: [
    { title: "Hard-stop the lunch hour",
      html: "No new entries <b>12:00–1:00pm ET</b>, no exceptions. This is your highest-value single rule — it removes your worst 74 trades and turns the account positive on its own." },
    { title: "Cap size at 3 contracts",
      html: "Trade 1–3 lots only until you've strung together 20 green sessions. Your edge lives in small size; scaling up is where it dies. Re-earn the right to size up." },
    { title: "One-trade cool-off after any red trade",
      html: "After a loss, sit out one setup — walk, log the trade, reset. This directly attacks the post-loss tilt that's costing you the win rate you need." },
    { title: "Shrink or paper-trade Thu/Fri",
      html: "Halve your size Thursday and Friday, or paper-trade them for a month and compare. Protect the Mon–Wed gains you're already making." },
    { title: "Tag every trade, review weekly",
      html: "Use the tags below (A+ setup, FOMO, revenge…). After two weeks, the Tag-performance card tells you which of your reads actually pay — and whether these rules are working." },
  ],
  strengths: [
    "Positive payoff ratio — your winners are bigger than your losers.",
    "Recent form is up: your last 90 days are net +$119 vs −$150 all-time.",
    "You cut losers small — most losses cluster under $25.",
  ],
  note:
    "Grounded in your realized-trade history. This is a behavioral read of your own data, not investment advice — validate every rule against your own results before trading it.",
};
