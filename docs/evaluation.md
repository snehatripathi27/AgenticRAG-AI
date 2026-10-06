# Evaluation protocol and extensions

## Execution

BenchLab validates config and task names, loads the chosen split, shuffles with the seed, and takes at most `limit` rows. It hashes selected samples and the effective prompt, then records Python/package versions, requested revisions, sources, splits, metrics, and the `generated-answer-v1` protocol.

Only questions, choices, and context are sent to models. Each completed batch commits sample logs and progress atomically. Completed task scores survive later task failures. Scores average sample metrics per task; the UI average is an **unweighted macro average of completed tasks**. Do not compare different task sets, partial runs, or protocols as equivalent. Sample latency is batch generation time divided by batch size.

HF/vLLM apply the tokenizer's chat template when available. HF uses left padding, inference mode, and slices output after the padded input length. No backend enables remote repository code. vLLM batches prompts through `LLM.generate` and `SamplingParams`. The HTTP backend sends `model`, `messages`, `temperature`, `max_tokens`, and `seed`; choose an endpoint supporting those fields. Network errors, 429 and 5xx responses receive three attempts total. Provider error bodies are not persisted.

## Metrics

- `choice_accuracy`: first standalone letter, optionally prefixed by `Answer:` and `(`. Explanations beginning with other words score zero. Numeric dataset labels are mapped to letter positions.
- `exact_match`: lowercase, remove ASCII punctuation, collapse whitespace. Does not strip articles or extract answers from prose.
- `numeric_match`: compares the final number with decimal arithmetic, removing commas. Reasoning must end with the final answer, not another number.
- `token_f1`: multiset token overlap using the same normalization; two empty strings score 1.

Metrics must return a finite score in `[0, 1]`. Invalid plugin scores fail a run. Generations must return exactly one string per prompt. Inference failures remain failures rather than silently becoming incorrect answers.

## Reproducibility

The demo repeats sample selection, predictions, and scores for identical configs. IDs, timestamps, and latency differ. GPU kernels and remote providers can vary even with seeds. Pin model `revision`, per-task `dataset_revisions`, package versions, and plugin versions for defensible experiments. Keep task IDs, limits, seed, prompt, and decoding settings fixed; compare manifest hashes and export full sample logs. Archive `pip freeze` with the experiment.

Unpinned dataset revisions are recorded as `main`, not represented as immutable. The sample hash identifies exact evaluated rows. There is no guarantee of bitwise remote inference reproducibility. Generated-answer scores are not equivalent to official few-shot or likelihood-based leaderboard protocols.

## Custom tasks

Put `.yaml` definitions and JSONL samples in a directory. Fields: `id`, `title`, `category`, `description`, `metric`, `prompt`, `data_file`. `data_file` resolves relative to the YAML and must stay within the task directory. IDs start with a lowercase letter and contain lowercase letters, digits, or underscores. Duplicate task/sample IDs and empty datasets are rejected.

Each JSONL row needs string `question` and `reference`. Optional `id`, `context`, and `choices` add metadata; choices are formatted text such as `A. Red\nB. Blue`.

```bash
benchlab --task-dir examples/tasks tasks
benchlab --task-dir examples/tasks run --backend hf \
  --model Qwen/Qwen2.5-0.5B-Instruct --tasks capitals --limit 2
benchlab --task-dir examples/tasks serve
```

Run config `prompts` maps task IDs to templates. Supported fields are `{question}`, `{context}`, `{choices}`. Expressions, attribute access, references, and format conversions are rejected. Escape literal braces as `{{` and `}}`.

## Custom metrics

A trusted installed distribution can expose `(prediction: str, reference: str) -> float`:

```python
# my_metrics.py

def case_sensitive_match(prediction, reference):
    return float(prediction.strip() == reference.strip())
```

```toml
# Your plugin's pyproject.toml
[project.entry-points."benchlab.metrics"]
case_sensitive_match = "my_metrics:case_sensitive_match"
```

Install the plugin, select `metric: case_sensitive_match` in a task YAML, and restart. Duplicate metric names are rejected. Plugins execute Python with server privileges; install trusted packages. Task files and prompt changes need no core modifications.

## Primary references

- [Transformers generation API](https://huggingface.co/docs/transformers/v4.57.1/en/main_classes/text_generation)
- [vLLM offline inference](https://docs.vllm.ai/en/latest/serving/offline_inference/)
- [ARC dataset schema and splits](https://huggingface.co/datasets/allenai/ai2_arc)
