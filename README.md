# bangkapi-cafe-network

Bipartite café × aspect network from Google Maps reviews – Bang Kapi café positioning (MADT7202 mid-term).

## Question
Which two attributes should a new Bang Kapi café own as its positioning?

## Files
- `analysis.py` – full pipeline: lexicon tagging → café × aspect NPMI graph → robustness checks → figure
- `BangKapi_Cafe_Analysis_Colab.ipynb` – the same code split into cells, for Google Colab
- `stats.json` – every number quoted in the report
- `fig.png` – the network figure

## Run
    pip install pandas numpy scipy networkx matplotlib pythainlp python-crfsuite
    python3 analysis.py reviews.csv

## Data
Google Maps reviews of cafés near Bang Kapi, collected 9 Oct 2026 with Apify crawler-google-places.
The raw file is not shared because it contains reviewer names and IDs.
