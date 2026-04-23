# Data Sources - EXCLUSIVE CRAWL4AI TARGETS

## 1. Smartphone Supply Chain

### TSMC Fab 18 (Hsinchu, Taiwan)
- **Source 1 (Local Tech News Archive):** `https://www.taiwannews.com.tw/archive/` (You'd navigate this to find actual yearly/monthly archive pages if they exist)
    - **Example Seed URL for crawl4ai:** `https://www.taiwannews.com.tw/archive/2023/10` (if such a page exists)
- **Source 2 (Taiwan Government News/Press Releases):** `https://english.ey.gov.tw/News_Publish/` (Executive Yuan, might have relevant policy news)
    - **Example Seed URL for crawl4ai:** `https://english.ey.gov.tw/News_Publish/45?page=1` (and iterate pages)

### Foxconn Plant (Zhengzhou, China)
- **Source 1 (Chinese Local News Archive - Example):** `http://www.zhengzhou.gov.cn/zwdt/zzyw/` (Zhengzhou Government News, may have local industry updates. *Note: Chinese sites might have different character encodings or require specific handling.*)
    - **Example Seed URL for crawl4ai:** `http://www.zhengzhou.gov.cn/zwdt/zzyw/index_1.html` (and iterate pagination)
- **Source 2 (Industry Blog/Forum - Hypothetical):** `https://manufacturinghub.cn/forum/foxconn-discussions` (You MUST find a real, public-facing forum)
    - **Example Seed URL for crawl4ai:** `https://some-manufacturing-forum.com/category/supplychain-issues/`

### Port of Long Beach (California, USA)
- **Source 1 (Official Port News Archive):** `https://polb.com/news/archive/`
    - **Example Seed URL for crawl4ai:** `https://polb.com/news/archive/` (and let it discover year/month links, or provide specific ones)
- **Source 2 (Logistics Industry News Portal - Example):** `https://www.shippingwatch.com/latest_news/`
    - **Example Seed URL for crawl4ai:** `https://www.shippingwatch.com/latest_news/` (and look for pagination/archives)

# ... (Sources for your other supply chains, following this pattern)