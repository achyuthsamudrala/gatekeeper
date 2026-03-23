"""Text judge modality."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from gatekeeper.registries.judge_modality import BaseJudgeModality

if TYPE_CHECKING:
    from gatekeeper.registries.dataset_format import BinaryInput, Sample


class TextModality(BaseJudgeModality):
    @property
    def name(self) -> str:
        return "text"

    async def build_judge_message(
        self,
        rubric: str,
        input_sample: Sample,
        candidate_output: dict | BinaryInput,
        reference_output: dict | BinaryInput | None,
        config: dict,
        cpu_executor: ThreadPoolExecutor,
    ) -> list[dict]:
        system_prompt = (
            "You are an expert evaluator. Score the candidate output on a scale of 0.0 to 1.0.\n"
            f"Rubric: {rubric}\n\n"
            'Respond with JSON: {"score": <float>, "reasoning": "<explanation>"}'
        )
        user_content = f"Input: {input_sample.input}\n\nCandidate output: {candidate_output}"
        if reference_output is not None:
            user_content += f"\n\nReference output: {reference_output}"

        return [
            {"role": "user", "content": f"{system_prompt}\n\n{user_content}"},
        ]
