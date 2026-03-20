# Bot Ecosystem – Port Allocation Table

## Master Range
50000–54999 → Bot ecosystem services

---

## 50000–50099 → Health & Monitoring

| Port  | Service |
|------:|---------|
| 50000 | Health Check Controller / Aggregator |
| 50001 | Bot 01 – Health Endpoint |
| 50002 | Bot 02 – Health Endpoint |
| 50003 | Bot 03 – Health Endpoint |
| 50004 | Bot 04 – Health Endpoint |
| 50005 | Bot 05 – Health Endpoint |
| 50006 | Bot 06 – Health Endpoint |
| 50007 | Bot 07 – Health Endpoint |
| 50008 | Bot 08 – Health Endpoint |
| 50009 | Bot 09 – Health Endpoint |
| 50010 | Bot 10 – Health Endpoint |
| 50011 | Scraper Bot – Health Endpoint |

---

## 51000–51099 → Bot Runtime / IPC Services

| Port  | Service |
|------:|---------|
| 51001 | Bot 01 – IPC / Internal Service |
| 51002 | Bot 02 – IPC / Internal Service |
| 51003 | Bot 03 – IPC / Internal Service |
| 51004 | Bot 04 – IPC / Internal Service |
| 51005 | Bot 05 – IPC / Internal Service |
| 51006 | Bot 06 – IPC / Internal Service |
| 51007 | Bot 07 – IPC / Internal Service |
| 51008 | Bot 08 – IPC / Internal Service |
| 51009 | Bot 09 – IPC / Internal Service |
| 51010 | Bot 10 – IPC / Internal Service |

---

## 52000–52099 → Internal APIs (Shared)

| Port  | Service |
|------:|---------|
| 52000 | User / Identity API |
| 52001 | Economy API |
| 52002 | Music Library API |
| 52003 | Timer / Reminder API |
| 52004 | Permissions / Roles API |
| 52005 | Logging / Audit API |

---

## 53000–53049 → Scrapers / Workers

| Port  | Service |
|------:|---------|
| 53000 | Scraper Controller |
| 53001 | Scraper Bot – IPC |
| 53002 | External Site Ingestion Worker |
| 53003 | Scheduled Data Sync Worker |

---

## 54000–54049 → Web Dashboards / Admin UIs

| Port  | Service |
|------:|---------|
| 54000 | Admin Dashboard |
| 54001 | Metrics / Monitoring UI |
| 54002 | Bot Control Panel |

---

## Key / Legend

- **500xx** → Health & monitoring
- **510xx** → Per-bot runtime services
- **520xx** → Shared internal APIs
- **530xx** → Scrapers & background workers
- **540xx** → Web dashboards & admin tools

---

## Notes

- One bot = one health port + one runtime port
- Scraper bots follow the same health pattern
- Leave unused ports empty for future expansion
- Dev environment can mirror this table using +1000 offset
