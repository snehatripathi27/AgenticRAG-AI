"""Lazy optional inference adapters. Inputs consist only of prompts."""

import hashlib
import os
import re
import time

import httpx


class DemoBackend:
    """Deterministic toy baseline, intentionally not a language model."""

    def __init__(self, config, seed):
        self.seed = seed

    def generate(self, prompts):
        outputs = []
        for prompt in prompts:
            arithmetic = re.search(r"What is (\d+) ([+*]) (\d+)\?", prompt)
            if arithmetic:
                a, op, b = arithmetic.groups()
                outputs.append(str(int(a) + int(b) if op == "+" else int(a) * int(b)))
            elif "A. " in prompt:
                index = int(hashlib.sha256(f"{self.seed}:{prompt}".encode()).hexdigest(), 16) % 4
                outputs.append("ABCD"[index])
            else:
                known = {
                    "capital of France": "Paris",
                    "planet do humans": "Earth",
                    "days are in a week": "7",
                    "H2O": "water",
                }
                outputs.append(next((v for k, v in known.items() if k in prompt), "Unknown"))
        return outputs


class APIBackend:
    def __init__(self, config, seed):
        self.config, self.seed = config, seed
        self.key = os.environ.get(config.api_key_env)
        if not self.key:
            raise ValueError(
                f"Set the {config.api_key_env} environment variable before using the API backend"
            )

    def generate(self, prompts):
        outputs = []
        with httpx.Client(timeout=self.config.timeout) as client:
            for prompt in prompts:
                for attempt in range(3):
                    try:
                        response = client.post(
                            f"{self.config.base_url}/chat/completions",
                            headers={"Authorization": f"Bearer {self.key}"},
                            json={
                                "model": self.config.name,
                                "messages": [{"role": "user", "content": prompt}],
                                "temperature": self.config.temperature,
                                "max_tokens": self.config.max_tokens,
                                "seed": self.seed,
                            },
                        )
                    except httpx.RequestError:
                        if attempt == 2:
                            raise RuntimeError("API connection failed or timed out") from None
                        time.sleep(2**attempt)
                        continue
                    if (response.status_code == 429 or response.status_code >= 500) and attempt < 2:
                        time.sleep(2**attempt)
                        continue
                    if response.is_error:
                        raise RuntimeError(
                            f"API request failed (HTTP {response.status_code}); check provider settings"
                        )
                    try:
                        content = response.json()["choices"][0]["message"]["content"]
                        if not isinstance(content, str):
                            raise TypeError()
                    except (ValueError, KeyError, IndexError, TypeError):
                        raise RuntimeError("API returned no text completion") from None
                    outputs.append(content)
                    break
        return outputs


class HFBackend:
    def __init__(self, config, seed):
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed
        except ImportError as exc:
            raise RuntimeError("Install Hugging Face support: pip install 'benchlab-eval[hf]'") from exc
        set_seed(seed)
        self.torch, self.config = torch, config
        self.tokenizer = AutoTokenizer.from_pretrained(
            config.name, revision=config.revision, padding_side="left"
        )
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(
            config.name, revision=config.revision, device_map=config.device
        )
        self.model.eval()

    def generate(self, prompts):
        if self.tokenizer.chat_template:
            prompts = [
                self.tokenizer.apply_chat_template(
                    [{"role": "user", "content": p}], tokenize=False, add_generation_prompt=True
                )
                for p in prompts
            ]
        inputs = self.tokenizer(
            prompts,
            return_tensors="pt",
            padding=True,
            add_special_tokens=not bool(self.tokenizer.chat_template),
        ).to(self.model.device)
        options = {
            "max_new_tokens": self.config.max_tokens,
            "do_sample": self.config.temperature > 0,
            "pad_token_id": self.tokenizer.pad_token_id,
        }
        if self.config.temperature:
            options["temperature"] = self.config.temperature
        with self.torch.inference_mode():
            result = self.model.generate(**inputs, **options)
        return self.tokenizer.batch_decode(
            result[:, inputs["input_ids"].shape[1] :], skip_special_tokens=True
        )


class VLLMBackend:
    def __init__(self, config, seed):
        try:
            from vllm import LLM, SamplingParams
        except ImportError as exc:
            raise RuntimeError("Install vLLM support: pip install 'benchlab-eval[vllm]'") from exc
        self.model = LLM(model=config.name, revision=config.revision, seed=seed, trust_remote_code=False)
        self.params = SamplingParams(temperature=config.temperature, max_tokens=config.max_tokens, seed=seed)
        self.tokenizer = self.model.get_tokenizer()

    def generate(self, prompts):
        if self.tokenizer.chat_template:
            prompts = [
                self.tokenizer.apply_chat_template(
                    [{"role": "user", "content": p}], tokenize=False, add_generation_prompt=True
                )
                for p in prompts
            ]
        return [r.outputs[0].text for r in self.model.generate(prompts, self.params, use_tqdm=False)]


def create_backend(config, seed):
    return {"demo": DemoBackend, "api": APIBackend, "hf": HFBackend, "vllm": VLLMBackend}[config.backend](
        config, seed
    )
