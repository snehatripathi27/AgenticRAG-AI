"""Task catalog, local YAML extensions, and Hugging Face dataset adapters."""

import json
import random
import string
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .metrics import metrics


@dataclass
class Sample:
    id: str
    question: str
    reference: str
    choices: str = ""
    context: str = ""


@dataclass
class Task:
    id: str
    title: str
    category: str
    description: str
    metric: str
    prompt: str
    source: str = "Bundled synthetic fixtures"
    subset: str | None = None
    split: str = "test"
    samples: list[Sample] = field(default_factory=list)
    size: int | None = None

    def public(self):
        return {
            key: getattr(self, key)
            for key in ("id", "title", "category", "description", "metric", "source", "split", "size")
        }


CHOICE_PROMPT = "{context}\n{question}\n{choices}\nReply with only the letter of the correct answer.\nAnswer:"
TEXT_PROMPT = "{context}\n{question}\nReply with a short answer.\nAnswer:"


def check_prompt(prompt: str):
    if not prompt or len(prompt) > 50000:
        raise ValueError("Prompt must contain between 1 and 50000 characters")
    for _, name, spec, conversion in string.Formatter().parse(prompt):
        if name is not None and (name not in {"question", "choices", "context"} or spec or conversion):
            raise ValueError("Prompts allow only {question}, {choices}, and {context}; no format specifiers")


class CustomTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    title: str
    category: str = "Custom"
    description: str = "Custom local evaluation"
    metric: str = "exact_match"
    prompt: str = TEXT_PROMPT
    data_file: str


def catalog(task_dir: Path | None = None) -> dict[str, Task]:
    tasks = [
        Task(
            "arc_easy",
            "ARC Easy",
            "Reasoning",
            "Grade-school science questions with multiple-choice answers.",
            "choice_accuracy",
            CHOICE_PROMPT,
            "allenai/ai2_arc",
            "ARC-Easy",
            size=2376,
        ),
        Task(
            "arc_challenge",
            "ARC Challenge",
            "Reasoning",
            "A harder test of scientific knowledge and reasoning.",
            "choice_accuracy",
            CHOICE_PROMPT,
            "allenai/ai2_arc",
            "ARC-Challenge",
            size=1172,
        ),
        Task(
            "hellaswag",
            "HellaSwag",
            "Commonsense",
            "Choose the most plausible ending to an everyday scenario.",
            "choice_accuracy",
            CHOICE_PROMPT,
            "Rowan/hellaswag",
            split="validation",
            size=10042,
        ),
        Task(
            "boolq",
            "BoolQ",
            "Reading",
            "Answer yes-or-no questions grounded in a reference passage.",
            "exact_match",
            "{context}\n{question}\nReply with only yes or no.\nAnswer:",
            "google/boolq",
            split="validation",
            size=3270,
        ),
        Task(
            "gsm8k",
            "GSM8K",
            "Mathematics",
            "Multi-step grade-school math problems with numeric answers.",
            "numeric_match",
            "{question}\nSolve step by step. End with the final numeric answer.",
            "openai/gsm8k",
            "main",
            size=1319,
        ),
    ]
    reasoning = [
        ("All roses are plants. A rose is a…", ["Plant", "Stone", "Animal", "Cloud"], "A"),
        ("Which comes next: 2, 4, 6, …?", ["7", "8", "9", "12"], "B"),
        ("If today is Monday, tomorrow is…", ["Friday", "Sunday", "Tuesday", "Saturday"], "C"),
        ("Which object is used to measure time?", ["Ruler", "Scale", "Cup", "Clock"], "D"),
        ("Which shape has three sides?", ["Circle", "Triangle", "Square", "Hexagon"], "B"),
        ("A is taller than B. B is taller than C. Who is tallest?", ["A", "B", "C", "Equal"], "A"),
        ("Which number is odd?", ["2", "4", "7", "8"], "C"),
        ("Water freezes when it becomes…", ["Steam", "Air", "Sand", "Ice"], "D"),
    ]
    rs = [
        Sample(str(i), q, answer, "\n".join(f"{chr(65 + j)}. {c}" for j, c in enumerate(choices)))
        for i, (q, choices, answer) in enumerate(reasoning)
    ]
    ms = [
        Sample(str(i), f"What is {a} {op} {b}?", str(a + b if op == "+" else a * b))
        for i, (a, op, b) in enumerate(
            [
                (2, "+", 3),
                (7, "*", 6),
                (12, "+", 18),
                (9, "*", 9),
                (25, "+", 17),
                (11, "*", 4),
                (100, "+", 23),
                (8, "*", 7),
                (15, "+", 16),
                (3, "*", 12),
                (23, "+", 19),
                (6, "*", 13),
            ]
        )
    ]
    ks = [
        Sample(str(i), q, a)
        for i, (q, a) in enumerate(
            [
                ("What is the capital of France?", "Paris"),
                ("What planet do humans live on?", "Earth"),
                ("How many days are in a week?", "7"),
                ("What is H2O commonly called?", "water"),
                ("What is the largest ocean?", "Pacific"),
                ("What star is closest to Earth?", "Sun"),
                ("What language is primarily spoken in Brazil?", "Portuguese"),
                ("How many sides does a hexagon have?", "6"),
            ]
        )
    ]
    for id_, title, category, metric, prompt, samples in [
        ("demo_reasoning", "Reasoning sampler", "Demo", "choice_accuracy", CHOICE_PROMPT, rs),
        ("demo_math", "Arithmetic sampler", "Demo", "numeric_match", TEXT_PROMPT, ms),
        ("demo_knowledge", "Knowledge sampler", "Demo", "exact_match", TEXT_PROMPT, ks),
    ]:
        tasks.append(
            Task(
                id_,
                title,
                category,
                "Small synthetic task for testing the evaluation workflow. Not an official benchmark.",
                metric,
                prompt,
                samples=samples,
                size=len(samples),
            )
        )
    registry = {t.id: t for t in tasks}
    if task_dir:
        for path in sorted(task_dir.glob("*.yaml")):
            custom = CustomTask.model_validate(yaml.safe_load(path.read_text()))
            if custom.id in registry:
                raise ValueError(f"Duplicate task: {custom.id}")
            data = (path.parent / custom.data_file).resolve()
            if not data.is_relative_to(task_dir.resolve()):
                raise ValueError("Custom data_file must stay inside task directory")
            samples = []
            for i, line in enumerate(data.read_text().splitlines()):
                if line.strip():
                    row = json.loads(line)
                    if not isinstance(row.get("question"), str) or not isinstance(row.get("reference"), str):
                        raise ValueError(f"{data.name} row {i + 1}: question and reference must be strings")
                    samples.append(
                        Sample(
                            str(row.get("id", i)),
                            row["question"],
                            row["reference"],
                            str(row.get("choices", "")),
                            str(row.get("context", "")),
                        )
                    )
            if not samples or len({s.id for s in samples}) != len(samples):
                raise ValueError("Custom tasks need samples with unique IDs")
            registry[custom.id] = Task(
                custom.id,
                custom.title,
                custom.category,
                custom.description,
                custom.metric,
                custom.prompt,
                source=f"Local: {data.name}",
                samples=samples,
                size=len(samples),
            )
    available_metrics = metrics()
    for task in registry.values():
        check_prompt(task.prompt)
        if task.metric not in available_metrics:
            raise ValueError(f"Unknown metric: {task.metric}")
    return registry


def validate_tasks(config, registry):
    unknown = set(config.tasks) - registry.keys()
    if unknown:
        raise ValueError(f"Unknown tasks: {', '.join(sorted(unknown))}")
    for prompt in config.prompts.values():
        check_prompt(prompt)
    if config.model.backend == "demo" and any(registry[t].category != "Demo" for t in config.tasks):
        raise ValueError(
            "The demo backend supports only the bundled demo tasks; choose hf, vllm, or api for benchmarks"
        )


def load_samples(task: Task, limit: int, seed: int, revision: str | None = None) -> list[Sample]:
    if task.samples:
        samples = list(task.samples)
        random.Random(seed).shuffle(samples)
        return samples[:limit]
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("Install benchmark support: pip install 'benchlab-eval[benchmarks]'") from exc
    dataset = load_dataset(task.source, task.subset, split=task.split, revision=revision or "main")
    rows = dataset.shuffle(seed=seed).select(range(min(limit, len(dataset))))
    samples = []
    for i, row in enumerate(rows):
        if task.id.startswith("arc_"):
            labels = row["choices"]["label"]
            reference = chr(65 + labels.index(row["answerKey"]))
            sample = Sample(
                str(row["id"]),
                row["question"],
                reference,
                "\n".join(f"{chr(65 + j)}. {c}" for j, c in enumerate(row["choices"]["text"])),
            )
        elif task.id == "hellaswag":
            sample = Sample(
                str(row.get("ind", i)),
                row["ctx"],
                chr(65 + int(row["label"])),
                "\n".join(f"{chr(65 + j)}. {c}" for j, c in enumerate(row["endings"])),
            )
        elif task.id == "boolq":
            sample = Sample(str(i), row["question"], "yes" if row["answer"] else "no", context=row["passage"])
        else:
            sample = Sample(str(i), row["question"], row["answer"].split("####")[-1].strip())
        samples.append(sample)
    return samples
