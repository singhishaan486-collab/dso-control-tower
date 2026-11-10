# Data dictionary

Snapshot date for all files: **2026-11-09**. All names, IDs, IBANs and person codes are fake.

**known_at** is the leakage rule. `Contract` and `Invoice` columns are known on the day the invoice is raised and may be model features. `Later` columns may never be features for a model that predicts at invoice stage.

## invoices.csv (history: service months Jul 2024 to Sep 2026, 1,437 raw rows)

| column | group | known_at | meaning | use |
|---|---|---|---|---|
| `invoice_id` | ID | Invoice | Unique invoice number | Key |
| `client_id` | ID | Contract | Client code | Key; clustering grain |
| `service_month` | ID | Invoice | Month the staff were deployed (YYYY-MM) | Time split |
| `month_end_date` | Dates | Invoice | Last day of the service month | Stage start |
| `signoff_date` | Dates | Invoice | Date client signed the timesheet (blank if invoiced unsigned) | Stage duration |
| `invoice_date` | Dates | Invoice | Date invoice was raised | Split key; DSO clock starts |
| `due_date` | Dates | Invoice | invoice_date + payment_terms_days | Defines paid_late |
| `wps_pay_date` | Dates | Invoice | Date salaries for that month are due under WPS (1st of next month) | Cash gap |
| `sector` | Client profile | Contract | Mall, Office, Residential, Hospital, Government, Hospitality (raw file has typos) | Feature; clustering descriptor |
| `client_ownership` | Client profile | Contract | Government, Semi-government, Private large, Private SME | Feature |
| `emirate` | Client profile | Contract | Dubai, Abu Dhabi, Sharjah | Feature |
| `service_line` | Client profile | Contract | Security, Technical (MEP), Front office and supervision | Feature |
| `payment_terms_days` | Client profile | Contract | 30, 45, 60 or 90 | Feature |
| `billing_basis` | Client profile | Contract | Per head per month or Per hour | Feature |
| `approval_layers` | Client profile | Contract | Steps in the client's invoice approval chain (1 to 4) | Feature |
| `heads_contracted` | Client profile | Contract | Contracted headcount | Feature |
| `attendance_method` | Client profile | Contract | Paper, Biometric or App (raw file has blanks) | Feature; association item |
| `submission_channel` | Client profile | Contract | Email, Client portal, Hand delivery | Feature |
| `sla_penalty_clause` | Client profile | Contract | 1 if contract allows SLA penalty deductions | Feature |
| `prev_invoices_paid` | Client history | Invoice | Client invoices already PAID before this invoice date | Feature |
| `prev_avg_days_to_pay` | Client history | Invoice | Average days to pay of those paid invoices (blank for new clients) | Feature |
| `prev_late_rate` | Client history | Invoice | Share of those paid invoices that were late | Feature |
| `prev_dispute_rate` | Client history | Invoice | Share of those paid invoices that were disputed | Feature |
| `last_paid_invoice_late` | Client history | Invoice | Was the most recently paid invoice late | Feature |
| `open_invoices_count` | Client history | Invoice | Client invoices still unpaid on this invoice date | Feature |
| `open_amount_aed` | Client history | Invoice | AED still unpaid by the client on this date | Feature |
| `heads_deployed` | Operations | Invoice | Staff actually deployed | Feature |
| `headcount_gap_pct` | Operations | Invoice | % shortfall against contract | Feature; association item |
| `relief_worker_share` | Operations | Invoice | Share of shifts covered by relief staff | Feature |
| `absence_rate` | Operations | Invoice | Share of shifts missed (raw file has blanks) | Feature |
| `ot_hours` | Operations | Invoice | Overtime hours billed (raw file has blanks) | Feature |
| `ot_preapproved` | Operations | Invoice | 1 if client approved the OT beforehand | Feature; association item |
| `timesheet_variance_hours` | Operations | Invoice | Hours difference between our count and the client's at sign-off | Feature; association item |
| `timesheet_status` | Invoice prep | Invoice | Signed, Signed with remarks, Unsigned | Feature; association item |
| `days_to_signoff` | Invoice prep | Invoice | Days from month end to sign-off (blank if unsigned) | Feature |
| `days_monthend_to_invoice` | Invoice prep | Invoice | Days from month end to invoice | Feature |
| `lpo_number` | Invoice prep | Invoice | LPO referenced | Lookup key |
| `lpo_status` | Invoice prep | Invoice | Valid, Not yet renewed, Insufficient balance, Missing on invoice | Feature; association item |
| `lpo_valid` | Invoice prep | Invoice | 1 if lpo_status is Valid | Feature |
| `lpo_balance_before_aed` | Invoice prep | Invoice | LPO balance before this invoice | Feature; LPO guard |
| `rate_matches_contract` | Invoice prep | Invoice | 1 if billed rate equals contract rate | Feature; invoice QA |
| `docs_attached` | Invoice prep | Invoice | 1 if signed timesheet and backup attached | Feature; invoice QA |
| `sla_deduction_aed` | Invoice prep | Invoice | SLA deduction we applied ourselves | Feature |
| `invoice_amount_aed` | Invoice prep | Invoice | Gross amount incl. 5% VAT (raw file has a few x10 errors) | Feature; DSO weighting |
| `payroll_cost_aed` | Invoice prep | Invoice | Payroll cost of the staff on this invoice | Margin; cash gap |
| `client_ack_date` | After invoice | Later | Date client acknowledged receipt | LEAKS. Diagnostic stage only |
| `dispute_raised` | After invoice | Later | 1 if client disputed | TARGET for dispute model; never a feature for paid_late at invoice stage |
| `dispute_reasons` | After invoice | Later | Reason codes separated by '; ' | LEAKS. Association rules, triage labels |
| `dispute_raised_date` | After invoice | Later | Date dispute was raised | Diagnostic stage |
| `dispute_resolved_date` | After invoice | Later | Date dispute was settled | Diagnostic stage |
| `disputed_amount_aed` | After invoice | Later | Value under dispute | LEAKS. Diagnostic |
| `dispute_resolution` | After invoice | Later | Credit note, Reissued invoice, Withdrawn by client, Open | LEAKS. Diagnostic |
| `first_followup_date` | After invoice | Later | Date collections first chased | LEAKS. Diagnostic |
| `short_paid_aed` | After invoice | Later | Amount the client did not pay | LEAKS. Diagnostic |
| `payment_date` | After invoice | Later | Date cash received (blank if still open on 2026-11-09) | Builds targets |
| `invoice_status` | After invoice | Later | Paid or Open on the snapshot date | Filter; aging |
| `days_to_pay` | Target | Later | payment_date minus invoice_date | Regression target |
| `paid_late` | Target | Later | 1 if paid after due_date | Classification target |

## current_batch.csv

Draft invoices for the October 2026 service month, not yet sent. Same columns as invoices.csv up to `payroll_cost_aed` (everything known at invoice stage), no outcomes. Used by the automation checks and live risk scoring.

## clients.csv

One row per client: profile columns above plus `client_name`, `rate_per_head_aed`, `contract_start_month`.

## lpos.csv

| column | meaning |
|---|---|
| `lpo_number` | LPO id |
| `client_id` | client |
| `covers_from` | first service month the LPO covers |
| `valid_from` | month the client actually issued it (later than covers_from means renewal lag) |
| `valid_to` | last month covered |
| `lpo_value_aed` | total value |

## payroll.csv (Jun to Oct 2026, one row per employee per month)

| column | meaning |
|---|---|
| `employee_id`, `person_code`, `client_id`, `trade` | worker and deployment |
| `basic_salary_aed`, `allowances_aed` | monthly pay components |
| `iban_on_file` | 1 if salary account recorded |
| `payroll_month`, `days_in_month`, `days_paid`, `lwop_days` | pay period |
| `ot_hours`, `ot_rate_multiplier_used` | overtime and the multiplier payroll applied |
| `fixed_income_aed`, `variable_income_aed` | WPS EDR fixed and variable amounts |
| `wps_due_date`, `pay_date` | due date (1st of next month) and actual pay date |

Planted issues for the WPS checks: late pay dates (more likely at clients who pay us late), OT paid at 1.0x instead of 1.25x, OT above the monthly limit, days_paid above days in month, missing IBAN.

## dispute_emails.csv (448 emails)

| column | meaning |
|---|---|
| `email_id` | id |
| `received_date` | date received |
| `client_id` | sender's client |
| `invoice_id_true` | the invoice it really refers to (ground truth for testing the extractor) |
| `subject`, `body` | email text: informal, typos, invoice numbers in mixed formats or missing |
| `labels` | true reason codes, `; ` separated, multi-label in about 23% of disputes; `NOT_DISPUTE` for payment queries and remittances |
| `is_dispute` | 1 or 0 |

Label counts: TS_MISMATCH 156, OT_UNAPPROVED 117, NOT_DISPUTE 89, HC_DISCREPANCY 62, LPO_ISSUE 48, DOCS_MISSING 29, SLA_PENALTY 25, RATE_DISPUTE 23, SERVICE_QUALITY 3 (too rare to learn; route to human).

## Planted data quality issues in invoices.csv

9 exact duplicate rows, 28 sector label typos, blanks in attendance_method (30), ot_hours (22), absence_rate (18), timesheet_variance_hours (15), 5 invoice amounts with an extra zero. `core/data.py` already fixes all of them and logs each step.
