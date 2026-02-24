#!/usr/bin/env python3
"""Spike 1.0: measure embedding latency and chunk overlap Recall@5.

Usage:
    python scripts/spike_embeddings.py --ollama-url http://localhost:11434
"""
import argparse
import json
import statistics
import time
from pathlib import Path

import httpx


def embed_batch(url: str, model: str, texts: list[str]) -> list[list[float]]:
    resp = httpx.post(f"{url}/api/embed", json={"model": model, "input": texts}, timeout=120)
    resp.raise_for_status()
    return resp.json()["embeddings"]


def measure_latency(url: str, model: str, n: int = 1000) -> dict:
    texts = [f"Sample chunk number {i} with some content for testing." for i in range(n)]
    batches = [texts[i:i+200] for i in range(0, len(texts), 200)]
    latencies = []
    for batch in batches:
        t0 = time.perf_counter()
        embed_batch(url, model, batch)
        latencies.append((time.perf_counter() - t0) / len(batch))

    return {
        "n": n, "model": model,
        "p50_ms": round(statistics.median(latencies) * 1000, 2),
        "p95_ms": round(sorted(latencies)[int(0.95 * len(latencies))] * 1000, 2),
        "mean_ms": round(statistics.mean(latencies) * 1000, 2),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    args = parser.parse_args()

    results = {}
    for model in ["nomic-embed-text", "all-minilm"]:
        print(f"Testing {model} @ 1k chunks...")
        try:
            results[model] = {
                "1k": measure_latency(args.ollama_url, model, 1000),
                "10k": measure_latency(args.ollama_url, model, 10000),
            }
        except Exception as e:
            results[model] = {"error": str(e)}

    print(json.dumps(results, indent=2))
    out = Path("docs/spike-1.0-results.json")
    out.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to {out}")
