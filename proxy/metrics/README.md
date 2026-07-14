### Queue Predictor

The queue predictor estimates the time from when the proxy enqueues a task on an instance until the first token is received. The estimate includes prefill time and queue waiting time.

After writing data to `ttft_benchmark_table.json`, run `python3 ttft_four_term_regressor.py` to fit the prediction model and write parameters to `ttft_coefficient.json`.

Quick validation for the regression:

```bash
python3 ttft_four_term_regressor.py
```

### Redis Pull-Time Regression

When you have an experiment table with fields like `kvcache_size_gb, redis_pull_ms_1..N`, run the regressor with CSV or JSON input support.

It writes linear coefficients in milliseconds to `proxy/metrics/redis_pull_coefficients.json`.

JSON input examples are supported for both top-level arrays and objects whose samples are stored under `rows`, `data`, or `samples`.

If samples omit `kvcache_size_gb` but include `actual_hit_length_tokens`, provide a conversion factor so the fitter derives `kvcache_size_gb = actual_hit_length_tokens * kv_gb_per_token`.

The predictor side can call the unified prediction helpers directly. The recommended output reports both `text-based` pure compute estimates from `--length` and `kvcache-based` estimates when `--knowledge-length` is supplied, including aligned hit length, KVCache size, remaining compute length, remaining text compute time, Redis pull time, and pull-plus-recompute time.
