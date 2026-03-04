from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from carcase_ai_moderation.application.policy import DEFAULT_POLICY
from carcase_ai_moderation.domain.moderation import Action, Field


class BatchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CategorySpec:
    expected_categories: tuple[str, ...]
    note: str


class TextGenerator(Protocol):
    def __call__(self, *, rng: random.Random, field: Field) -> str: ...


ALLOW_SPEC = CategorySpec(expected_categories=(), note="benign")
SPAM_SPEC = CategorySpec(expected_categories=("spam_ads_scam",), note="spam/ads/scam")
PROFANITY_SPEC = CategorySpec(
    expected_categories=("profanity_insult_harassment",), note="profanity/harassment"
)
PII_SPEC = CategorySpec(expected_categories=("pii_doxxing",), note="PII/doxxing")
VIOLENCE_SPEC = CategorySpec(expected_categories=("violence_threats",), note="violence/threats")
SEXUAL_SPEC = CategorySpec(expected_categories=("sexual",), note="adult sexual content (mild)")


def _parse_int(value: str, *, name: str, min_value: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise BatchError(f"{name} must be an integer") from exc
    if parsed < min_value:
        raise BatchError(f"{name} must be >= {min_value}")
    return parsed


def _choose_field(rng: random.Random) -> Field:
    return rng.choice((Field.SQUAD_NAME, Field.SQUAD_DESCRIPTION))


def _choose_action(rng: random.Random) -> Action:
    return rng.choice((Action.CREATE, Action.UPDATE))


def _generate_allow_text(*, rng: random.Random, field: Field) -> str:
    if field == Field.SQUAD_NAME:
        adjectives = ("Night", "Golden", "Brave", "Silent", "Shadow", "Iron", "Blue")
        nouns = ("Riders", "Wolves", "Dragons", "Guard", "Crew", "Legion", "Squad")
        return f"{rng.choice(adjectives)} {rng.choice(nouns)}"

    templates = (
        "Играем каждый вечер, помогаем новичкам, общаемся без токсичности.",
        "Собираемся на события, фармим очки, держим дисциплину и дружелюбную атмосферу.",
        "Активный клан, вместе делаем задания и поддерживаем друг друга.",
    )
    return rng.choice(templates)


def _generate_spam_text(*, rng: random.Random, field: Field) -> str:
    if field == Field.SQUAD_NAME:
        names = (
            "Free Coins",
            "Cheap Gems",
            "Promo Shop",
            "Boost Service",
            "Купи монеты",
            "Бесплатные кристаллы",
        )
        return rng.choice(names)

    templates = (
        "Скидки на донат: example.com, успей забрать бонус.",
        "Промокоды и монеты дешево — пиши в личку.",
        "Реклама: подписка со скидкой, ссылка: example.com/deal",
    )
    return rng.choice(templates)


def _generate_profanity_text(*, rng: random.Random, field: Field) -> str:
    insults = (
        "идиоты",
        "тупые",
        "клоуны",
        "noobs",
        "losers",
    )
    if field == Field.SQUAD_NAME:
        templates = (
            "Noob Haters",
            "Losers Club",
            "Тупые но вместе",
        )
        return rng.choice(templates)

    templates = (
        f"Только не {rng.choice(insults)}. Собираем сильных игроков.",
        "Не пиши гадости в чат — бан без предупреждения.",
        "Если ты токсичный игрок, тебе сюда не надо.",
    )
    return rng.choice(templates)


def _generate_pii_text(*, rng: random.Random, field: Field) -> str:
    emails = ("player@example.com", "admin@example.com", "support@example.com")
    phones = ("+1-555-0100", "+7-999-123-45-67", "+44 20 7946 0958")
    if field == Field.SQUAD_NAME:
        return "Связь: " + rng.choice(phones)

    templates = (
        f"Связь по почте: {rng.choice(emails)}",
        f"Наш телефон для связи: {rng.choice(phones)}",
        f"Пиши на {rng.choice(emails)} для вступления.",
    )
    return rng.choice(templates)


def _generate_violence_text(*, rng: random.Random, field: Field) -> str:
    if field == Field.SQUAD_NAME:
        names = (
            "Kill Team",
            "Death Squad",
            "Убью всех",
        )
        return rng.choice(names)

    templates = (
        "Я тебя найду и убью.",
        "Если проиграешь — я тебя уничтожу.",
        "Угрожать другим игрокам запрещено.",
    )
    return rng.choice(templates)


def _generate_sexual_text(*, rng: random.Random, field: Field) -> str:
    if field == Field.SQUAD_NAME:
        names = (
            "18+ знакомства",
            "Only 18+",
            "Dating 18+",
        )
        return rng.choice(names)

    templates = (
        "Только для 18+, ищем знакомства.",
        "Чат 18+ для взрослых, без обсуждения игры.",
        "Знакомства для взрослых 18+.",
    )
    return rng.choice(templates)


def _expected_decision_for_categories(expected_categories: tuple[str, ...]) -> str:
    return DEFAULT_POLICY.decision_for_categories(set(expected_categories))


def _build_distribution(*, dataset_kind: str, total: int) -> dict[str, int]:
    if dataset_kind not in {"smoke", "full"}:
        raise BatchError("dataset-kind must be smoke or full")

    ratios = {
        "allow": 0.60,
        "spam": 0.15,
        "profanity": 0.10,
        "pii": 0.10,
        "violence": 0.03,
        "sexual": 0.02,
    }

    raw_counts = {name: int(round(total * ratio)) for name, ratio in ratios.items()}
    raw_counts["allow"] += total - sum(raw_counts.values())

    if dataset_kind == "smoke":
        for key in ("spam", "profanity", "pii", "violence", "sexual"):
            if raw_counts[key] == 0:
                raw_counts[key] = 1
                raw_counts["allow"] -= 1
        if raw_counts["allow"] < 0:
            raise BatchError("total is too small for smoke distribution")

    return raw_counts


def generate_examples(
    *, dataset_version: str, dataset_kind: str, total: int, seed: int
) -> list[dict[str, object]]:
    if not dataset_version.strip():
        raise BatchError("dataset-version must not be empty")
    if total <= 0:
        raise BatchError("total must be > 0")

    rng = random.Random(seed)
    dist = _build_distribution(dataset_kind=dataset_kind, total=total)

    generators: list[tuple[str, CategorySpec, TextGenerator]] = [
        ("allow", ALLOW_SPEC, _generate_allow_text),
        ("spam", SPAM_SPEC, _generate_spam_text),
        ("profanity", PROFANITY_SPEC, _generate_profanity_text),
        ("pii", PII_SPEC, _generate_pii_text),
        ("violence", VIOLENCE_SPEC, _generate_violence_text),
        ("sexual", SEXUAL_SPEC, _generate_sexual_text),
    ]

    examples: list[dict[str, object]] = []
    for category_key, spec, generator in generators:
        count = dist.get(category_key, 0)
        for index in range(count):
            field = _choose_field(rng)
            action = _choose_action(rng)
            text = generator(rng=rng, field=field)
            expected_decision = _expected_decision_for_categories(spec.expected_categories)

            example_id = f"gen-{dataset_kind}-{category_key}-{index:05d}"
            examples.append(
                {
                    "id": example_id,
                    "dataset_version": dataset_version,
                    "field": field.value,
                    "action": action.value,
                    "text": text,
                    "expected_categories": list(spec.expected_categories),
                    "expected_decision": expected_decision,
                    "source": "synthetic",
                    "notes": spec.note,
                }
            )

    rng.shuffle(examples)
    return examples


def _write_jsonl(*, out_path: Path, examples: list[dict[str, object]]) -> None:
    lines = [
        json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
        for obj in examples
    ]
    payload = "\n".join(lines) + "\n"
    out_path.write_text(payload, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a synthetic validation dataset (JSONL).")
    parser.add_argument("--dataset-version", default="v1", help="Dataset version string (e.g. v1).")
    parser.add_argument(
        "--dataset-kind",
        default="smoke",
        choices=("smoke", "full"),
        help="Dataset kind: smoke or full.",
    )
    parser.add_argument(
        "--total",
        default=None,
        help="Total number of examples. Defaults: smoke=200, full=5000.",
    )
    parser.add_argument("--seed", default="1", help="Random seed (int).")
    parser.add_argument(
        "--out-path",
        required=True,
        help="Where to write JSONL. Full datasets should not be committed to git.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite out-path if it already exists.",
    )
    args = parser.parse_args(argv)

    total_default = 200 if args.dataset_kind == "smoke" else 5000
    total = (
        total_default if args.total is None else _parse_int(args.total, name="total", min_value=1)
    )
    seed = _parse_int(args.seed, name="seed", min_value=0)

    out_path = Path(args.out_path)
    if out_path.exists() and not args.overwrite:
        raise BatchError("out-path already exists (use --overwrite to replace)")

    examples = generate_examples(
        dataset_version=args.dataset_version,
        dataset_kind=args.dataset_kind,
        total=total,
        seed=seed,
    )
    _write_jsonl(out_path=out_path, examples=examples)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
