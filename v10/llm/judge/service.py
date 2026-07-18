from __future__ import annotations

from v10.llm.contracts import FinalJudgeReview, StructuredResponse


class FinalJudgeService:
    def parse(self, response: StructuredResponse) -> FinalJudgeReview:
        return FinalJudgeReview(**response.output)
