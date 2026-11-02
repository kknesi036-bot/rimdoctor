"""Conservative, rule-based analysis. No network, filesystem writes or game access."""
import hashlib
import re

RULES_VERSION = "2026.11.02.2"
PREFIX = re.compile(r"^(?:(?:\[?\d{4}-\d{2}-\d{2}[T ])?\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\]?\s*|\[\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\]\s*)")
START = re.compile(r"(?:\b(?:[\w.]*Exception|Error|ERROR|Fatal)\b|Exception\s+(?:ticking|drawing|loading)|XML\s+error|Could not (?:load|resolve)|Failed to (?:load|apply)|Patch operation .* failed)", re.I)
FRAME = re.compile(r"^(?:at\s|\(wrapper|---|--->|UnityEngine\.|Verse\.(?:Log|LogUtility)|System\.|\[Ref\s|Duplicate stacktrace|\s)")
RULES = [
    ("xml", re.compile(r"XML|PatchOperation|Patch operation|XmlException", re.I), "XML 로딩·패치 오류", "설정 또는 패치 적용 과정에서 문제가 기록됐습니다.", ["원문의 XML 항목·파일명·패치 대상을 확인하세요.", "해당 모드의 게임 버전과 필수 모드 요구사항을 확인하세요."]),
    ("assembly", re.compile(r"TypeLoadException|ReflectionTypeLoadException|FileNotFoundException|Could not load.*(?:assembly|type)|MissingMethodException|BadImageFormatException", re.I), "타입·모듈 로딩 오류", "필요한 타입, 메서드 또는 모듈을 불러오지 못했습니다.", ["관련 모드와 라이브러리가 같은 게임 버전을 지원하는지 확인하세요.", "필수 모드 누락과 중복 설치 여부를 확인하세요."]),
    ("reference", re.compile(r"NullReferenceException|MissingReferenceException|Object reference not set", re.I), "참조 오류", "코드가 사용하려던 객체를 찾지 못했거나 이미 제거된 상태일 수 있습니다.", ["최초 발생 구간과 최근 모드 변경 내역을 비교하세요.", "원본 세이브를 보존하고 별도 테스트 게임에서 재현 여부를 확인하세요."]),
]


def classify(raw: str):
    header = clean(raw.splitlines()[0])
    if re.match(r"Fallback handler could not load library\b", header, re.I):
        return ("loader_notice", "info", "라이브러리 로딩 참고 기록",
                "로더가 특정 라이브러리를 찾지 못했다는 기록입니다. 이 문구만으로 실행 실패를 판단할 수 없습니다.",
                ["플레이에 문제가 없다면 이 기록만으로 모드를 제거하지 마세요.", "실제 실행 실패가 있다면 뒤따르는 예외나 오류를 함께 확인하세요."])
    if re.match(r"Could not resolve reference to object\b", header, re.I):
        return ("save_reference", "warning", "저장 데이터 참조 확인 필요",
                "불러오는 과정에서 저장된 객체 참조를 찾지 못했다는 기록입니다. 플레이 불가능이나 세이브 손상을 확정하는 뜻은 아닙니다.",
                ["인물 관계 등 해당 데이터에 실제로 이상이 있는지 확인하세요.", "특별한 증상이 없다면 원본 세이브를 보존하고 경과를 확인하세요."])
    rule = next((r for r in RULES if r[1].search(raw)), None)
    if rule:
        return rule[0], "error", rule[2], rule[3], rule[4]
    explicit_error = bool(re.search(r"\b(?:[\w.]*Exception|Error|Fatal)\b", header, re.I))
    return ("unknown", "error" if explicit_error else "warning", "분류되지 않은 기록",
            "등록된 진단 규칙 없음",
            ["최초 발생 구간과 게임·모드 버전을 확인하세요.", "실제 증상이 있다면 원문과 함께 해당 모드의 이슈 문서를 확인하세요."])


def clean(line: str) -> str:
    return PREFIX.sub("", line).strip()


def analyze(text: str) -> dict:
    lines = text.splitlines()
    blocks = []
    current = None
    for number, raw in enumerate(lines, 1):
        stripped = clean(raw)
        continuation = bool(current and (FRAME.match(raw) or FRAME.match(stripped)))
        # A fresh Error header starts a new event, even if indented.
        explicit = re.match(r"^(?:\[?(?:ERROR|Error|Fatal)\]?[: ]|Exception\s+(?:ticking|drawing|loading))", stripped)
        starts = bool(START.search(stripped)) and (not continuation or bool(explicit))
        if starts:
            if current:
                blocks.append(current)
            current = {"start_line": number, "end_line": number, "lines": [raw]}
        elif current and stripped and continuation:
            current["lines"].append(raw)
            current["end_line"] = number
        elif current:
            blocks.append(current)
            current = None
    if current:
        blocks.append(current)

    groups = {}
    for block in blocks:
        raw = "\n".join(block["lines"])
        # Preserve numbers, object IDs and paths: aggressive normalization hides distinct errors.
        normalized = "\n".join(clean(line) for line in block["lines"])
        key = hashlib.sha256(normalized.encode()).hexdigest()
        if key not in groups:
            rule_id, severity, title, explanation, next_steps = classify(raw)
            candidates = sorted(set(re.findall(r"\[(?:mod|모드)\s*:\s*([^\]\r\n]+)\]", raw, re.I)))
            groups[key] = {
                "id": key[:12], "title": title, "severity": severity,
                "rule_id": rule_id,
                "explanation": explanation,
                "next_steps": next_steps,
                "related_mod_candidates": candidates,
                "candidate_note": "명시적 [mod: 이름] 표기만 추출합니다. 호출 기록의 이름만으로 모드나 원인을 확정하지 않습니다.",
                "count": 0, "occurrences": [], "preview": clean(block["lines"][0])[:300],
            }
        group = groups[key]
        group["count"] += 1
        group["occurrences"].append({"start_line": block["start_line"], "end_line": block["end_line"], "raw": raw})

    order = {"error": 0, "warning": 1, "info": 2}
    result = sorted(groups.values(), key=lambda g: (order[g["severity"]], -g["count"]))
    return {
        "rules_version": RULES_VERSION,
        "summary": {"line_count": len(lines), "error_count": sum(g["count"] for g in result if g["severity"] == "error"),
                    "warning_count": sum(g["count"] for g in result if g["severity"] == "warning"),
                    "info_count": sum(g["count"] for g in result if g["severity"] == "info"), "group_count": len(result)},
        "groups": result,
        "notice": "오류는 명시적인 오류·예외 기록, 확인 필요는 불확실한 진단 기록, 참고는 단독으로 실패를 뜻하지 않는 기록입니다. 게임 고장이나 모드 충돌을 확정하는 판정이 아닙니다.",
    }
