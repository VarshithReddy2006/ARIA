# Storage Architecture & Access Patterns (Phase 7 Audit)

## 1. Data Classification Matrix

| Data Asset | Lifecycle Category | Volume / Frequency | Recommended Target | Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **SQLite DB (`repo_understanding.db`)** | Durable | Read-heavy by Web, Write-burst by Worker | **Azure Files mount (`/app/data`)** | SQLite requires direct POSIX filesystem locking and WAL mode support. Azure Files provides standard SMB/NFS share accessible by both Web and ACA Job instances. |
| **JSON Snapshots (`data/snapshots/*.json`)** | Durable | Read on sub-page load, Atomic write on analysis | **Azure Files mount (`/app/data`)** | Atomic `.tmp` + `os.replace` requires a shared POSIX-compliant filesystem mounted to all containers. |
| **Qdrant Vector Data (`data/qdrant/`)** | Durable / Reconstructable | Read during Chat/RAG, Batch upsert during analysis | **Azure Files mount (`/app/data`)** | Local Qdrant embedded engine persists segments to disk. Storing on `/app/data` ensures vectors survive container scale-to-zero. |
| **Cloned Git Repos (`cloned_repos/`)** | Ephemeral / Cacheable | High I/O burst during analysis | **Container-local Ephemeral Storage (`/tmp`)** | Ephemeral storage has zero Azure storage costs and high NVMe IOPS. Storing cloned code in `/tmp` avoids inflating Azure Files storage bills. |
| **BGE HuggingFace Model Weights** | Cacheable | Loaded into container RAM on warmup | **Container Image / Local Cache** | Baked directly into the image or cached in ephemeral RAM, requiring 0 external storage calls. |

---

## 2. Storage Recommendation Summary

1. **Azure Files (Standard LRS, Transaction-Optimized)**:
   - Mount to `/app/data` (5 GB capacity is sufficient for 50+ repositories).
   - Monthly cost: ~$0.30/month.
2. **Container-local Ephemeral Storage**:
   - Used for Git clones and temporary files (`/home/appuser/.repo_intelligence/cloned_repos`).
   - Cost: $0.00 (Included free in ACA vCPU allocation).
3. **Blob Storage**:
   - Not required for initial student deployment. Avoids adding an Azure Blob Storage SDK abstraction layer.
