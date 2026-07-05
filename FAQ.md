# Frequently Asked Questions — Repo Intelligence Agent

This document answers common technical questions about the Repo Intelligence Agent architecture.

---

### Q: How does repository indexing work?
**A**: Indexing is split into three deterministic pipelines:
1. **Cloning & Detection**: Clones the public repository to local disk and detects language configurations.
2. **AST Parsing (Tree-sitter)**: Scans source files to extract class signatures, functions, imports, and exports. Symbols are stored in SQLite and relationships are populated into a directed NetworkX graph.
3. **Semantic Chunking (ChromaDB)**: Chunks code snippets, embeds them using the `BAAI/bge-small-en-v1.5` model, and inserts them into a local ChromaDB vector store.

---

### Q: How does deterministic retrieval work?
**A**: When a user queries the chatbot (e.g. "Where is the `run_migrations` function defined?"), the system first runs a local **Intent Router** (rule-based keyword classifier) to detect if the query is a symbol lookup. If so, it queries the SQLite AST index directly instead of using semantic search. This guarantees that symbol queries are 100% accurate, eliminating LLM hallucinations.

---

### Q: How does provider failover work?
**A**: During server initialization, the **ProviderManager** validates configured LLM credentials:
1. It sends lightweight validation checks to Google AI Studio and NVIDIA NIM.
2. If the primary provider (Gemini) fails, it updates its routing state to fallback mode.
3. All subsequent chatbot prompts are routed to the fallback provider (DeepSeek V4) until Gemini is validated as healthy again.

---

### Q: How does the call graph work?
**A**: The parser extracts function calls from method bodies. The **Call Graph Service** maps calls to defined functions in the AST database. This directed graph is positioned on the frontend canvas using **Dagre** topological layering. You can filter out library calls or cyclic loops to isolate custom project structures.

---

### Q: Can I analyze private repositories?
**A**: Yes. Provide a valid **GitHub Personal Access Token (PAT)** in your `.env` file under `GITHUB_TOKEN`. The ingestion pipeline will pass this token as authorization headers during cloning.

---

### Q: Are my codebases uploaded to third-party servers?
**A**: **No.** Repository cloning, database storage, tree-sitter parsing, and vector embeddings happen entirely on your local machine. Code snippets only leave your machine if you query the chatbot and have configured a cloud LLM provider (Gemini/Nvidia).
