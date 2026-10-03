# Data Notes

## Spike Findings

```json
{
  "auth_works": true,
  "rate_limit_headers": {
    "ratelimit_limit": "600",
    "ratelimit_window": "5m"
  },
  "no_data_status_codes": {
    "insolvency": [
      "404"
    ]
  },
  "test_set": {
    "large_plc": "00445790",
    "new_ltd": "17491796",
    "dissolved": "12115175",
    "insolvency": "01468547",
    "no_charges": "17491796",
    "overdue_accounts": "12056899",
    "has_charges": "17016019",
    "corporate_psc": "03977902"
  },
  "calls_per_report_median": 7.0,
  "calls_per_report_max": 11.0,
  "reports_per_5min_at_600_limit": 85,
  "api_p95_ms_per_call": 189,
  "sequential_api_time_s_median_report": 0.3
}
```
