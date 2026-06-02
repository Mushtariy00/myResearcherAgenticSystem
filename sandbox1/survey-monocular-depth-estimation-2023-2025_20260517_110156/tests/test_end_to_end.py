"""Runnable entrypoint for the generated research scaffold."""

from model import build_research_plan


def main() -> None:
    plan = build_research_plan()
    print("Topic: Survey monocular depth estimation 2023-2025")
    print(f"Method: {plan.recommended_method}")
    print("Gaps:")
    for gap in plan.research_gaps:
        print(f"- {gap}")


if __name__ == "__main__":
    main()
