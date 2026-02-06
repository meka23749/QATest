# QA & Stability Test (Python)

This project is a small QA /stability test for HTTP-based services.
It was created to demonstrate how availability, latency and basic
functional correctness can be tested in an automated and reproducible way.

## Features

- Repeated HTTP checks over time
- Latency measurement (p50 / p95)
- Availability calculation
- Structured logging
- JSON reports
- Optional Docker log collection

## Typical Use Case

- Test a local service or container
- Validate stability before deployment
- Provide reproducible QA evidence

## Example

```bash
python qa_test.py \
  --url http://127.0.0.1:8000/health \
  --duration 30 \
  --interval 1 \
  --expected OK
```
