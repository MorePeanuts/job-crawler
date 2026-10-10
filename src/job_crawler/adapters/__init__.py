"""Explicit adapter registration; unknown sites never fall through to guessing."""

from job_crawler.adapters.platforms import CCB, CNPC, Alibaba, Pingan

REGISTRY = {adapter.name: adapter for adapter in (Pingan, CCB, CNPC, Alibaba)}
