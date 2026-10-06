import json
import sys
from types import SimpleNamespace

import httpx
import pytest

from benchlab.backends import APIBackend, VLLMBackend
from benchlab.config import ModelConfig
from benchlab.tasks import catalog, load_samples


def test_api_adapter_payload_and_retry(monkeypatch):
    monkeypatch.setenv("MODEL_KEY", "synthetic-key")
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer synthetic-key"
        assert request.url.path == "/v1/chat/completions"
        if len(calls) == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"choices": [{"message": {"content": "A"}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("benchlab.backends.httpx.Client", lambda **_: client)
    monkeypatch.setattr("benchlab.backends.time.sleep", lambda _: None)
    backend = APIBackend(
        ModelConfig(
            backend="api", name="test-model", base_url="http://localhost:9000/v1", api_key_env="MODEL_KEY"
        ),
        7,
    )
    assert backend.generate(["question"]) == ["A"]
    assert len(calls) == 2
    assert calls[0]["seed"] == 7
    assert calls[0]["messages"] == [{"role": "user", "content": "question"}]
    assert calls[0]["temperature"] == 0


@pytest.mark.parametrize(
    "code,body,error",
    [
        (401, {}, "HTTP 401"),
        (200, {"choices": []}, "no text completion"),
        (200, {"choices": [{"message": {"content": None}}]}, "no text completion"),
    ],
)
def test_api_errors_do_not_leak_provider_body(monkeypatch, code, body, error):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(code, json=body)))
    monkeypatch.setattr("benchlab.backends.httpx.Client", lambda **_: client)
    with pytest.raises(RuntimeError, match=error):
        APIBackend(ModelConfig(backend="api"), 42).generate(["test"])


def test_vllm_adapter_batching(monkeypatch):
    captured = {}

    class LLM:
        def __init__(self, **kwargs):
            captured["model"] = kwargs

        def get_tokenizer(self):
            return SimpleNamespace(chat_template=None)

        def generate(self, prompts, params, use_tqdm):
            captured["prompts"] = prompts
            captured["params"] = params
            return [SimpleNamespace(outputs=[SimpleNamespace(text="response")]) for _ in prompts]

    monkeypatch.setitem(sys.modules, "vllm", SimpleNamespace(LLM=LLM, SamplingParams=lambda **kw: kw))
    backend = VLLMBackend(ModelConfig(backend="vllm", name="model"), 7)
    assert backend.generate(["one", "two"]) == ["response", "response"]
    assert captured["prompts"] == ["one", "two"]
    assert captured["params"]["seed"] == 7
    assert captured["model"]["trust_remote_code"] is False


@pytest.mark.parametrize(
    "task_id,row,reference",
    [
        (
            "arc_easy",
            {
                "id": "arc-1",
                "question": "Q?",
                "choices": {"label": ["1", "2"], "text": ["first", "second"]},
                "answerKey": "2",
            },
            "B",
        ),
        ("hellaswag", {"ind": 4, "ctx": "scenario", "endings": ["first", "second"], "label": "1"}, "B"),
        ("boolq", {"question": "Q?", "passage": "passage", "answer": False}, "no"),
        ("gsm8k", {"question": "Q?", "answer": "Compute 2+2. #### 4"}, "4"),
    ],
)
def test_dataset_adapters(monkeypatch, task_id, row, reference):
    class Dataset(list):
        def shuffle(self, seed):
            assert seed == 42
            return self

        def select(self, indices):
            return [self[i] for i in indices]

    def load_dataset(source, subset, split, revision):
        assert revision == "pinned-revision"
        return Dataset([row])

    monkeypatch.setitem(sys.modules, "datasets", SimpleNamespace(load_dataset=load_dataset))
    samples = load_samples(catalog()[task_id], limit=2, seed=42, revision="pinned-revision")
    assert len(samples) == 1 and samples[0].reference == reference


@pytest.mark.parametrize("chat_template", [None, "template"])
def test_hf_batch_padding_and_generated_token_slice(monkeypatch, chat_template):
    from contextlib import nullcontext

    from benchlab.backends import HFBackend

    captured = {}

    class Inputs(dict):
        def to(self, device):
            assert device == "cpu"
            return self

    class Tokenizer:
        pad_token_id = 0

        def __init__(self):
            self.chat_template = chat_template

        def apply_chat_template(self, messages, **kwargs):
            assert kwargs == {"tokenize": False, "add_generation_prompt": True}
            return "chat: " + messages[0]["content"]

        def __call__(self, prompts, **kwargs):
            captured["prompts"] = prompts
            captured["tokenizer"] = kwargs
            return Inputs(input_ids=SimpleNamespace(shape=(2, 5)))

        def batch_decode(self, tokens, skip_special_tokens):
            assert tokens == "new tokens only"
            assert skip_special_tokens
            return ["A", "B"]

    class Output:
        def __getitem__(self, key):
            assert key == (slice(None), slice(5, None))
            return "new tokens only"

    class Model:
        device = "cpu"

        def eval(self):
            captured["eval"] = True

        def generate(self, **kwargs):
            captured["generation"] = kwargs
            return Output()

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(inference_mode=nullcontext))
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a, **kw: Tokenizer()),
            AutoModelForCausalLM=SimpleNamespace(from_pretrained=lambda *a, **kw: Model()),
            set_seed=lambda seed: captured.update(seed=seed),
        ),
    )
    backend = HFBackend(ModelConfig(backend="hf", device="cpu"), 7)
    assert backend.generate(["one", "two"]) == ["A", "B"]
    assert captured["eval"] and captured["seed"] == 7
    assert captured["tokenizer"]["padding"] is True
    assert captured["tokenizer"]["add_special_tokens"] is (not bool(chat_template))
    assert captured["generation"]["do_sample"] is False
    assert "temperature" not in captured["generation"]
    assert captured["prompts"] == (["chat: one", "chat: two"] if chat_template else ["one", "two"])
