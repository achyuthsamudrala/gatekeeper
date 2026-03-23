# Extending GateKeeper

GateKeeper is built around 6 plugin registries. Each uses Python entry points for discovery — install a package with the right entry point and GateKeeper picks it up at startup.

## Plugin Architecture

```
pyproject.toml entry point → load_all_plugins() at startup → Registry.register()
```

All plugins are discovered via `importlib.metadata.entry_points()`. No code changes to GateKeeper are needed.

## Entry Point Groups

| Group | Base Class | Built-in |
|-------|-----------|----------|
| `gatekeeper.evaluators` | `BaseEvaluator` | accuracy, drift, llm_judge, champion_challenger, latency |
| `gatekeeper.model_types` | `ModelTypeDefinition` | llm, pytorch |
| `gatekeeper.dataset_formats` | `BaseDatasetLoader` | jsonl, parquet, csv |
| `gatekeeper.drift_methods` | `BaseDriftMethod` | psi, ks |
| `gatekeeper.inference_encodings` | `BaseInferenceEncoding` | json |
| `gatekeeper.judge_modalities` | `BaseJudgeModality` | text |

---

## Data Types Reference

These dataclasses appear throughout the plugin interfaces.

### Sample

```python
from gatekeeper.registries.dataset_format import Sample, BinaryInput

@dataclass
class Sample:
    input: dict | BinaryInput    # Model input (text as dict, or binary reference)
    ground_truth: dict | None    # Expected output for comparison
    metadata: dict               # Arbitrary metadata (default: {})

@dataclass
class BinaryInput:
    format: str       # e.g. "png", "wav", "pcd"
    uri: str          # Path or URI to the binary file
    metadata: dict    # Arbitrary metadata (default: {})
```

### DatasetConfig

```python
from gatekeeper.registries.evaluator import DatasetConfig

@dataclass
class DatasetConfig:
    uri: str                              # Path or URI to the dataset
    format: str | None = None             # Registered format name (inferred from extension if None)
    label_column: str | None = None       # Column name for ground truth
    task_type: str | None = None          # classification, regression, summarisation, qa
    feature_columns: list[str] | None = None       # For drift detection
    categorical_columns: list[str] | None = None   # For drift detection
```

### EvalResult

```python
from gatekeeper.registries.evaluator import EvalResult

@dataclass
class EvalResult:
    gate_name: str              # From ctx.gate_config["name"]
    evaluator_name: str         # Your evaluator's name
    phase: str                  # "offline" or "online"
    metric_name: str            # Your primary_metric
    metric_value: float | None  # The computed metric (None if skipped/error)
    passed: bool | None         # Always None — gate engine sets this via threshold comparison
    skip_reason: str | None     # Why the evaluator was skipped (e.g. missing config)
    error: bool = False         # True if evaluator caught an exception
    error_message: str | None = None
    detail: dict = {}           # Arbitrary JSON stored in DB, shown in UI
```

**Important:** Always set `passed=None`. The gate engine compares `metric_value` against the threshold from `gatekeeper.yaml` and sets `passed` itself. If your evaluator can't run (missing config), set `metric_value=None` and `skip_reason` to explain why.

### EvaluationContext

```python
from gatekeeper.registries.evaluator import EvaluationContext

@dataclass
class EvaluationContext:
    run_id: str                          # Pipeline run ID
    model_name: str                      # Model being evaluated
    candidate_version: str               # Version being evaluated
    model_type: ModelTypeDefinition      # Resolved model type
    runner: OfflineInferenceRunner | None # For offline phase — runs model inference
    serving_adapter: ServingAdapter | None # For online phase — live endpoint access
    registry_adapter: RegistryAdapter    # Model artifact registry
    dataset_loader: BaseDatasetLoader    # Resolved dataset loader
    eval_dataset_config: DatasetConfig   # Eval dataset configuration
    reference_dataset_config: DatasetConfig | None  # Reference data (for drift)
    llm_judge_config: LLMJudgeConfig | None  # LLM judge settings
    llm_judge_client: AsyncAnthropic | None  # Pre-configured Anthropic client
    gate_config: dict                    # Raw gate config from gatekeeper.yaml
    cpu_executor: ThreadPoolExecutor | None  # For run_in_executor()
```

### PredictionRequest / PredictionResponse

```python
from gatekeeper.adapters.base_types import PredictionRequest, PredictionResponse, ModelVersion

@dataclass
class PredictionRequest:
    model_role: str = "champion"         # "champion" or "challenger"
    timeout_seconds: float = 30.0
    inputs: list[dict] | None = None     # JSON inputs
    binary_inputs: list[BinaryInput] | None = None

@dataclass
class PredictionResponse:
    model_role: str           # Echoed from request
    latency_ms: float         # Time for the prediction
    status_code: int          # HTTP status (200 = success)
    error: str | None = None  # Error message if failed
    outputs: list[dict] | None = None

@dataclass
class ModelVersion:
    name: str                 # Model name
    version: str              # Version identifier
    model_type: str           # Registered model type name
    artifact_uri: str | None = None  # URI for downloading artifact
    stage: str | None = None  # e.g. "champion", "challenger", "archived"
    metadata: dict = {}
```

### DriftResult

```python
from gatekeeper.registries.drift_method import DriftResult

@dataclass
class DriftResult:
    primary_metric_name: str     # e.g. "max_psi_score", "max_ks_statistic"
    primary_metric_value: float  # The main drift score
    detail: dict = {}            # Per-feature breakdown, stored in DB
```

### EncodedRequest

```python
from gatekeeper.registries.inference_encoding import EncodedRequest

@dataclass
class EncodedRequest:
    method: str = "POST"              # HTTP method
    headers: dict | None = None       # Extra HTTP headers
    content: bytes | None = None      # Raw body (for binary encodings)
    json_body: dict | None = None     # JSON body (for JSON encoding)
```

### LLMJudgeConfig

```python
from gatekeeper.registries.evaluator import LLMJudgeConfig

@dataclass
class LLMJudgeConfig:
    provider: str = "anthropic"    # "anthropic" or "openai"
    model: str = "claude-sonnet-4-20250514"
    api_key: str = ""
```

---

## Plugin Type 1: Custom Evaluator

The most common extension point. Evaluators compute metrics from model outputs.

### Base Class

```python
from gatekeeper.registries.evaluator import BaseEvaluator, EvaluationContext, EvalResult

class BaseEvaluator(ABC):
    @property
    def name(self) -> str: ...              # Unique name, referenced in gatekeeper.yaml
    @property
    def phase(self) -> str: ...             # "offline" or "online"
    @property
    def supported_model_types(self) -> list[str]: ...  # ["*"] for all
    @property
    def primary_metric(self) -> str: ...    # Metric name stored in DB

    async def evaluate(self, context: EvaluationContext) -> EvalResult:
        """Always async. Never raises — catch exceptions and return
        EvalResult with error=True. CPU-bound work must use run_in_executor()."""
```

### Example: WordCountEvaluator

```python
# my_package/evaluators.py
import asyncio
from gatekeeper.registries.evaluator import BaseEvaluator, EvalResult, EvaluationContext

class WordCountEvaluator(BaseEvaluator):
    name = "word_count"
    phase = "offline"
    supported_model_types = ["*"]
    primary_metric = "avg_word_count"

    async def evaluate(self, ctx: EvaluationContext) -> EvalResult:
        try:
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

            # CPU-bound work in thread pool
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
                passed=None,       # Gate engine handles threshold comparison
                skip_reason=None,
                detail={"num_samples": len(outputs)},
            )
        except Exception as e:
            return EvalResult(
                gate_name=ctx.gate_config["name"],
                evaluator_name=self.name,
                phase=self.phase,
                metric_name=self.primary_metric,
                metric_value=None,
                passed=None,
                skip_reason=str(e),
            )
```

### Registration

```toml
# pyproject.toml
[project.entry-points."gatekeeper.evaluators"]
word_count = "my_package.evaluators:WordCountEvaluator"
```

### Usage in gatekeeper.yaml

```yaml
gates:
  - name: word_count_gate
    phase: offline
    evaluator: word_count
    metric: avg_word_count
    threshold: 5.0
    comparator: ">="
```

---

## Plugin Type 2: Custom Dataset Format

Dataset loaders stream data in batches. They must never load the full dataset into memory.

### Base Class

```python
from gatekeeper.registries.dataset_format import BaseDatasetLoader, Sample
from gatekeeper.registries.evaluator import DatasetConfig

class BaseDatasetLoader(ABC):
    @property
    def format_name(self) -> str: ...       # e.g. "jsonl", "parquet"

    @property
    def default_batch_size(self) -> int:    # Default: 256
        return 256

    async def stream(
        self, uri: str, config: DatasetConfig, batch_size: int
    ) -> AsyncIterator[list[Sample]]:
        """Yield batches of samples. Never load full dataset into memory."""
```

### Example: TSV Loader

```python
import aiofiles
from gatekeeper.registries.dataset_format import BaseDatasetLoader, Sample
from gatekeeper.registries.evaluator import DatasetConfig

class TSVLoader(BaseDatasetLoader):
    @property
    def format_name(self) -> str:
        return "tsv"

    async def stream(self, uri, config, batch_size):
        label_col = config.label_column or "expected_output"
        headers = None
        batch = []
        async with aiofiles.open(uri, "r") as f:
            async for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if headers is None:
                    headers = parts
                    continue
                row = dict(zip(headers, parts))
                ground_truth = row.pop(label_col, None)
                batch.append(Sample(input=row, ground_truth=ground_truth))
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
        if batch:
            yield batch
```

### Registration

```toml
[project.entry-points."gatekeeper.dataset_formats"]
tsv = "my_package.loaders:TSVLoader"
```

---

## Plugin Type 3: Custom Drift Method

Drift methods compare a reference dataset against an evaluation dataset to detect data distribution shifts.

### Base Class

```python
from gatekeeper.registries.drift_method import BaseDriftMethod, DriftResult
from gatekeeper.registries.dataset_format import BaseDatasetLoader
from gatekeeper.registries.evaluator import DatasetConfig
from concurrent.futures import ThreadPoolExecutor

class BaseDriftMethod(ABC):
    @property
    def name(self) -> str: ...           # e.g. "psi", "ks"
    @property
    def primary_metric(self) -> str: ... # e.g. "max_psi_score"

    async def compute(
        self,
        reference_config: DatasetConfig,
        current_config: DatasetConfig,
        reference_loader: BaseDatasetLoader,
        current_loader: BaseDatasetLoader,
        config: dict,              # Gate config from gatekeeper.yaml
        cpu_executor: ThreadPoolExecutor,
    ) -> DriftResult:
        """Async. Statistical computation must use cpu_executor."""
```

### Example: Jensen-Shannon Divergence

```python
import asyncio
from gatekeeper.registries.drift_method import BaseDriftMethod, DriftResult

class JSDriftMethod(BaseDriftMethod):
    @property
    def name(self):
        return "js"

    @property
    def primary_metric(self):
        return "max_js_divergence"

    async def compute(self, reference_config, current_config,
                      reference_loader, current_loader, config, cpu_executor):
        # Stream both datasets
        ref_samples, cur_samples = [], []
        async for batch in reference_loader.stream(reference_config.uri, reference_config, 256):
            ref_samples.extend(batch)
        async for batch in current_loader.stream(current_config.uri, current_config, 256):
            cur_samples.extend(batch)

        feature_columns = config.get("feature_columns", [])

        # CPU-bound stats in thread pool
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            cpu_executor, _compute_js_sync, ref_samples, cur_samples, feature_columns
        )
```

### Registration

```toml
[project.entry-points."gatekeeper.drift_methods"]
js = "my_package.drift:JSDriftMethod"
```

### Usage

```yaml
gates:
  - name: drift_gate
    evaluator: drift
    drift_method: js          # Your custom method
    threshold: 0.15
    comparator: "<"
```

---

## Plugin Type 4: Custom Model Type

Model types define how inference works for a class of models.

### Definition

```python
from gatekeeper.registries.model_type import ModelTypeDefinition

@dataclass
class ModelTypeDefinition:
    name: str                    # e.g. "llm", "pytorch", "onnx"
    inference_mode: str          # "local_artifact" or "sequential_http"
    supported_input_formats: list[str] = []    # e.g. ["jsonl", "csv"]
    supported_output_formats: list[str] = []
    compatible_evaluators: list[str] = []      # Empty = all evaluators
    artifact_loader: type | None = None        # For local_artifact mode
    description: str = ""
```

**`inference_mode` values:**
- `"sequential_http"` — Model runs as a remote HTTP service. The offline runner sends requests to the serving URL.
- `"local_artifact"` — Model artifact is downloaded and loaded locally. Requires an `artifact_loader` class.

### Example: ONNX Model Type

```python
from gatekeeper.registries.model_type import ModelTypeDefinition

class ONNXModelType:
    definition = ModelTypeDefinition(
        name="onnx",
        inference_mode="local_artifact",
        supported_input_formats=["jsonl", "csv"],
        artifact_loader=ONNXArtifactLoader,
        description="ONNX Runtime models",
    )
```

### Registration

Model types register a `ModelTypeDefinition` instance, not a class:

```toml
[project.entry-points."gatekeeper.model_types"]
onnx = "my_package.model_types:ONNXModelType"
```

---

## Plugin Type 5: Custom Inference Encoding

Inference encodings control how `PredictionRequest` is serialized for HTTP and how responses are deserialized. Used by the `custom_http` serving adapter.

### Base Class

```python
from gatekeeper.registries.inference_encoding import BaseInferenceEncoding, EncodedRequest
from gatekeeper.adapters.base_types import PredictionRequest, PredictionResponse
import httpx

class BaseInferenceEncoding(ABC):
    @property
    def name(self) -> str: ...

    async def encode_request(
        self, request: PredictionRequest, config: dict
    ) -> EncodedRequest:
        """Serialize PredictionRequest for HTTP transmission."""

    async def decode_response(
        self, response: httpx.Response, config: dict
    ) -> PredictionResponse:
        """Deserialize HTTP response into PredictionResponse."""
```

### Example: MessagePack Encoding

```python
from gatekeeper.registries.inference_encoding import BaseInferenceEncoding, EncodedRequest
from gatekeeper.adapters.base_types import PredictionResponse
import msgpack

class MsgpackEncoding(BaseInferenceEncoding):
    @property
    def name(self):
        return "msgpack"

    async def encode_request(self, request, config):
        return EncodedRequest(
            method="POST",
            headers={"Content-Type": "application/msgpack"},
            content=msgpack.packb({"inputs": request.inputs}),
        )

    async def decode_response(self, response, config):
        data = msgpack.unpackb(response.content)
        return PredictionResponse(
            model_role="unknown", latency_ms=0.0,
            status_code=response.status_code,
            outputs=data.get("outputs", []),
        )
```

### Registration

```toml
[project.entry-points."gatekeeper.inference_encodings"]
msgpack = "my_package.encodings:MsgpackEncoding"
```

### Usage

```yaml
# server.yaml
serving:
  type: custom_http
  request_encoding: msgpack     # Your custom encoding
```

---

## Plugin Type 6: Custom Judge Modality

Judge modalities build the message list sent to the LLM judge. The built-in `text` modality formats text inputs. Custom modalities can handle images, audio, or structured data.

### Base Class

```python
from gatekeeper.registries.judge_modality import BaseJudgeModality
from gatekeeper.registries.dataset_format import Sample, BinaryInput
from concurrent.futures import ThreadPoolExecutor

class BaseJudgeModality(ABC):
    @property
    def name(self) -> str: ...

    async def build_judge_message(
        self,
        rubric: str,
        input_sample: Sample,
        candidate_output: dict | BinaryInput,
        reference_output: dict | BinaryInput | None,
        config: dict,                   # render_config from gatekeeper.yaml
        cpu_executor: ThreadPoolExecutor,
    ) -> list[dict]:
        """Return a messages list in OpenAI/Anthropic format.
        CPU-bound rendering (e.g. image processing) must use cpu_executor."""
```

The returned `list[dict]` must be valid Anthropic API messages format:

```python
[{"role": "user", "content": "..."}]
```

### Example: Image Modality

```python
import asyncio, base64
from gatekeeper.registries.judge_modality import BaseJudgeModality

class ImageModality(BaseJudgeModality):
    @property
    def name(self):
        return "image"

    async def build_judge_message(self, rubric, input_sample, candidate_output,
                                   reference_output, config, cpu_executor):
        # CPU-bound image loading in thread pool
        loop = asyncio.get_running_loop()
        img_b64 = await loop.run_in_executor(
            cpu_executor, _load_and_encode_image, input_sample.input.uri
        )

        return [
            {"role": "user", "content": [
                {"type": "text", "text": f"Rubric: {rubric}\nScore 0-1."},
                {"type": "image", "source": {"type": "base64", "data": img_b64}},
                {"type": "text", "text": f"Candidate output: {candidate_output}"},
            ]},
        ]
```

### Registration

```toml
[project.entry-points."gatekeeper.judge_modalities"]
image = "my_package.modalities:ImageModality"
```

### Usage

```yaml
gates:
  - name: visual_quality
    evaluator: llm_judge
    judge_modality: image         # Your custom modality
    render_config:
      max_width: 512
```

---

## Adapter Interfaces

Serving and registry adapters are **not pluggable via entry points** — they are selected by `type` in `server.yaml` and resolved by a factory. However, the base classes define clear contracts for anyone forking or contributing.

### ServingAdapter

```python
from gatekeeper.adapters.serving.base import ServingAdapter
from gatekeeper.adapters.base_types import PredictionRequest, PredictionResponse

class ServingAdapter(ABC):
    async def startup(self) -> None: ...
    async def shutdown(self) -> None: ...
    async def health_check(self) -> tuple[bool, str]: ...

    async def predict(self, request: PredictionRequest) -> PredictionResponse:
        """Single prediction. Uses shared httpx.AsyncClient."""

    async def predict_batch(self, requests: list[PredictionRequest]) -> list[PredictionResponse]:
        """Concurrent predictions with Semaphore(10). Default implementation provided."""

    async def wait_for_ready(self, role: str, timeout_seconds: int, interval_seconds: int = 10) -> None:
        """Poll health endpoint. Uses asyncio.sleep(), never time.sleep()."""

    async def set_traffic_split(self, weights: dict[str, float]) -> None: ...
    async def get_traffic_split(self) -> dict[str, float]: ...
```

**Built-in:** `openai_compatible`, `torchserve`, `custom_http`, `proxy`, `none`

### RegistryAdapter

```python
from gatekeeper.adapters.registry.base import RegistryAdapter
from gatekeeper.adapters.base_types import ModelVersion

class RegistryAdapter(ABC):
    async def startup(self) -> None: ...
    async def shutdown(self) -> None: ...
    async def health_check(self) -> tuple[bool, str]: ...

    async def get_model_version(self, name: str, version: str) -> ModelVersion: ...
    async def get_champion_version(self, name: str) -> ModelVersion | None: ...
    async def set_champion(self, name: str, version: str) -> None: ...
    async def download_artifact(self, artifact_uri: str, local_path: str) -> str:
        """Returns local filesystem path after async download."""
```

**Built-in:** `mlflow`, `sagemaker`, `s3`, `local`, `none`

---

## Rules for Plugin Authors

1. **All methods must be async** — `evaluate()`, `stream()`, `compute()`, `build_judge_message()`
2. **CPU-bound work in thread pool** — Use `await loop.run_in_executor(ctx.cpu_executor, func, ...)`
3. **Never use `time.sleep()`** — Use `await asyncio.sleep()` instead
4. **Stream datasets** — Never call `.read()` to load an entire file; iterate line-by-line
5. **Return `passed=None`** — The gate engine handles threshold comparison, not your evaluator
6. **Never raise from `evaluate()`** — Catch all exceptions, return `EvalResult(error=True)`
7. **Use `gate_config` for custom settings** — Access via `ctx.gate_config.get("my_setting")`

## Testing Plugins

```python
# test_my_evaluator.py
import asyncio
from unittest.mock import AsyncMock
from my_package.evaluators import WordCountEvaluator
from gatekeeper.registries.evaluator import EvaluationContext, DatasetConfig
from gatekeeper.registries.dataset_format import Sample

async def test_word_count():
    evaluator = WordCountEvaluator()

    # Mock the context
    ctx = EvaluationContext(
        run_id="test-run",
        model_name="test-model",
        candidate_version="v1",
        model_type=...,
        runner=mock_runner,         # AsyncMock returning [{"text": "hello world"}]
        dataset_loader=mock_loader, # Yields [Sample(input={"text": "hi"}, ground_truth="pos")]
        eval_dataset_config=DatasetConfig(uri="test.jsonl"),
        gate_config={"name": "test_gate"},
        cpu_executor=ThreadPoolExecutor(max_workers=2),
        ...
    )

    result = await evaluator.evaluate(ctx)
    assert result.metric_value is not None
    assert result.passed is None  # Gate engine sets this
    assert not result.error
```

See `examples/pattern-d-custom-evaluator/` for a complete installable example.
