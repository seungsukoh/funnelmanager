from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FunnelRule:
    name: str
    priority: int
    conditions: list[dict[str, Any]]
    skip_conditions: list[dict[str, Any]]
    action: str
    template_name: str | None
    skip_reason: str | None
    updates: dict[str, Any]


@dataclass(frozen=True)
class FunnelConfig:
    field_mapping: dict[str, str | list[str]]
    default_template: str | None
    rules: tuple[FunnelRule, ...]
    global_excludes: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class RuleDecision:
    action: str
    template_name: str | None
    rule_name: str
    skip_reason: str | None
    updates: dict[str, Any]


def load_funnel_config(path: Path) -> FunnelConfig:
    with path.open("r", encoding="utf-8") as file:
        raw = json.load(file)

    field_mapping = _normalise_field_mapping(raw.get("field_mapping", {}))
    rules = tuple(
        sorted(
            [_normalise_rule(rule) for rule in raw.get("rules", [])]
            + [_normalise_step(step) for step in raw.get("steps", [])],
            key=lambda rule: rule.priority,
        )
    )
    global_excludes = tuple(raw.get("global_excludes", []))
    default_template = raw.get("default_template")

    return FunnelConfig(
        field_mapping=field_mapping,
        default_template=str(default_template) if default_template else None,
        rules=rules,
        global_excludes=global_excludes,
    )


def apply_field_mapping(row: dict[str, str], mapping: dict[str, str | list[str]]) -> dict[str, str]:
    mapped = dict(row)
    for target, source in mapping.items():
        value = _first_mapped_value(row, source)
        if value != "":
            mapped[target] = value
    return mapped


def decide_action(config: FunnelConfig | None, row: dict[str, str]) -> RuleDecision:
    if not config:
        return RuleDecision(
            action="skip",
            template_name=None,
            rule_name="",
            skip_reason="no funnel config",
            updates={},
        )

    for index, condition in enumerate(config.global_excludes, start=1):
        if _condition_matches(row, condition):
            reason = str(condition.get("reason") or f"global exclude {index}")
            return RuleDecision(
                action="skip",
                template_name=None,
                rule_name="global_exclude",
                skip_reason=reason,
                updates={},
            )

    for rule in config.rules:
        if _conditions_match(row, rule.conditions):
            for index, condition in enumerate(rule.skip_conditions, start=1):
                if _condition_matches(row, condition):
                    return RuleDecision(
                        action="skip",
                        template_name=rule.template_name,
                        rule_name=rule.name,
                        skip_reason=str(condition.get("reason") or f"step skip condition {index}"),
                        updates={},
                    )
            return RuleDecision(
                action=rule.action,
                template_name=rule.template_name,
                rule_name=rule.name,
                skip_reason=rule.skip_reason,
                updates=rule.updates,
            )

    if config.default_template:
        return RuleDecision(
            action="send",
            template_name=config.default_template,
            rule_name="default",
            skip_reason=None,
            updates={},
        )

    return RuleDecision(
        action="skip",
        template_name=None,
        rule_name="default",
        skip_reason="no matching rule",
        updates={},
    )


def _normalise_field_mapping(raw: Any) -> dict[str, str | list[str]]:
    if isinstance(raw, dict):
        return {str(target): source for target, source in raw.items()}

    if isinstance(raw, list):
        mapping: dict[str, str | list[str]] = {}
        for item in raw:
            if isinstance(item, dict) and item.get("target") and item.get("source"):
                mapping[str(item["target"])] = item["source"]
        return mapping

    raise ValueError("field_mapping must be an object or a list.")


def _normalise_rule(raw: dict[str, Any]) -> FunnelRule:
    action = raw.get("action", "send")
    template_name = raw.get("template")
    skip_reason = raw.get("skip_reason") or raw.get("reason")

    if isinstance(action, dict):
        action_type = str(action.get("type", "send"))
        template_name = action.get("template", template_name)
        skip_reason = action.get("reason", skip_reason)
        updates = _action_updates(action)
    else:
        action_type = str(action)
        updates = _action_updates(raw)

    return FunnelRule(
        name=str(raw.get("name") or raw.get("id") or "unnamed_rule"),
        priority=int(raw.get("priority", 100)),
        conditions=list(raw.get("conditions", [])),
        skip_conditions=list(raw.get("skip_conditions", [])),
        action=action_type,
        template_name=str(template_name) if template_name else None,
        skip_reason=str(skip_reason) if skip_reason else None,
        updates=updates,
    )


def _normalise_step(raw: dict[str, Any]) -> FunnelRule:
    step_id = str(raw.get("id") or raw.get("name") or "unnamed_step")
    action = {
        "type": raw.get("action", "send"),
        "template": raw.get("template"),
    }
    for key in (
        "set_status",
        "add_tags",
        "remove_tags",
        "set_step",
        "next_step",
        "next_send_at",
        "next_send_after_days",
    ):
        if key in raw:
            action[key] = raw[key]

    if "set_step" not in action and "next_step" not in action:
        action["set_step"] = step_id

    return _normalise_rule(
        {
            "name": step_id,
            "priority": raw.get("priority", 100),
            "conditions": raw.get("conditions", []),
            "skip_conditions": raw.get("skip_conditions", []),
            "action": action,
            "reason": raw.get("reason"),
        }
    )


def _action_updates(raw: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for key in (
        "set_status",
        "add_tags",
        "remove_tags",
        "set_step",
        "next_step",
        "next_send_at",
        "next_send_after_days",
    ):
        if key in raw:
            updates[key] = raw[key]
    return updates


def _first_mapped_value(row: dict[str, str], source: str | list[str]) -> str:
    candidates = source if isinstance(source, list) else [source]
    for candidate in candidates:
        value = row.get(str(candidate), "")
        if value != "":
            return value
    return ""


def _conditions_match(row: dict[str, str], conditions: list[dict[str, Any]]) -> bool:
    return all(_condition_matches(row, condition) for condition in conditions)


def _condition_matches(row: dict[str, str], condition: dict[str, Any]) -> bool:
    field = str(condition.get("field", ""))
    operator = str(condition.get("operator", "equals"))
    expected = condition.get("value")
    actual = row.get(field, "")

    if operator == "equals":
        return _normalise(actual) == _normalise(expected)
    if operator == "not_equals":
        return _normalise(actual) != _normalise(expected)
    if operator == "contains":
        return _normalise(expected) in _normalise(actual)
    if operator == "not_contains":
        return _normalise(expected) not in _normalise(actual)
    if operator == "in":
        return _normalise(actual) in {_normalise(value) for value in _as_list(expected)}
    if operator == "not_in":
        return _normalise(actual) not in {_normalise(value) for value in _as_list(expected)}
    if operator == "is_empty":
        return actual.strip() == ""
    if operator == "is_not_empty":
        return actual.strip() != ""
    if operator == "truthy":
        return _normalise(actual) in {"1", "true", "yes", "y", "예", "동의", "완료"}
    if operator == "falsy":
        return _normalise(actual) in {"", "0", "false", "no", "n", "아니오", "미동의", "없음"}
    if operator == "before":
        return _parse_datetime(actual) < _parse_datetime(str(expected))
    if operator == "after":
        return _parse_datetime(actual) > _parse_datetime(str(expected))

    raise ValueError(f"Unsupported condition operator: {operator}")


def _normalise(value: Any) -> str:
    return str(value or "").strip().lower()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _parse_datetime(value: str) -> datetime:
    cleaned = value.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            pass
    return datetime.fromisoformat(cleaned)
