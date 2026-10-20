# GLIMPSE UI ideas

Main rule: show first, explain only when asked. Every screen should answer "how do I
compare?" with a picture or a number before any sentence.

Status: [x] done, [~] partly done, [ ] not started.

## Wording rules (every page)

- [x] At most about 12 words per text block. Explanations live behind a "?" tip.
- [x] One plain word per idea: "models agree / disagree", never "Rashomon set".
- [x] Numbers and units first: "Glucose 150 mg/dL · higher than 82% of people".
- [x] Colour always comes with an icon or a word (lock for can't change, ▲▼ for direction,
      badge text for close call / clear).
- [x] Long explanations moved off the page (intro, captions, table notes).

## Pages

1. Home
   - [x] One-line pitch, topic cards, "Enter my numbers", "Try an example person".
   - [x] Short "How it works" and a "Not medical or financial advice" line.
2. Where you stand (the map page)
   - [x] Big prediction with a "Close call" / "Clear" badge.
   - [x] One range bar per model, explanation behind "?".
   - [x] "How you compare": the most important values first, as position bars.
   - [x] Tables and standardized numbers folded away.
3. Enter your numbers
   - [~] Units shown, typical value as placeholder, gentle out-of-range warning.
   - [ ] One small group at a time with a progress bar.
   - [ ] Sliders with a typical-value mark, and a live mini-map while typing.
4. Map explorer
   - [x] Density map as the main view (no individual people shown); click anywhere for the
         estimated person at that spot. The dot map stays behind "Old GLIMPSE graph (test)".
   - [x] Simple / Flexible / Both, Find me, Reset zoom.
   - [x] Dot map: hover card (prediction, models' range, two key values) and a
         "Most disputed" highlight (the 15% with the widest ranges).
   - [x] Clicking an empty spot shows a short "Estimated person at this spot" card.
   - [ ] Pin two people and compare them side by side.
   - [ ] "Show people like me".
5. What would change it
   - [x] Top 3 changes per model as cards: before → after, unit, effort tag (easy / harder).
   - [x] Can't-change values as grey lock chips, no explanation text.
   - [x] "Quickest change" and "Safest change" tabs with icons.
   - [x] "What if" sliders: the chance updates live and a hollow star moves on the map.
   - [x] Checklist plan with a live result, saved to the account and comparable with now.
6. Compare
   - [x] Compare page: you vs a typical person, or any two saves (before vs after), with the
         prediction move, a "flips the result" badge and changed values first.
   - [ ] Simple vs flexible model side by side on the same page.
7. My account
   - [x] Email, member since, saves per topic, sign out.
   - [x] Change password, delete account, forgot password (email link).
   - [x] Save cards with name, date, mini verdict and range bar.
   - [x] Open, Rename, Compare, Delete with Undo.
   - [x] Timeline per topic: chance over time across saves.
8. Sign in / create account
   - [x] Two fields with a show-password toggle, "Continue without an account", forgot password,
         "Save and compare your results", plain errors.
9. How it works page
   - [x] Its own page (top menu, "How it works"), linked from the home page and under the map
         legend (2026-10-19).
   - [~] Glossary that the "?" tips link into: each term has an anchor (#read-map, #close-call,
         #quick-safe, #can-change, …); the "?" tips don't link yet.
10. Expert view
   - [x] "Details for experts" keeps the exact numbers.
   - [ ] CSV download.

## Across all pages

- [ ] First-time tour (three skippable pointers).
- [~] Loading message ("Loading… the first time can take up to a minute").
- [~] Mobile: single column below 1000 px, smaller maps on phones. Needs a real pass.
- [~] Accessibility: keyboard topic cards and tips, labelled bars. Map keyboard use is missing.
- [ ] Shareable links that never include personal values unless the user chooses.

## Things people can't change (added 2026-10-14)

- [~] Never recommend changes to things people can't change. Today a fixed list per dataset
      (age, pregnancies, family history, …) is held fixed in the search and shown with a lock.
- [x] Add an interface where each value can be marked:
      - can't change (immutable),
      - can only go up (monotonically increasing, e.g. age, number of pregnancies),
      - can only go down (monotonically decreasing),
      - free to change.
      The counterfactual search should then respect these as constraints.
      Done: "What can you change?" on the map page (2026-10-14).
- [x] Also keep recommendations inside what is possible. Seen on the credit topic:
      "Inquiries (6 mo) 3 → -2 count" and "% accounts never late 70 → 101%". Counts can't be
      negative and percentages can't pass 100, so the search needs real bounds per value.
