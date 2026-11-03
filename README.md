# Instamart Customer Intelligence & Support Copilot

## Overview

An internal Copilot for a fictional quick-commerce business (all data is synthetic, all amounts are in INR). It is built in four connected Parts:

- **Part A**: clean the raw exports and store them in SQLite, then query them (done).
- **Part B**: customer segments and lapse prediction (done).
- **Part C**: support ticket triage with guardrails (done).
- **Part D**: policy RAG assistant and refund agent (done).

`generate_data.py` and `mock_llm.py` are the supplied files and are unmodified. No network, API key or paid service is used.

Project layout:

| Path | Purpose |
|---|---|
| `run_project.py` | runs every step below in order with one command |
| `app.py`, `web/` (`index.html`, `style.css`, `app.js`) | optional local web UI (`python app.py`, then open http://127.0.0.1:8000): a chat-style page (messages and answers scroll above, the input box stays at the bottom) with the same five tools as `ask.py`; "Auto" mode picks the tool from your message. Standard library only. Run it after `run_project.py` |
| `ask.py` | optional interactive menu (`python ask.py`): redact a ticket, classify it, ask a policy question, request a refund, look up customer segments. Refunds made here go to `interactive_runs/` (git-ignored), not to the graded outputs |
| `src/` | reusable functions: `cleaning.py` (Part A rules), `features.py` and `modeling.py` (Part B), `triage.py` (Part C), `rag.py` and `agent.py` (Part D) |
| `part_a/` to `part_d/` | the runnable scripts of each Part; they import their logic from `src/` and print and save the results |
| `sql/queries.sql` | the seven Part A queries |
| `data/`, `outputs/`, `state/` | raw and clean data, database, model, result files and agent checkpoints |

## Reproduce

Commands for Windows PowerShell; on macOS/Linux use `source .venv/bin/activate` instead of the activate line.

1. `python -m venv .venv`
2. `.venv\Scripts\Activate.ps1`
3. `pip install -r requirements.txt`
4. `python generate_data.py`
5. `python part_a/audit.py`
6. `python part_a/clean.py`
7. `python part_a/run_queries.py`
8. `python part_a/eda.py`
9. `python part_a/validate.py`

10. `python part_b/segments.py`
11. `python part_b/lapse.py`
12. `python part_c/triage.py`
13. `python part_d/rag.py`
14. `python part_d/agent.py`

Steps 4 to 14 can also be run in one go with `python run_project.py` (about 70 seconds). It runs the same scripts in the same order and stops at the first failure.

## Part A

Libraries: Python 3.11.9, pandas 3.1.0, numpy 2.4.6 (see `requirements.txt`). Raw CSVs are read with `keep_default_na=False, na_values=[""]` so that only truly blank cells are missing and the text `N/A` stays visible as a bad amount.

### Audit of the raw data

| Table | Shape | Columns with missing values |
|---|---|---|
| customers | 1200 x 5 | age 61 (5.08%), gender 30 (2.50%) |
| products | 40 x 4 | none |
| orders | 13084 x 9 | delivery_minutes 2541 (19.42%) |

Data types: customer_id, city, signup_date, gender, and all id and text columns are strings; age is float (blanks); price_inr, quantity and discount_pct are int; order_amount is read as string (it contains `N/A` and `error`); delivery_minutes is float.

| Audit figure | Value |
|---|---|
| raw orders rows | 13,084 |
| exact duplicate rows | 119 |
| pending rows | 656 |
| distinct order_id | 12,309 |
| non-numeric order_amount | 120 |
| negative delivery_minutes | 106 |
| blank delivery_minutes | 2,541 |
| customers: blank age | 61 |
| customers: age outside 10-100 | 6 |
| customers: distinct raw city spellings | 24 |
| customers: distinct non-blank gender spellings | 10 |
| customers: blank gender | 30 |

All match the reference values.

### Cleaning rules and what each changed

Customers:

1. City: strip spaces and title case. Changed 476 values; exactly 6 cities remain.
2. Gender: m/male to `male`, f/female to `female`, blank to `unknown`. Result female 610, male 560, unknown 30.
3. Age: 6 impossible values (outside 10-100) set to missing, then all 67 missing ages (61 blank + 6) filled with the city median using `groupby("city").transform("median")`. 0 missing, all ages 18 to 60.
4. signup_date converted to datetime.

Orders, in this order:

1. `order_ts` converted to datetime.
2. Exact duplicates removed: 119 rows (13,084 to 12,965).
3. For each `order_id` keep the record with the latest `order_ts`: 656 earlier pending records removed (12,965 to 12,309).
4. `order_amount` converted to numeric, 112 unparseable values became missing (120 raw, the other 8 sat on rows already removed in rules 2 and 3) and were filled with `round(price_inr x quantity x (1 - discount_pct/100), 2)`.
5. Negative `delivery_minutes` (105 remaining after de-duplication) set to missing. For completed orders, 774 missing delivery times were filled with the median of the order's product category among completed orders (`groupby` + `transform`). Cancelled orders keep a missing delivery time, because a cancelled order was never delivered and imputing one would invent data.

Result: 12,309 rows, one per `order_id`; 11,110 completed and 1,199 cancelled; no pending; 0 missing `order_amount`; 0 missing delivery among completed and 1,199 among cancelled; completed revenue INR 2,998,668.80.

### Storage and validation

Clean tables are written to `data/clean/customers.csv`, `products.csv`, `orders.csv` and to `data/instamart.db` (tables `customers`, `products`, `orders`; `order_ts` stored as text `YYYY-MM-DD HH:MM:SS`). `part_a/validate.py` asserts 19 checkpoints (cities, genders, ages, order counts, statuses, missing values, revenue, database tables and the results of all seven queries) and prints `ALL CHECKPOINTS PASSED`.

### SQL analysis (`sql/queries.sql`, run by `part_a/run_queries.py`)

| Query | Result |
|---|---|
| Q1 WHERE + HAVING | 30 customers |
| Q2 three-table join | 30 rows; total INR 2,998,668.80; largest cell Bengaluru / Electronics INR 233,909.45 |
| Q3 scalar subquery | 11 products above the average price |
| Q4 LEFT JOIN | 25 customers with no completed order |
| Q5 CTE | 550 customers above the average total of INR 2,552.06 |
| Q6 window ranking | top per city: Bengaluru C0082 (12,856.20), Chennai C0930 (10,151.40), Delhi C0291 (13,742.60), Hyderabad C0743 (12,730.05), Mumbai C0693 (14,766.55), Pune C0426 (10,377.10); 8 rows where RANK() differs from ROW_NUMBER() |
| Q7 running total | 183 daily rows; final cumulative INR 2,998,668.80 |

RANK() differs from ROW_NUMBER() when customers in the same city have equal total spend: ties share one rank (the next rank is skipped) while ROW_NUMBER() still gives each row a distinct number.

### pandas cross-check and exploratory analysis

`pd.pivot_table(..., margins=True)` gives a grand total of INR 2,998,668.80, equal to the SQL total (largest cell 233,909.45, also equal).

| City | Sum | Mean | Count |
|---|---|---|---|
| Bengaluru | 523,643.40 | 276.47 | 1,894 |
| Chennai | 463,629.15 | 272.72 | 1,700 |
| Delhi | 502,829.80 | 243.62 | 2,064 |
| Hyderabad | 528,589.90 | 284.95 | 1,855 |
| Mumbai | 479,058.50 | 297.00 | 1,613 |
| Pune | 500,918.05 | 252.48 | 1,984 |

Completed `order_amount`: mean 269.91, median 135.00, skewness 4.61, Q1 64.80, Q3 297.00, IQR 232.20, lower fence -283.50 (0 outliers below), upper fence 645.30 (897 outliers above).

Correlation matrix (completed orders):

| | order_amount | discount_pct | quantity | delivery_minutes |
|---|---|---|---|---|
| order_amount | 1.000 | -0.095 | 0.087 | -0.003 |
| discount_pct | -0.095 | 1.000 | -0.000 | -0.010 |
| quantity | 0.087 | -0.000 | 1.000 | -0.013 |
| delivery_minutes | -0.003 | -0.010 | -0.013 | 1.000 |

**Findings (under 200 words).** The data are six-city quick-commerce orders for groceries, dairy, snacks, personal care and electronics, with 11,110 completed orders. Order amounts are strongly right-skewed: the mean (269.91) is about double the median (135.00) and skewness is 4.61. There are 897 high outliers above 645.30 and none below; they are mostly legitimate electronics purchases, not errors, so they should be kept. The anomalies were in the raw export (duplicates, pending rows, impossible ages and delivery times) and have been cleaned. The pair with the largest correlation in absolute value is order_amount and discount_pct at -0.095, just ahead of order_amount and quantity at +0.087. Both are very weak, and correlation of this size does not establish causation.

## Part B

Scripts: `part_b/segments.py` (RFM, K-means, PCA, segments file) and `part_b/lapse.py` (lapse model). scikit-learn 1.9.1, all seeds fixed at 42. Only completed orders are used for behaviour.

**Leakage statement.** No encoder, scaler or resampler saw test rows (all are fitted inside a Pipeline on the training rows, and over-sampling is applied to the training rows only). No data dated 2025-09-01 or later entered the features. The segment labels from the RFM clustering were not used as features.

### RFM (snapshot 2025-10-01 00:00:00)

| Item | Value |
|---|---|
| customers with a completed order | 1,175 |
| recency (days) | median 19, min 0, max 180 |
| frequency | mean 9.46, max 33 |
| monetary (INR) | mean 2,552.06, max 14,766.55 |

### K-means (StandardScaler, n_init=10, random_state=42)

| K | Inertia | Silhouette |
|---|---|---|
| 2 | 1820.8 | 0.465 |
| 3 | 1268.2 | 0.445 |
| 4 | 743.1 | 0.526 |
| 5 | 617.4 | 0.480 |
| 6 | 503.2 | 0.482 |
| 7 | 408.5 | 0.416 |
| 8 | 366.5 | 0.412 |

All values are within tolerance of the reference. The elbow is at K=4: inertia drops by 525 from K=3 to K=4 and only by 126 from K=4 to K=5, and the silhouette peaks at K=4 (0.526). **Final K = 4**, which is also easy to act on (four campaigns). Inertia always falls as K grows because more centres sit closer to every point (it would reach 0 with one cluster per customer), so K=8 beating K=2 says nothing about quality; K must be chosen from the shape of the curve, the silhouette and whether the groups are useful to the business.

### Segment profile (K = 4)

Cluster numbers are only labels with no ordering. Names are assigned from each segment's profile, and Premium is the segment with the highest mean monetary value.

| Segment id | Name | Size | Mean recency (days) | Mean frequency | Mean monetary (INR) | Recommended action |
|---|---|---|---|---|---|---|
| 1 | Premium Big Spenders (is_premium) | 138 | 24.12 | 6.77 | 7,129.70 | Early access to electronics offers and priority support |
| 2 | Loyal Regulars | 419 | 8.77 | 19.40 | 3,410.02 | Loyalty points and subscription for daily staples |
| 0 | Occasional Buyers | 436 | 28.86 | 3.77 | 1,057.62 | Bundle and free-delivery nudges to raise order frequency |
| 3 | Lapsing Customers | 182 | 109.04 | 2.20 | 685.99 | Win-back coupon before they are lost |

PCA on the scaled RFM matrix: explained variance ratio 0.634 and 0.218, total 0.852. `outputs/customer_segments.csv` has columns customer_id, recency, frequency, monetary, segment_id, segment_name, is_premium.

### Lapse problem

Cutoff 2025-09-01. Cohort: customers with at least one completed order before the cutoff. Label `lapsed` = 1 if the customer has no completed order from 2025-09-01 to 2025-09-30. Features (orders before the cutoff only): recency, frequency, monetary, average discount_pct, cancellation rate, average delivery_minutes, favourite category, city, age, gender, tenure in days.

| Item | Value |
|---|---|
| cohort | 1,156 customers |
| lapsed | 443 (38.32%) |
| train / test | 924 / 232 (`train_test_split`, test_size=0.2, stratify, random_state=42) |
| baseline "never lapsed" on test | accuracy 61.6%, lapsed-class F1 0.000 |

### Preprocessing

One-hot encoding of city, gender and favourite category with `drop="first"` and standardisation of the numeric features run inside a scikit-learn Pipeline, fitted on training rows only. The scaler's learned mean of frequency is 8.1147 against 8.0285 for the full cohort: they differ because the scaler only saw the 924 training customers, while the cohort mean also includes the 232 test customers. Check in code: the feature matrix contains no missing values.

### Tuning and test results (lapsed class)

| Model | Best parameters | Best CV F1 | Test accuracy | Test precision | Test recall | Test F1 | Confusion [[TN, FP], [FN, TP]] |
|---|---|---|---|---|---|---|---|
| LogisticRegression (C in 0.01, 0.1, 1, 10, 100; cv=5) | C=100 | 0.651 | 0.728 | 0.644 | 0.652 | 0.648 | [[111, 32], [31, 58]] |
| RandomForest (max_depth 3/5/8 x min_samples_leaf 5/10/20; cv=5) | depth 8, leaf 10 | 0.681 | 0.737 | 0.659 | 0.652 | 0.655 | [[113, 30], [31, 58]] |

The baseline has lapsed F1 0 and accuracy 0.616, so both models are far better (accuracy 0.728 and 0.737).

**Why accuracy stays near 74% and not 90%.** I tried to push it higher. I added recent-activity features (orders in the last 30, 60 and 90 days, span between first and last order, average order value, electronics share) and tested several models (logistic regression, random forest, gradient boosting) with 5-fold cross-validation on the whole cohort. Accuracy stayed between 70% and 74%. On the held-out test set the 14-feature random forest scored 0.728 accuracy and 0.648 F1, no better than the 8-feature one (0.737 and 0.655), so I kept the simpler model. The reason is the data, not the model: the generator creates orders as random events at a fixed rate per customer type, so whether a customer places an order in one particular month is partly pure chance, and no feature can predict chance. A frequent buyer with 3.5 orders a month lapses with probability of about 3%, but a premium customer with 1 order a month still lapses about 37% of the time. Accuracy near 74% is therefore close to what this dataset allows, and a target of 89 to 90% would need information that is not in the data. **Selected model: RandomForest** (best cross-validated F1, and test F1 0.655, above the required 0.55). Missing a lapsing customer means losing the customer's future revenue, while wrongly targeting a loyal one costs only a coupon or message, so recall matters more than precision here; the two models have equal recall (0.652), and the forest has the better precision and F1, so it wastes fewer offers for the same number of lapsers caught. The test set was used only after tuning was finished. The best logistic regression's C=100 is at the edge of the grid, so a larger C might help slightly.

### Class-balance experiment

Over-sampling the training set only: 216 randomly drawn duplicates of lapsed training rows (with replacement, random_state=42) gave 570 / 570 rows. Best logistic regression refitted and scored on the original test set:

| Model | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|
| unbalanced | 0.728 | 0.644 | 0.652 | 0.648 |
| balanced | 0.716 | 0.589 | 0.854 | 0.697 |

Recall moved most (+0.20), precision fell (0.644 to 0.589). The model finds many more lapsing customers (76 of 89 instead of 58) but also flags more loyal ones (53 false positives versus 32). For the retention team this is a good trade if a retention offer is cheap, because the cost of missing a lapser is higher than the cost of a wasted offer. Note that the brief's reference expects precision to stay near 0.6; here the unbalanced precision was already 0.64 because the model started with higher precision.

### Interpretation

Top 5 random forest features: frequency (0.280), monetary (0.271), recency (0.115), average delivery time (0.061), cancellation rate (0.052). Business reading: how often and how much a customer bought before September dominate the prediction; recency matters but less; delivery speed and cancellations contribute a little.

Logistic regression coefficients (standardised features; a negative sign lowers the lapse probability):

- frequency: -1.70, so customers who order often rarely lapse.
- favourite category Electronics: -1.14 versus the dropped baseline category (Dairy), so electronics buyers (premium customers) are more likely to stay.
- cancellation rate: -0.12, which is tiny, so cancellations carry little signal on their own.

### Persistence and retention list

The selected model is saved with `joblib.dump` to `outputs/lapse_model.joblib`; the reloaded model reproduces the original test predictions exactly. Of the 232 test customers, 40 are in the Premium segment. `outputs/retention_list.csv` holds the top 10 by predicted lapse probability (columns customer_id, lapse_probability, actually_lapsed); 1 of those 10 truly lapsed. The retention list is illustrative and not a leakage-free evaluation, because the Premium flag comes from whole-window RFM that includes the September window that defines the lapse label.

## Part C

Script: `part_c/triage.py` (one command runs everything). It reads `data/raw/tickets.csv` (with `keep_default_na=False`) and `outputs/customer_segments.csv` from Part B, processes tickets in file order, and calls only the offline `mock_llm.py`. `mock_llm.reset()` is called immediately before every full run. Constants: `MAX_INPUT_TOKENS = 400`, `BASE_DELAY = 0.05`, 3 retries maximum.

### Input guardrails

An empty or whitespace-only text gets `skipped_empty`; a ticket whose `est_tokens(text)` is above 400 gets `flagged_long`. Neither is ever sent to the model. Result: 4 empty tickets and 4 long tickets (each estimated at 734 tokens).

### Redaction

Applied in this order before any prompt: email `[\w.+-]+@[\w-]+\.[\w.]+` to `[EMAIL]`, phone `\b[6-9]\d{9}\b` to `[PHONE]`, order id `ORD-\d{6}` to `[ORDER_ID]`. The user message sent to the model is exactly the redacted text.

| Type | Substitutions |
|---|---|
| email | 55 |
| phone | 91 |
| order id | 132 |
| total | 278 |

Re-applying the three patterns to the redacted texts finds 0. The code also asserts, for each of the 560 prompts sent across all runs, that none of the three patterns matches the user message.

### Prompts

The zero-shot prompt (37 estimated tokens) contains CLASSIFY, lists billing, delivery, technical and fraud, and requires a JSON-only reply `{"category": "...", "reason": "..."}`; it has no `EXAMPLES:` line. The few-shot prompt (119 estimated tokens) is the same text plus an `EXAMPLES:` line with four labelled examples, including a fraud one.

### Retries

Every model call is wrapped in a retry function: maximum 3 retries, wait before retry n = `0.05 x 2**n x random.uniform(0.9, 1.15)` seconds, one log line per retry (ticket id, retry number, wait) written to `outputs/retry_log.txt` (it accumulates all four runs). In a full run over the 156 eligible tickets there were exactly 19 `TransientLLMError`s and all 19 were recovered by the first retry (every retry is retry number 0, with waits between 0.0458 and 0.0573 seconds, inside 0.045 to 0.0575). No ticket ended with a permanent error.

### Output validation

A reply that parses as JSON with an allowed category is `classified_json`. A reply that is not valid JSON has its lowercase words extracted with `re.findall(r"[a-z]+", text.lower())` (so `billing-related` gives `billing` and `related`) and is `classified_keyword` if exactly one allowed category word is present. Anything else, including valid JSON with a category outside the list (the mock answers `shipping`), is `flagged_invalid_output` and goes to human review. The code never guesses.

Full run over all 164 tickets (identical for both prompts): 135 `classified_json`, 12 `classified_keyword`, 9 `flagged_invalid_output`, 4 `skipped_empty`, 4 `flagged_long`.

### Zero-shot versus few-shot (no token budget)

| Prompt | Tickets classified | Correct | Accuracy | Total tokens | Tokens per classified ticket |
|---|---|---|---|---|---|
| zero-shot | 147 | 126 | 85.7% | 10,180 | 69.3 |
| few-shot | 147 | 147 | 100.0% | 22,972 | 156.3 |

Zero-shot confusion table (rows true, columns predicted):

| true \ predicted | billing | delivery | fraud | technical |
|---|---|---|---|---|
| billing | 38 | 0 | 0 | 0 |
| delivery | 0 | 36 | 0 | 0 |
| fraud | 11 | 0 | 23 | 0 |
| technical | 10 | 0 | 0 | 29 |

Every zero-shot error is a fraud ticket predicted billing (11) or a technical ticket predicted billing (10). The few-shot prompt costs about 87 more tokens per classified ticket (156.3 versus 69.3, 2.3 times as much) and removes all 21 errors. It is worth paying when a miss is costly: a fraud ticket labelled billing would skip the security team's 2-hour escalation, so the extra tokens are cheap compared to 11 missed fraud tickets. For low-stakes labels, or when a tight token budget is the binding constraint, zero-shot is acceptable.

### Token budget demo and final routing

Budget demo (zero-shot, `TOKEN_BUDGET = 6000`, saved to `outputs/triage_budget_demo.csv`): the budget stopped the run after 6,010 tokens; **64 tickets ended `budget_exhausted`** and went to human review (80 `classified_json`, 7 `classified_keyword`, 5 `flagged_invalid_output`, 4 `skipped_empty`, 4 `flagged_long`).

Final run (`outputs/triage_results.csv`, 164 rows): few-shot prompt, `TOKEN_BUDGET = 100000` (22,972 tokens used, nothing exhausted). Routing: statuses `skipped_empty`, `flagged_long`, `flagged_invalid_output` or `budget_exhausted` go to `human_review` with priority NORMAL; otherwise fraud goes to `security_team` with HIGH; otherwise a premium customer (from Part B's `is_premium`, missing customer treated as not premium) goes to `premium_desk` with HIGH; otherwise `support_queue` with NORMAL.

| Route | Priority | Tickets |
|---|---|---|
| security_team | HIGH | 34 |
| premium_desk | HIGH | 11 |
| support_queue | NORMAL | 102 |
| human_review | NORMAL | 17 |

**Rule-validated versus human.** 147 tickets (135 JSON, 12 keyword) were validated by the rules and routed automatically. 17 went to humans: 9 invalid model outputs, 4 empty tickets and 4 over-long tickets. In the final run none went to humans because of the budget.

## Part D

Scripts: `part_d/rag.py` (tasks 1 to 4, policy assistant and its evaluation) and `part_d/agent.py` (tasks 5 to 8, refund agent). Every model call goes through `mock_llm.py`; there is no network call or API key.

### Chunking, retrieval and answering

Each of the five policy files is split into chunks of 40 words with an overlap of 10 (next chunk starts 30 words later; stop after the first chunk that reaches the last word). The source file name is stored with every chunk. Result: **15 chunks** (refund 4, delivery 3, escalation 3, payment 3, privacy 2).

`TfidfVectorizer()` is fitted on the chunk texts; a query is transformed by the same vectorizer and chunks are ranked by cosine similarity. `retrieve(query, k=3)` returns dictionaries with `source`, `score`, `text`. For the query "refund policy late delivery" the top three chunks all come from `refund_policy.txt` (scores 0.272, 0.251, 0.245).

TF (term frequency) measures how often a word appears in a chunk; IDF (inverse document frequency) down-weights words that appear in many chunks, so rare, informative words count more. A limitation is that TF-IDF matches words, not meaning: a question phrased with different words than the policy (for example "money back" versus "refund") scores near zero.

`answer(question)` retrieves three chunks and sends two messages to `mock_llm.chat`: a system message containing POLICY ASSISTANT (answer only from the context, otherwise say the information could not be found) and a user message `CONTEXT:`, newline, the chunks each prefixed with `[<file name>]` on its own line, newline, `QUESTION:`, newline, the question. It returns the text and the sources used.

### Evaluation on `policy_eval.csv`

| Setting | Chunks | Answerable: expected doc in top 3 | Answerable: expected fact in answer | Unanswerable: fallback "I could not find..." |
|---|---|---|---|---|
| 40 words, overlap 10 | 15 | 12/12 | 12/12 | 2/2 |
| 40 words, overlap 0 | 13 | 12/12 | 10/12 | 2/2 |

With zero overlap two questions break, both because the answer sentence is split across a chunk boundary. "What delivery time makes a completed order eligible for a full refund?" returns "receives a full refund of the order amount." because the first half of the sentence, which holds "more than 45 minutes", ended up at the end of the previous chunk. "How soon is money returned when a payment fails but is deducted?" returns a sentence cut off after "returned automatically", so the fact "48 hours" fell into the next chunk. Overlap repeats the last 10 words of each chunk at the start of the next one, which keeps such sentences whole.

### Tools

Five tools are defined with a name, description and parameter specification in `TOOLS_SPEC`, and a dictionary `TOOL_MAP` maps each name to its Python function. `get_order` reads `data/instamart.db`; `search_policy` returns the retrieval results under `results`; `calculate_refund` returns 100% of the order amount if delivery took more than 45 minutes, otherwise 0; `issue_refund` and `escalate_to_human` each append a JSON line (timestamp, tool name, order id, amount, run id) to `outputs/refund_ledger.jsonl`. The model asks for a tool by name with an arguments dictionary, and the code looks it up in `TOOL_MAP`.

### ReAct loop results (`run_agent`, defaults: 6 iterations, 6000 tokens, 10 seconds)

| Scenario | Status | Refund (INR) | Expected | Model calls | Tokens used |
|---|---|---|---|---|---|
| S1 | REFUND | 128.25 | 128.25 | 5 | 1,077 |
| S2 | REFUND | 135.00 | 135.00 | 5 | 1,077 |
| S3 | ESCALATE | 1999.00 | 1999.00 | 5 | 1,064 |
| S4 | DENIED | 0.00 | 0.00 | 4 | 749 |
| S5 | DENIED | 0.00 | 0.00 | 3 | 445 |
| S6 | NOT_FOUND | 0.00 | 0.00 | 2 | 144 |
| S7 | FALLBACK_MAX_ITERATIONS | 0.00 | 0.00 | 6 | 3,216 |

All seven match the expected outcome and refund (within 0.01). S7 uses all six model calls with the default token limit of 6000 and ends with `FALLBACK_MAX_ITERATIONS`. The S3 escalation of INR 1999.00 is recorded in the ledger but not paid out automatically. One JSON line per run (scenario id, status, final answer, model calls, tokens, and every step's tool, arguments and observation) is in `outputs/agent_runs.jsonl`.

### Stop-safely demonstrations

| Demo | Result |
|---|---|
| S1 with `token_limit=200` | `FALLBACK_TOKEN_LIMIT` (462 tokens after the third model call; the tool requested then was not executed; steps so far: get_order, search_policy) |
| S1 with `time_limit_seconds=0` | `FALLBACK_TIMEOUT` (stopped before the first model call, 0 calls) |

Each fallback returns the steps completed and a short handoff summary in `final_answer`. These demo runs are printed by the script and are not part of `agent_runs.jsonl`.

### Crash and resume

After every tool observation a checkpoint is written to `state/<run_id>.json` (run id, scenario id, full message list, tokens used, step number, tools executed). S1 was run with a simulated crash right after the second tool (after its checkpoint was saved), then `resume_agent("S1-crash-demo")` continued from the checkpoint. Tools executed across the crash and the resume, in order: **get_order, search_policy, calculate_refund, issue_refund**, four executions with none repeated. Final status REFUND with INR 128.25. The ledger therefore contains one extra `issue_refund` line for ORD-100048 tagged with the run id `S1-crash-demo`; this is the demo, not a second real refund (ledger lines carry the run id for that reason).

### ReAct versus plan-and-execute

My ReAct agent made 5 model calls for S1, S2 and S3, 4 for S4, 3 for S5, 2 for S6 and 6 for S7, using 1,077 tokens for S1 and only 144 for the NOT_FOUND case S6. A plan-and-execute design asks the model for the whole step list once and replans only on error. For a normal refund that would be about 2 model calls instead of 5, and fewer tokens, because the growing message history (including the policy chunks) is not re-sent at every step. I did not build it, so that saving is an estimate, not a measurement. ReAct pays for the extra calls but reacts to each observation: a NOT_FOUND order stopped after 2 calls and a cancelled order after 3, because the model saw the observation and ended the run. A fixed plan would carry on until a replan was triggered, or each step would need its own error check. For this refund workflow I would choose ReAct: the path is short (at most six steps), money is involved so each decision should see the latest observation, and the extra tokens are small. Plan-and-execute becomes attractive when the step list is long and predictable, or when model calls are slow or priced per token.

## Limitations and Next Steps

- All four Parts are implemented.
- The Premium flag is a post-hoc whole-window label (its RFM includes September, which defines the lapse label), so the retention list is illustrative and not a leakage-free evaluation.
- The lapse test set has only 232 customers (89 lapsed), so the F1 differences between the two models (0.648 versus 0.655) are within noise.
- The triage classifier is a keyword-based mock, so its accuracies (85.7% and 100%) say nothing about a real language model; the 9 invalid outputs are simulated faults.
- Median imputation of delivery time uses the category median and ignores city and time of day.
- Dependency versions are pinned to what was installed on the author's machine (pandas 3.1.0); reference values were verified against these versions.
