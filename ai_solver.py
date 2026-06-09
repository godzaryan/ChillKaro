"""
AI Ensemble Solver (Batch Mode)
Sends ALL questions to 3 AI models at once, then uses per-question majority voting.
Models: Google Gemini 2.5 Flash | Groq Llama 3.3 70B | Cerebras GPT OSS 120B
"""

import requests
import re
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter

# --- API Keys ---
GEMINI_API_KEY = ""
GROQ_API_KEY = ""
CEREBRAS_API_KEY = ""


def configure_keys(gemini_key, groq_key, cerebras_key):
    global GEMINI_API_KEY, GROQ_API_KEY, CEREBRAS_API_KEY
    GEMINI_API_KEY = gemini_key
    GROQ_API_KEY = groq_key
    CEREBRAS_API_KEY = cerebras_key


def build_batch_prompt(questions):
    """
    Build ONE prompt containing ALL questions for the AI to answer at once.
    questions = list of {"number": int, "text": str, "options": [str, ...]}
    """
    lines = []
    lines.append("You are an expert academic exam solver with deep knowledge across all university subjects.")
    lines.append("Below are ALL the questions from an exam. Answer every single one.\n")

    for q in questions:
        opts = "\n".join([f"    {i+1}) {o}" for i, o in enumerate(q["options"])])
        lines.append(f"Q{q['number']}:")
        lines.append(q["text"])
        lines.append(f"  Options:")
        lines.append(opts)
        lines.append("")

    lines.append("INSTRUCTIONS:")
    lines.append("- Answer ALL questions above.")
    lines.append("- For each question, respond with EXACTLY this format:  Q<number>: <option_number>")
    lines.append("- Example output format:")
    lines.append("  Q1: 2")
    lines.append("  Q2: 4")
    lines.append("  Q3: 1")
    lines.append("- Respond with ONLY the answers in the format above. No explanations.")
    lines.append("- If unsure, make your best educated guess. Never skip a question.")
    lines.append("\nANSWERS:")

    return "\n".join(lines)


def ask_gemini(prompt):
    """Query Google Gemini 2.5 Flash Lite."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 500}
    }
    try:
        r = requests.post(url, json=payload, timeout=60, verify=False)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"    [!] Gemini API error: {e}")
        return None


def ask_groq(prompt):
    """Query Groq — Llama 3.3 70B Versatile."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    h = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 500
    }
    try:
        r = requests.post(url, json=payload, headers=h, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"    [!] Groq API error: {e}")
        return None


def ask_cerebras(prompt):
    """Query Cerebras — GPT OSS 120B."""
    url = "https://api.cerebras.ai/v1/chat/completions"
    h = {"Authorization": f"Bearer {CEREBRAS_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-oss-120b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 500
    }
    try:
        r = requests.post(url, json=payload, headers=h, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"    [!] Cerebras API error: {e}")
        return None


def parse_batch_response(response_text, total_questions):
    """
    Parse AI batch response into a dict of {question_number: option_number}.
    Expected format per line: Q1: 2  or  Q1:2  or  1: 2  or  1. 2
    """
    answers = {}
    if not response_text:
        return answers

    for line in response_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Match patterns like: Q1: 2, Q1:2, 1: 2, 1. 2, 1) 2
        match = re.match(r'Q?(\d+)\s*[:.)\-]\s*(\d+)', line, re.IGNORECASE)
        if match:
            q_num = int(match.group(1))
            a_num = int(match.group(2))
            if 1 <= q_num <= total_questions and 1 <= a_num <= 10:
                answers[q_num] = a_num

    return answers


def solve_all_questions(questions):
    """
    Main entry point — solves ALL questions using 3-AI ensemble with batch prompting.

    Args:
        questions: list of dicts, each with:
            - "number": int (1-indexed)
            - "text": str (question text)
            - "options": list of str (option display texts)
            - "option_values": list of str (form submission values)
            - "metadata": dict (q_id, option_order, q_type, display_pos, screen)

    Returns:
        list of dicts with same structure + "ai_answer_index" (0-based) and "ai_answer_value"
    """
    total = len(questions)
    prompt = build_batch_prompt(questions)

    print(f"\n{'='*70}")
    print(f"  PHASE 2: AI ENSEMBLE SOLVING — {total} questions")
    print(f"{'='*70}")
    print(f"  Sending all {total} questions to 3 AI models in parallel...")
    print(f"  Models: Gemini 2.5 Flash | Groq Llama 3.3 70B | Cerebras GPT OSS 120B")
    print(f"{'='*70}\n")

    # Query all 3 AIs in parallel (just 3 API calls total!)
    raw_responses = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(ask_gemini, prompt): "Gemini",
            executor.submit(ask_groq, prompt): "Groq",
            executor.submit(ask_cerebras, prompt): "Cerebras",
        }
        for future in as_completed(futures):
            model = futures[future]
            try:
                raw_responses[model] = future.result()
                status = "OK" if raw_responses[model] else "FAILED"
            except Exception:
                raw_responses[model] = None
                status = "ERROR"
            print(f"  [{model}] Response: {status}")

    # Parse each AI's response into answer maps
    parsed = {}
    for model, raw in raw_responses.items():
        parsed[model] = parse_batch_response(raw, total)
        answered = len(parsed[model])
        print(f"  [{model}] Parsed {answered}/{total} answers")

    # Majority voting per question
    print(f"\n{'='*70}")
    print(f"  AI ANSWER SUMMARY")
    print(f"{'='*70}")
    print(f"  {'Q#':<5} {'Gemini':<10} {'Groq':<10} {'Cerebras':<10} {'FINAL':<10} {'Method'}")
    print(f"  {'—'*4} {'—'*9} {'—'*9} {'—'*9} {'—'*9} {'—'*20}")

    consensus_count = 0
    tiebreak_count = 0
    fallback_count = 0

    for q in questions:
        qn = q["number"]
        num_options = len(q["options"])

        # Get each model's vote for this question
        votes = {}
        for model in ["Gemini", "Groq", "Cerebras"]:
            v = parsed[model].get(qn)
            if v and 1 <= v <= num_options:
                votes[model] = v
            else:
                votes[model] = None

        # Display individual votes
        g = f"Opt {votes['Gemini']}" if votes['Gemini'] else "—"
        r = f"Opt {votes['Groq']}" if votes['Groq'] else "—"
        c = f"Opt {votes['Cerebras']}" if votes['Cerebras'] else "—"

        # Majority vote
        valid_votes = [v for v in votes.values() if v is not None]

        if not valid_votes:
            # All failed — random
            final = random.randint(1, num_options)
            method = "RANDOM (all failed)"
            fallback_count += 1
        elif len(valid_votes) == 1:
            final = valid_votes[0]
            method = "SINGLE MODEL"
            tiebreak_count += 1
        else:
            vote_counts = Counter(valid_votes)
            most_common = vote_counts.most_common()

            if most_common[0][1] >= 2:
                final = most_common[0][0]
                count = most_common[0][1]
                method = f"CONSENSUS ({count}/3)"
                consensus_count += 1
            else:
                # All 3 different — trust Gemini
                if votes["Gemini"]:
                    final = votes["Gemini"]
                    method = "TIEBREAK (Gemini)"
                else:
                    final = most_common[0][0]
                    method = "TIEBREAK (first)"
                tiebreak_count += 1

        f_str = f"Opt {final}"
        print(f"  Q{qn:<4} {g:<10} {r:<10} {c:<10} {f_str:<10} {method}")

        # Store the final answer
        q["ai_answer_index"] = final - 1  # 0-based index
        q["ai_answer_value"] = q["option_values"][final - 1]

    # Summary stats
    print(f"\n  {'='*60}")
    print(f"  CONFIDENCE BREAKDOWN:")
    print(f"    Consensus (2-3 models agree) : {consensus_count}/{total} questions")
    print(f"    Tiebreak / Single model      : {tiebreak_count}/{total} questions")
    print(f"    Random fallback (AI failed)  : {fallback_count}/{total} questions")
    print(f"    Estimated accuracy           : ~{int((consensus_count * 90 + tiebreak_count * 70 + fallback_count * 25) / max(total, 1))}%")
    print(f"  {'='*60}\n")

    return questions
