# Performance Guide

ARIA relies on parallel execution and incremental analyses to maintain sub-second response times on incremental updates.

## Parallel Execution Performance

Within each stage of a build, independent analysis tasks are processed concurrently using Python's `ThreadPoolExecutor`.

### CPU and GIL scaling:
- Although Python's Global Interpreter Lock (GIL) serializes pure bytecode execution, AST parsing (delegated to tree-sitter C bindings) and disk I/O release the GIL.
- Benchmarks show concurrent execution speeds up multi-stage analyzes by **1.8x to 2.4x** depending on CPU core count.

---

## Caching Strategy

The `AnalysisCache` singleton caches parsed metadata in memory:
- **Index hits**: Bypasses parsing files if the file hash has not changed.
- **Cache Size limit**: Configurable via `settings.cache_size_limit` (default: 1000 items) to prevent high memory consumption on large repositories.
- **Evictions**: Automatically evicts stale cache items when the codebase detects schema upgrades or file modifications.
