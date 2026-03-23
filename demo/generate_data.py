"""Generate eval and reference JSONL datasets for the blog demo."""

from __future__ import annotations

import json
import random

random.seed(42)

LABELS = ["positive", "negative", "neutral"]
TEMPLATES = {
    "positive": [
        "Great product, love it!",
        "Excellent service and fast delivery",
        "This exceeded my expectations",
        "Highly recommend to everyone",
        "Best purchase I've made this year",
        "Amazing quality for the price",
        "Works perfectly, very satisfied",
        "Outstanding customer support",
    ],
    "negative": [
        "Terrible quality, broke on day one",
        "Worst experience ever, avoid",
        "Completely unusable product",
        "Wasted my money on this",
        "Customer service was unhelpful",
        "Does not work as advertised",
        "Returned immediately, very disappointed",
        "Falling apart after one week",
    ],
    "neutral": [
        "It's okay, nothing special",
        "Average product, does the job",
        "Not bad but not great either",
        "Meets basic expectations",
        "Standard quality, fair price",
        "Decent but could be improved",
        "Works as described, no surprises",
        "Acceptable for the price point",
    ],
}


def generate_sample(label: str, idx: int) -> dict:
    text = random.choice(TEMPLATES[label])
    text_length = len(text.split())
    category_id = random.randint(1, 5)
    return {
        "text": text,
        "text_length": text_length,
        "category_id": category_id,
        "sentiment": label,
        "expected_label": label,
    }


def main():
    # Eval dataset: 60 samples (20 per class)
    eval_samples = []
    for label in LABELS:
        for i in range(20):
            eval_samples.append(generate_sample(label, i))
    random.shuffle(eval_samples)

    with open("demo/data/eval.jsonl", "w") as f:
        for s in eval_samples:
            f.write(json.dumps(s) + "\n")
    print(f"Wrote {len(eval_samples)} samples to demo/data/eval.jsonl")

    # Reference dataset: same distribution (for drift — should show low PSI)
    ref_samples = []
    for label in LABELS:
        for i in range(20):
            ref_samples.append(generate_sample(label, i))
    random.shuffle(ref_samples)

    with open("demo/data/reference.jsonl", "w") as f:
        for s in ref_samples:
            f.write(json.dumps(s) + "\n")
    print(f"Wrote {len(ref_samples)} samples to demo/data/reference.jsonl")


if __name__ == "__main__":
    main()
