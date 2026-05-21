# Free Components Used in This Project

This project is intentionally built using only free and open-source components. No paid services, API keys, or cloud subscriptions are required for the default workflow.

## Data Sources

### Binance Public Market Data
- **License**: Free to use for market-data-only endpoints
- **Authentication**: Not required for `/api/v3/klines`, `/api/v3/ticker/24hr`, `/api/v3/exchangeInfo`, `/api/v3/trades`
- **Rate Limits**: 1200 request weight per minute (generous for local use)
- **Why**: Binance provides the most liquid crypto markets with reliable public APIs
- **Note**: Trading endpoints require authentication; this project only uses market data

## Database & Analytics

### DuckDB
- **License**: MIT
- **Website**: https://duckdb.org
- **Why**: Fast, embedded, columnar analytics database. Perfect for local data lakehouse workloads. No server required.

## Backend Framework

### FastAPI
- **License**: MIT
- **Website**: https://fastapi.tiangolo.com
- **Why**: Modern, fast, Python web framework with automatic OpenAPI docs and type validation via Pydantic.

### Pydantic
- **License**: MIT
- **Website**: https://docs.pydantic.dev
- **Why**: Data validation using Python type annotations.

## Data Processing

### Polars
- **License**: MIT
- **Website**: https://pola.rs
- **Why**: Extremely fast DataFrame library written in Rust. Much faster than pandas for most operations.

### PyArrow
- **License**: Apache 2.0
- **Website**: https://arrow.apache.org
- **Why**: Columnar memory format, essential for Parquet file I/O.

### httpx
- **License**: BSD 3-Clause
- **Website**: https://www.python-httpx.org
- **Why**: Modern async HTTP client for Python.

## Frontend

### React
- **License**: MIT
- **Website**: https://react.dev
- **Why**: Industry-standard UI library with massive ecosystem.

### TypeScript
- **License**: Apache 2.0
- **Website**: https://www.typescriptlang.org
- **Why**: Type-safe JavaScript. Catches errors at compile time.

### Vite
- **License**: MIT
- **Website**: https://vitejs.dev
- **Why**: Fast build tool and dev server for modern web projects.

### Tailwind CSS
- **License**: MIT
- **Website**: https://tailwindcss.com
- **Why**: Utility-first CSS framework for rapid UI development.

### Recharts
- **License**: MIT
- **Website**: https://recharts.org
- **Why**: Composable charting library built on D3 and React.

## LLM / AI

### Ollama
- **License**: MIT
- **Website**: https://ollama.com
- **Why**: Local LLM runtime. Run models on your own hardware without sending data to third parties.

### Qwen3
- **License**: Apache 2.0
- **Website**: https://qwenlm.github.io
- **Why**: High-quality open model from Alibaba. Available in various sizes (4B, 8B, 14B, 32B, 72B).

## Intentionally Excluded (Paid/Cloud)

The following are **NOT** used by default:

| Service | Why Excluded |
|---------|-------------|
| OpenAI API | Requires API key, per-token cost |
| Gemini API | Requires API key, usage limits |
| Anthropic API | Requires API key, per-token cost |
| AWS (S3, Redshift, etc.) | Cloud subscription, complex setup |
| GCP (BigQuery, etc.) | Cloud subscription, per-query cost |
| Azure (Synapse, etc.) | Cloud subscription |
| Snowflake | Paid analytics warehouse |
| Databricks | Paid lakehouse platform |
| Apache Airflow | Heavy orchestration (optional future addition) |

## Future Additions (Still Free)

- **Apache Spark** (Apache 2.0) - For distributed processing
- **Apache Airflow** (Apache 2.0) - For workflow orchestration
- **Apache Kafka** (Apache 2.0) - For streaming data
- **Grafana** (AGPL 3.0) - For additional dashboards
- **Prefect** (Apache 2.0) - Lightweight orchestration alternative
