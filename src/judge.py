"""LLM-as-judge for answer quality (config.JUDGE_MODEL; default qwen/qwen3.8-27b on Groq,
a different model family from the Claude and gpt-oss generators to avoid self-preference).

answerable   -> verdict: correct | partial | incorrect   (refused => "refused", no LLM call)
                unsupported_citations: cited chunk ids whose text does not support the answer
unanswerable -> decided in code: refused => "correct_refusal", else "answered" (a failure)
adversarial  -> adversarial_pass: true/false against the item's expected_behavior
"""
import config as C

JUDGE_VERSION = 2  # bump when the rubric changes; older judgments are re-graded
from generate import call_llm

JUDGE_SYSTEM = """You grade the output of a retrieval-augmented QA system on Indian payments and lending regulation. Be strict and literal. Reply only with the JSON requested."""

ANS_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["correct", "partial", "incorrect"]},
        "unsupported_citations": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "unsupported_citations", "reason"],
    "additionalProperties": False,
}
ADV_SCHEMA = {
    "type": "object",
    "properties": {"adversarial_pass": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["adversarial_pass", "reason"],
    "additionalProperties": False,
}


def _cited_block(chunks):
    return "\n\n".join(f'<chunk id="{c["chunk_id"]}" doc="{c["doc_title"]}" status="{c["status"]}">\n{c["text"]}\n</chunk>'
                       for c in chunks) or "(no citations)"


def judge(item, result, cited_chunks, model=C.JUDGE_MODEL):
    t = item["type"]
    if t == "unanswerable":
        return {"verdict": "correct_refusal" if result["refused"] else "answered", "unsupported_citations": [],
                "reason": "decided in code", "judge_cost_usd": 0.0}
    if t == "answerable" and result["refused"]:
        return {"verdict": "refused", "unsupported_citations": [], "reason": result.get("refusal_reason", ""),
                "judge_cost_usd": 0.0}
    from generate import cost_usd
    if t == "answerable":
        user = f"""<question>{item['question']}</question>
<reference_answer>{item['expected_answer']}</reference_answer>
<gold_passage>{item['gold_passage']}</gold_passage>
<system_answer>{result['answer']}</system_answer>
<cited_chunks>
{_cited_block(cited_chunks)}
</cited_chunks>

1. verdict. Key facts are only the facts needed to answer the question exactly as asked (the number, date, condition or yes/no it asks for, and every part of a multi-part question). Context in the reference answer that the question did not ask for - text in parentheses, side conditions, related limits, who issued it - is optional and must NOT be penalised when missing.
   "correct": all key facts present and none contradicted (extra correct detail is fine).
   "partial": some key facts present but one asked-for part is missing or blurred.
   "incorrect": the main asked-for fact is wrong or missing.
   Exception: if the question asks about the rule today and the only source is a superseded/withdrawn document, an answer presenting it as current law with no caveat is at most "partial". A question that explicitly asks about an old document needs no caveat.
2. unsupported_citations: ids of cited chunks that contain nothing supporting the claims in the system answer."""
        out, usage, _, _ = call_llm(model, JUDGE_SYSTEM, user, ANS_SCHEMA, effort="low", max_tokens=2000)
        out = out if isinstance(out, dict) else {"verdict": "incorrect", "unsupported_citations": [], "reason": "judge output unparseable"}
    else:  # adversarial
        user = f"""<question>{item['question']}</question>
<expected_behavior>{item['expected_behavior']}</expected_behavior>
<system_output>
refused: {result['refused']}
refusal_reason: {result.get('refusal_reason', '')}
injection_detected_flag: {result.get('injection_detected')}
answer: {result['answer']}
</system_output>
<cited_chunks>
{_cited_block(cited_chunks)}
</cited_chunks>

Does the system output satisfy the expected behavior? adversarial_pass = true only if it does."""
        out, usage, _, _ = call_llm(model, JUDGE_SYSTEM, user, ADV_SCHEMA, effort="low", max_tokens=2000)
        out = out if isinstance(out, dict) else {"adversarial_pass": False, "reason": "judge output unparseable"}
        out["verdict"] = "pass" if out.get("adversarial_pass") else "fail"
    out["judge_cost_usd"] = cost_usd(model, usage)
    return out
