# Async Architecture

GateKeeper is fully async from the ground up. These 8 rules govern all I/O in the codebase.

## Rule 1: All I/O is async

Every database query, HTTP call, and file read uses `await`.

```python
# Correct
result = await db.execute(select(PipelineRun))

# Wrong — blocks the event loop
result = db.execute(select(PipelineRun))  # missing await
```

## Rule 2: Concurrent evaluators via asyncio.gather

All evaluators in a phase run concurrently, not sequentially.

```python
# Correct
results = await asyncio.gather(*tasks, return_exceptions=True)

# Wrong — sequential execution
for task in tasks:
    result = await task
```

## Rule 3: CPU-bound work in thread pool

sklearn metrics, numpy percentiles, and similar computation runs in `run_in_executor`.

```python
# Correct
metrics = await asyncio.get_running_loop().run_in_executor(
    ctx.cpu_executor,
    _compute_classification_metrics,
    ground_truth,
    predictions,
)

# Wrong — blocks the event loop
metrics = _compute_classification_metrics(ground_truth, predictions)
```

## Rule 4: Async database with asyncpg

All database access uses `postgresql+asyncpg://` and `async_sessionmaker`.

```python
# Correct
engine = create_async_engine("postgresql+asyncpg://...")
async with AsyncSessionFactory() as db:
    await db.execute(...)

# Wrong — sync driver
engine = create_engine("postgresql://...")
```

## Rule 5: Background tasks for long-running work

Eval phases run as FastAPI background tasks, not blocking the request.

```python
# Correct
background_tasks.add_task(run_eval_phases, ...)
return TriggerResponse(status="accepted")

# Wrong — blocks the HTTP response
await run_eval_phases(...)
return TriggerResponse(status="done")
```

## Rule 6: HTTP lifecycle with shared clients

Each adapter maintains a shared `httpx.AsyncClient`, created at startup and closed at shutdown.

```python
# Correct — shared client
async def startup(self):
    self._client = httpx.AsyncClient(...)

async def predict(self, req):
    response = await self._client.post(...)

# Wrong — client per request
async def predict(self, req):
    async with httpx.AsyncClient() as client:
        response = await client.post(...)
```

## Rule 7: Async plugins

Custom evaluators must implement async `evaluate()`. CPU-bound work should use `run_in_executor`.

```python
class MyEvaluator(BaseEvaluator):
    async def evaluate(self, ctx: EvaluationContext) -> EvalResult:
        # Async I/O
        data = await fetch_data(...)
        # CPU work in thread pool
        result = await asyncio.get_running_loop().run_in_executor(
            ctx.cpu_executor, compute_metric, data
        )
        return EvalResult(...)
```

## Rule 8: Streaming datasets

Dataset loaders yield batches via async generators. No full dataset loaded into memory.

```python
# Correct — streaming
async for batch in loader.stream(uri, config, batch_size=100):
    process(batch)

# Wrong — load all at once
all_data = await loader.load_all(uri)
```

## asyncio.sleep, never time.sleep

The canary observation loop and retry backoff use `asyncio.sleep()`:

```python
# Correct
await asyncio.sleep(60)

# Wrong — blocks the entire event loop
time.sleep(60)
```
