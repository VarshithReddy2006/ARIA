# Azure Cost Model & Student Credit Budgeting ($100 Available)

## 1. Free Grants vs. Paid Rates (Azure Container Apps)

### Azure Container Apps Free Grant (Every Month):
- **180,000 vCPU-seconds free per month**
- **360,000 GiB-seconds free per month**
- **First 2 million HTTP requests free per month**

### Azure Container Apps Billed Rates (After Free Grant):
- **vCPU Active**: $0.000024 / vCPU-second
- **Memory Active**: $0.000003 / GiB-second
- **Scale-to-Zero Inactive**: $0.000000 (Completely $0.00 when idle)

### Azure Files (Standard LRS):
- Storage: $0.06 / GB / month
- 5 GB usage: **$0.30 / month**

### Azure Container Registry (Basic):
- $0.167 / day = **$5.00 / month** (or $0.00 if using free GitHub Container Registry `ghcr.io`).

---

## 2. Workload Compute Consumption Per Analysis (`fastapi/fastapi` scale ~245s)

- **Worker Specs**: 1.0 vCPU, 2.0 GiB RAM
- **Active Duration**: 245 seconds
- **vCPU-seconds per run**: $1.0 \times 245 = 245\text{ vCPU-s}$
- **GiB-seconds per run**: $2.0 \times 245 = 490\text{ GiB-s}$
- **Cost per Analysis Run (if billed beyond free tier)**:
  $$\text{vCPU: } 245 \times \$0.000024 = \$0.00588$$
  $$\text{Memory: } 490 \times \$0.000003 = \$0.00147$$
  $$\mathbf{\text{Total Compute Cost Per Run}} = \mathbf{\$0.00735}$$

---

## 3. Monthly Cost Across Analysis Volumes

| Monthly Analysis Volume | Worker Compute Usage (vCPU-s) | Covered by Free Grant? | Paid Compute Cost | Storage Cost (Azure Files) | Total Monthly Burn | Months Sustainable on $100 Credit |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **10 analyses/month** | 2,450 vCPU-s | **100% Free** (Uses 1.3% of grant) | $0.00 | $0.30 | **$0.30 / month** | **>100 months** |
| **50 analyses/month** | 12,250 vCPU-s | **100% Free** (Uses 6.8% of grant) | $0.00 | $0.30 | **$0.30 / month** | **>100 months** |
| **100 analyses/month** | 24,500 vCPU-s | **100% Free** (Uses 13.6% of grant) | $0.00 | $0.35 | **$0.35 / month** | **>100 months** |
| **500 analyses/month** | 122,500 vCPU-s | **100% Free** (Uses 68.0% of grant) | $0.00 | $0.50 | **$0.50 / month** | **>100 months** |
| **1,000 analyses/month** | 245,000 vCPU-s | 180,000 Free, 65,000 Paid | $0.48 | $0.80 | **$1.28 / month** | **78 months** |

> **Conclusion**: Even at **500 full repository analyses per month**, compute consumption is **100% covered by the Azure Container Apps free monthly grant**. The only recurring paid line item is Azure Files storage (~$0.30-$0.50/mo), ensuring the **$100 student credit lasts over 2 years**.
