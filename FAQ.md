# Frequently Asked Questions — ARIA

This document answers common technical questions about the ARIA architecture.

---

### Q: How does repository indexing work?
**A**: Indexing is split into three deterministic pipelines:
1. **Cloning & Detection**: Clones the public repository to local disk and detects language configurations.
2. **AST Parsing (Tree-sitter)**: Scans source files to extract class signatures, functions, imports, and exports. Symbols are stored in SQLite and relationships are populated into a directed NetworkX graph.
3. **Semantic Chunking (ChromaDB)**: Chunks code snippets, embeds them using the `BAAI/bge-small-en-v1.5` model, and inserts them into a local ChromaDB vector store.

---

### Q: How does deterministic retrieval work?
**A**: When a user queries the chatbot (e.g. "Where is the `run_migrations` function defined?" or "Explain backend/api.py"), the system first evaluates **Deterministic Gating**:
1. Explicit file paths, symbol names, functions, snake_case tokens, and backtick expressions resolve directly against the symbol index and file manifest.
2. Common conversational English verbs (e.g. "handle", "build") are protected from hijacking deterministic resolution.
3. If no explicit entity is targeted, the query smoothly transitions to hybrid semantic retrieval with BGE embeddings, ensuring accurate grounding with zero hallucination.

---

### Q: How does provider failover work?
**A**: During runtime orchestration, the **ProviderManager** manages configured candidate providers in priority order:
1. **Priority Chain**: Gemini 3.1 Flash Lite (Primary) → DeepSeek V4 Flash NIM (Secondary) → NVIDIA Llama 3.2 11B Vision → NVIDIA MiniMax M3.
2. **Circuit Breakers**: Each provider is guarded by an individual circuit breaker (`CLOSED`, `OPEN`, `HALF_OPEN`) with a 60s recovery cooldown.
3. **Token-Aware Failover**: If a provider fails when 0 tokens have been emitted, failover immediately advances to the next healthy candidate in the chain. Once tokens have been yielded, failover ceases to prevent stream corruption.
4. **Resilience Boundaries**: Configured timeouts (e.g., `LLM_READ_TIMEOUT=60.0`) guard against upstream NVIDIA queueing delays.

---

### Q: How does the call graph work?
**A**: The parser extracts function calls from method bodies. The **Call Graph Service** maps calls to defined functions in the AST database. This directed graph is positioned on the frontend canvas using **Dagre** topological layering. You can filter out library calls or cyclic loops to isolate custom project structures.

---

### Q: Can I analyze private repositories?
**A**: Yes. Provide a valid **GitHub Personal Access Token (PAT)** in your `.env` file under `GITHUB_TOKEN`. The ingestion pipeline will pass this token as authorization headers during cloning.

---

### Q: Are my codebases uploaded to third-party servers?
**A**: **No.** Repository cloning, database storage, tree-sitter parsing, and vector embeddings happen entirely on your local machine. Code snippets only leave your machine if you query the chatbot and have configured a cloud LLM provider (Gemini/Nvidia).
