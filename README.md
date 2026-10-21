# GLIMPSE

Many models can fit the same data about equally well and still disagree about one
person. GLIMPSE shows that whole group of good models (the Rashomon set) instead of
trusting just one. You see how sure the models really are, what drove the prediction,
and the changes that would flip it.

Live at https://glimpse-dev-hazel.vercel.app

## What you can do

- Pick a topic (diabetes or breast cancer), enter your numbers or try an example person.
- See the chance from a simple and a flexible model, and the range the other good models give.
- Get three changes that would flip the result: the smallest, the one with fewest values,
  and the safest (works for every good model). Things you can't change are never suggested.
- Sign in to save your numbers and compare them over time.

## The map

The map squeezes everyone onto a flat page; darker areas are where more people are.
Click anywhere to see the person who would be there. "Around this person" rebuilds the
map around you so your changes show at their true size. A developer switch draws the map
with ECLIPSE, our experimental method, and `/eclipse.html` compares it with PCA.

## Running it

```bash
uv sync
PORT=8010 .venv/bin/python backend/server.py      # http://127.0.0.1:8010
.venv/bin/python -m unittest discover -s backend/tests
```

Datasets: Pima diabetes and Wisconsin breast cancer. For learning and research, not
medical advice.
