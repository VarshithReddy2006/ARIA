# ARIA Operating-Point Analysis (v5)

## 1. Operating Point Comparison (SAFE vs BALANCED vs EXPLORATORY)

| Operating Mode | Confidence Tiers Included | File Precision | File Recall | File F1 | File FPs | Test F1 (RAW) | Test F1 (VALID GT) | Recommended Developer Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **SAFE** | **HIGH Only** | **23.2%** | 48.3% | **29.9%** | **77** | **28.5%** | **36.4%** | Zero-noise ground truth for automated CI gate |
| **BALANCED (Default)** | **HIGH + MEDIUM** | **9.5%** | **63.3%** | **16.0%** | **314** | **32.0%** | **41.0%** | Optimal daily developer workflow (verified + likely) |
| **EXPLORATORY** | **ALL (HIGH+MED+LOW)** | 9.4% | 75.0% | 16.0% | 417 | 29.7% | 35.5% | Major refactor audit & peripheral discovery |

---

## 2. Per-Repository Operating Breakdown

### FastAPI (`fastapi/fastapi`)
- **SAFE**: File F1 = 15.0%, Test F1 (RAW) = 25.9%
- **BALANCED**: File F1 = 14.8%, Test F1 (RAW) = 5.5%

### Requests (`psf/requests`)
- **SAFE**: File F1 = 61.2%, Test F1 (RAW) = 44.4%
- **BALANCED**: File F1 = 29.9%, Test F1 (RAW) = 88.9%

### ARIA (`VarshithReddy2006/ARIA`)
- **SAFE**: File F1 = 17.5%, Test F1 (RAW) = 18.5%
- **BALANCED**: File F1 = 6.5%, Test F1 (RAW) = 9.2%

---

## 3. Recommendation
**BALANCED** is selected as the authoritative default:
- It achieves **39.8% valid GT test F1** and **16.0% file F1**.
- It provides a comprehensive safety net including helper chains and re-exports without flooding developers with unverified peripheral noise.
