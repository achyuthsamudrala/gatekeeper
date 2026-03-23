# Writing Custom Plugins

GateKeeper uses Python entry points for plugin discovery. You can extend it with custom evaluators, model types, dataset formats, drift methods, inference encodings, and judge modalities.

## Custom Evaluator Example

The simplest way to add a custom evaluator is to create a Python package with an entry point.

### 1. Create the evaluator

```python
# my_custom_eval/evaluators.py

import asyncio
from gatekeeper.registries.evaluator import BaseEvaluator, EvalResult, EvaluationContext

class WordCountEvaluator(BaseEvaluator):
    name = "word_count"
    phase = "offline"
    supported_model_types = ["*"]
    primary_metric = "avg_word_count"

    async def evaluate(self, ctx: EvaluationContext) -> EvalResult:
        samples = []
        async for batch in ctx.dataset_loader.stream(
            ctx.eval_dataset_config.uri,
            ctx.eval_dataset_config,
            batch_size=50,
        ):
            samples.extend(batch)
            break

        outputs = await ctx.runner.run(
            ctx.model_name, ctx.candidate_version, samples[:50]
        )

        # CPU-bound work in thread pool (Rule 3)
        avg_words = await asyncio.get_running_loop().run_in_executor(
            ctx.cpu_executor,
            lambda: sum(len(str(o).split()) for o in outputs) / max(len(outputs), 1),
        )

        return EvalResult(
            gate_name=ctx.gate_config["name"],
            evaluator_name=self.name,
            phase=self.phase,
            metric_name=self.primary_metric,
            metric_value=avg_words,
            passed=None,
            skip_reason=None,
            detail={"num_samples": len(outputs)},
        )
```

### 2. Register via entry point

```toml
# pyproject.toml
[project.entry-points."gatekeeper.evaluators"]
word_count = "my_custom_eval.evaluators:WordCountEvaluator"
```

### 3. Install and use

```bash
pip install -e ./my_custom_eval
```

The evaluator appears in the startup report and can be referenced in `gatekeeper.yaml`:

```yaml
gates:
  - name: word_count_gate
    phase: offline
    evaluator: word_count
    metric: avg_word_count
    threshold: 5.0
    comparator: ">="
```

## Entry Point Groups

| Group | Base Class | Example |
|-------|-----------|---------|
| `gatekeeper.evaluators` | `BaseEvaluator` | Custom quality metrics |
| `gatekeeper.model_types` | `ModelType` | New inference modes |
| `gatekeeper.dataset_formats` | `DatasetLoader` | Custom data formats |
| `gatekeeper.drift_methods` | `DriftMethod` | Alternative drift detection |
| `gatekeeper.inference_encodings` | `InferenceEncoding` | Custom serialization |
| `gatekeeper.judge_modalities` | `JudgeModality` | Image/audio judging |

## Key Rules for Plugin Authors

1. All `evaluate()` methods must be `async`
2. Use `ctx.cpu_executor` with `run_in_executor` for CPU-bound work
3. Use `asyncio.sleep()`, never `time.sleep()`
4. Stream datasets — don't load everything into memory
5. Return `EvalResult` with `passed=None` — the gate engine handles threshold comparison

See `examples/pattern-d-custom-evaluator/` for a complete working example.
