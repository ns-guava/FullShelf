# FullShelf validation brief and improvement questions

**Status:** Product-discovery plan; completion of the proposed interviews and concierge tests has not been verified.
**Engineering status:** A working FullShelf prototype exists. This document is a product-discovery plan, not an engineering readiness verdict. See `README.md` for implemented functionality, technical assumptions, and test instructions.
**Scope:** FullShelf, the CSV-to-reorder-priorities prototype.

Commercial assumptions and pricing experiments below are retained as historical product-discovery context. They are outside the AI engineering review scorecard and are not evidence that the planned research was completed.

---

## 1. Why this document exists

The prototype proves the mechanics work: CSV validation, deterministic coverage and reorder math, ranked priorities, and a Gemini assistant that explains Python-calculated facts without inventing numbers.

It does **not** prove that anyone needs it, has the data to run it, will keep using it, or will pay for it. This brief turns the council critique into a short validation programme and a set of questions for improving the product.

---

## 2. Council summary

| Advisor | Main objection | What it means for validation |
|---|---|---|
| The Contrarian | Owners do not maintain clean demand and lead-time data; CSV upload is friction; no execution workflow. | Test data availability and upload habit before adding features. |
| The First Principles | The real job is "what do I order this week, with limited cash", not "show me coverage days". | Ask how orders are actually decided today. |
| The Expansionist | Strong wedge if focused on one vertical and one geography; WhatsApp and wholesale distribution are natural expansions. | Pick one vertical for interviews. |
| The Outsider | It reads as a demo, not a product: no login, no persistence, no support or terms. | Test whether trust and workflow, not features, block adoption. |
| The Investor | Low ARPU, high support cost, no moat, churn-heavy category. | Test willingness to pay early, not after building. |
| The Judge | Four core assumptions are unvalidated. | Run the 14-day plan below. |

---

## 3. The four assumptions to test

| ID | Assumption | Why it matters | Evidence required |
|---|---|---|---|
| A1 | Owners have, or can reasonably estimate, average daily demand, supplier lead time, and unit cost per SKU. | Without this, every calculation is confident guesswork. | A real stock file or credible verbal estimate from at least half of interviewees. |
| A2 | Owners will refresh the data weekly or before each order. | A one-off analysis does not prevent stockouts. | At least a third return with updated data within two weeks. |
| A3 | A ranked priority list changes what they order. | Insight without action has no value. | At least 40% place or change an order because of the list. |
| A4 | Owners will pay R99 to R299 per month per store. | A free tool with no revenue is a hobby. | Three or more prepayments or signed paid pilots. |

---

## 4. Fourteen-day validation plan

| Days | Activity | Output |
|---|---|---|
| 1 to 3 | Recruit 10 to 15 owners in one vertical (for example, independent beauty and skincare stores). | Interview schedule. |
| 4 to 7 | Run 20 to 25 minute interviews using the script in section 5. | Notes coded against A1 to A4. |
| 5 to 12 | Concierge test: collect a real stock file, run the analysis manually, send a WhatsApp reorder list. | Action and response log. |
| 10 to 12 | Follow up on whether they ordered, changed quantities, or ignored the list. | A3 evidence. |
| 12 to 14 | Ask for updated data and offer a paid pilot. | A2 and A4 evidence. |
| 14 | Score against section 6 and write the verdict. | Proceed, pause, or kill decision. |

**Rule:** do not write production code during these two weeks. The only artefacts are interview notes, the concierge log, and the scorecard.

---

## 5. Interview script

### Warm-up (3 minutes)
1. Tell me about your store: what do you sell, how long have you run it, and who works with you?
2. Walk me through a normal week of stock work.

### How decisions happen today (7 minutes)
3. How do you decide what to order and how much?
4. Show me the last time you ran out of something. What happened?
5. What did you do the last time you had too much of something?
6. How do you decide how much cash to tie up in stock?
7. Who else influences the order, and what do they care about?

### Data reality (5 minutes)
8. Where does your stock information live: notebook, spreadsheet, POS, supplier portal?
9. How do you estimate daily or weekly sales for a product?
10. How do you know each supplier's lead time? What happens when they are late?
11. Could you export or photograph your current stock list today?

### Tools and trust (5 minutes)
12. What do you use now, and what do you hate about it?
13. Have you tried inventory software? Why did you stop?
14. Would you trust an AI summary of what to reorder? What would make you trust it more?
15. What would you never let an AI decide for you?

### Value and payment (5 minutes)
16. If this prevented one stockout a month, what would that be worth to you?
17. Would you pay R99 per month today for a tool that produced this list? Why or why not?
18. What would make you switch from your current method within a week?

### Closing
19. Who else should I speak to?
20. May I use your stock file for a free reorder review this week?

---

## 6. Concierge test protocol

1. Ask for a CSV export, spreadsheet, or clear photos of the stock sheet.
2. Record how long it takes to get usable data and what is missing.
3. Run the deterministic analysis manually. Do not use the AI assistant for calculations.
4. Send one WhatsApp message with:
   - the top five reorders,
   - the reason for each (coverage versus lead time),
   - the assumptions used (average demand, zero safety stock, lead time),
   - one question: "Would you order this?"
5. Log the response within 48 hours: ordered, changed quantity, disagreed, or ignored.
6. Follow up after seven days with one question: "Did the list change what you bought?"

**Do not** send a dashboard link yet. The test is whether the recommendation changes behaviour, not whether the UI is liked.

---

## 7. Scorecard and decision thresholds

| Metric | Proceed | Pause or reframe | Kill |
|---|---|---|---|
| Usable data from interviewees (A1) | 50% or more | 30% to 49% | Below 30% |
| Acted on the reorder list (A3) | 40% or more | 20% to 39% | Below 20% |
| Returned with updated data (A2) | 30% or more | 10% to 29% | Below 10% |
| Prepay or signed paid pilot (A4) | 3 or more | 1 to 2 | 0 |
| Interviews naming stockouts or overstock in their top three pains | 8 of 15 or more | 4 to 7 | 3 or fewer |

**Proceed:** build the smallest paid pilot, focused on the chosen vertical.
**Pause or reframe:** the pain may be real but the data or workflow is wrong. Consider supplier-provided lead times, POS integration, or a done-for-you service.
**Kill:** the pain is not strong enough, owners will not act, and nobody will pay.

---

## 8. Questions for improvement

Use these to decide what the pilot should build, not what the demo should add.

### Data and onboarding
- Can we accept messy exports with a column-mapping step instead of a strict template?
- Can lead time be inferred from past order and delivery dates?
- What is the minimum viable input if an owner does not know daily demand?
- Can we support a simple stock count plus a weekly sales number instead of both?
- How do we show data freshness and confidence on every number?

### Decision support
- Should the tool include a cash budget for the week?
- Should pack sizes and supplier minimums cap the suggested quantity?
- Should shelf life and expiry affect priority?
- Should dead stock and slow movers be a first-class view?
- Should there be a what-if order simulator before committing cash?
- Should the tool show the cost of the current plan versus the suggested plan?

### Workflow
- Can the output become a WhatsApp-ready or PDF order list per supplier?
- Should the tool track orders placed versus received?
- Should it remind the owner to refresh data before the next delivery?
- Can it reconcile a delivery against the expected order?
- Does it need multi-store or multi-user support for the pilot?

### Trust and AI
- Should every ranking show a "why this rank" explanation?
- Should assumptions appear inline next to the affected metric?
- Should the assistant be allowed to challenge a decision, not just explain it?
- Should there be a council or red-team mode with multiple perspectives?
- What should the AI explicitly refuse to answer or decide?
- How do we prove the AI never calculates business metrics?

### Business model
- Which vertical first: beauty, pharmacy, pet, hardware, or food?
- Which geography and currency first?
- Is the model freemium, a paid pilot, or a done-for-you service?
- Would a wholesaler pay to distribute this to its retail customers?
- What would make an owner switch from Excel within one week?
- What support level can we afford at R99 to R299 per month?

### Differentiation
- What can FullShelf do that a spreadsheet cannot?
- What can it do that Shopify, Zoho, Cin7, or Unleashed will not do for this segment?
- Is "explicit assumptions and no fake metrics" a promise we can market?
- Is speed to first useful answer the wedge: CSV in, list out, under a minute?

---

## 9. What would upgrade the verdict to Proceed

Any one of these removes the biggest unknown:

- A POS or e-commerce integration partner that supplies clean stock and sales data.
- A wholesaler willing to distribute or co-sell to its retail customers.
- Five paying stores with week-4 retention.
- Evidence that the priority list repeatedly changes purchase decisions.

---

## 10. Open decisions

- [ ] Choose the first vertical.
- [ ] Build the 15-owner recruitment list.
- [ ] Approve the interview script.
- [ ] Create the WhatsApp concierge template.
- [ ] Decide the paid-pilot price and terms.
- [ ] Set the review date for the scorecard and verdict.
