
from __future__ import annotations
import os, asyncio, re
from flask import Flask, render_template, request
from scraping import scrape_multi, detect_pack_qty
from pricing import compute_suggestion, choose_and_suggest, tokens, jaccard

app = Flask(__name__)

TITLE_SIM_THRESHOLD = 0.75  # title guard for exact UPC matches

PRICE_CLUSTER_WINDOW = 8.0   # dollars spanned by the densest cluster window (try 6–10)


def _norm_digits(x: str) -> str:
    return re.sub(r"[^0-9]", "", x or "")

def default_ctx():
    return {
        "form": {
            "code": "",
            "title": "",
            "req": "",
            "condition": "new",
            "iqr_mult": "1.5",
            "min_price": "",
            "max_price": "",
            "pages": "1",
            "retries": "3",
            "attempts": "6",
        },
        "error": None,
        "amazon": None,
        "amazon_note": None,
        "results": None,
        "results_raw": None,
        "suggestion": None,
        "suggestion_source": None,
        "reference": None,
        "secondary": None,
        "secondary_ref": None,
        "counts": None,
    }

@app.route("/clear", methods=["GET"])
def clear():
    return render_template("index.html", **default_ctx())

@app.route("/", methods=["GET", "POST"])
def index():
    ctx = default_ctx()
    if request.method == "POST":
        code = (request.form.get("code") or "").strip()
        title = (request.form.get("title") or "").strip() or None
        req_tokens = (request.form.get("req") or "").strip()
        condition = (request.form.get("condition") or "new").strip().lower()
        iqr_mult = float(request.form.get("iqr_mult") or 1.5)
        min_price = float(request.form.get("min_price")) if request.form.get("min_price") else None
        max_price = float(request.form.get("max_price")) if request.form.get("max_price") else None
        pages = max(1, int(request.form.get("pages") or 1))
        retries = max(1, int(request.form.get("retries") or 3))
        attempts = max(1, int(request.form.get("attempts") or 6))

        ctx["form"].update({
            "code": code or "",
            "title": title or "",
            "req": req_tokens,
            "condition": condition,
            "iqr_mult": str(iqr_mult),
            "min_price": "" if min_price is None else str(min_price),
            "max_price": "" if max_price is None else str(max_price),
            "pages": str(pages),
            "retries": str(retries),
            "attempts": str(attempts),
        })

        if not code:
            ctx["error"] = "Enter a product code, ASIN, or Amazon URL."
            return render_template("index.html", **ctx)

        try:
            data = asyncio.run(scrape_multi(
                code, title,
                condition=condition,
                prefer_amazon_first=True,
                use_amazon=True,
                pages=pages,
                retries=retries,
                attempts=attempts,
                visible=False,
            ))
        except Exception as e:
            ctx["error"] = f"Search failed: {e}"
            return render_template("index.html", **ctx)

        raw_rows = data.get("rows", [])
        amazon = data.get("amazon")

        rows = data.get("filtered_rows") or raw_rows
        comp_rows = rows

        # ---------- Amazon context ----------
        amz_title = (amazon.get("title") if amazon else "") or ""
        amz_toks = tokens(amz_title)

        # ---------- Exact-UPC-first with title guard (>= 0.60) ----------
        user_code = _norm_digits(code)
        ebay_exact_row = None
        ebay_exact_total = None
        ebay_abs_row = None
        ebay_abs_total = None

        if comp_rows and user_code:
            def row_code_match(r):
                for k in ("upc","code","barcode","item_upc"):
                    v = r.get(k)
                    if v and _norm_digits(str(v)) == user_code:
                        return True
                if r.get("has_code") and r.get("code"):
                    return _norm_digits(str(r["code"])) == user_code
                return False

            def sim_ok_title(r):
                if not amz_toks:
                    return True
                s = jaccard(amz_toks, tokens(r.get("title") or ""))
                return s >= TITLE_SIM_THRESHOLD

            exacts = [r for r in comp_rows if row_code_match(r) and r.get("total") is not None and sim_ok_title(r)]
            if exacts:
                ebay_exact_row = min(exacts, key=lambda r: r["total"])
                ebay_exact_total = float(ebay_exact_row["total"])

        # ---------- If no exact code+title match, use absolute-low from comp_rows ----------
        if comp_rows:
            valids = [r for r in comp_rows if r.get("total") is not None]
            pool = []

            if valids:
                if amz_toks:
                    strict = [r for r in valids if jaccard(amz_toks, tokens(r.get("title") or "")) >= TITLE_SIM_THRESHOLD]
                    if strict:
                        pool = strict
                    else:
                        relaxed = [r for r in valids if jaccard(amz_toks, tokens(r.get("title") or "")) >= 0.45]
                        pool = relaxed if relaxed else valids
                else:
                    pool = valids

            if pool:
                # <-- CLUSTER here: pick the lowest inside the densest window
                best_total, best_row, used_rows = compute_suggestion(
                    pool,
                    method="mode",               # densest price window
                    window=PRICE_CLUSTER_WINDOW, # tighten/loosen cluster span
                    # min_price=None, max_price=None   # you can add hard caps if you want
                )
                if best_row:
                    ebay_abs_row = best_row
                    ebay_abs_total = float(best_row["total"])


        # Amazon total
        amz_total = float(amazon["total"]) if (amazon and amazon.get("total") is not None) else None

        # Prefer exact eBay if available
        ebay_to_use = ebay_exact_total if ebay_exact_total is not None else ebay_abs_total
        ebay_row_ref = ebay_exact_row if ebay_exact_row is not None else ebay_abs_row

        pick = choose_and_suggest(amz_total, ebay_to_use)

        ctx["amazon"] = amazon
        if amazon and amz_total is not None:
            pack_msg = f" (pack qty detected: {amazon.get('pack_qty')})" if amazon and amazon.get("pack_qty") else ""
            ctx["amazon_note"] = "Amazon price from product page; if missing, pulled from Offer Listings (New)" + pack_msg + "."

        ctx["results"] = comp_rows
        ctx["results_raw"] = raw_rows
        ctx["counts"] = {"raw": len(raw_rows), "used": len(comp_rows)}

        if pick["suggested"] is not None:
            ctx["suggestion"] = f"{pick['suggested']:.2f}"
            ctx["suggestion_source"] = pick["source"]
            if pick["source"] == "Amazon":
                ctx["reference"] = amazon.get("url") if amazon else None
            else:
                ctx["reference"] = ebay_row_ref.get("url") if ebay_row_ref else None
        else:
            ctx["error"] = "Not enough clean data to suggest a price."

        return render_template("index.html", **ctx)

    return render_template("index.html", **ctx)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","5000")), debug=False)
