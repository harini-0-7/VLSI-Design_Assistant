import re


def generate_optimizations(source: str, analysis_result: dict) -> list:
    suggestions = []

    suggestions += _suggest_logic_reduction(source)
    suggestions += _suggest_timing_improvements(source)
    suggestions += _suggest_power_reduction(source, analysis_result)
    suggestions += _suggest_from_issues(analysis_result)

    # de-duplicate by title, keep first occurrence
    seen = set()
    unique = []
    for s in suggestions:
        if s["title"] not in seen:
            unique.append(s)
            seen.add(s["title"])

    return unique


# ─────────────────────────────────────────────────────────
# Logic usage suggestions
# ─────────────────────────────────────────────────────────
def _suggest_logic_reduction(source):
    out = []

    if re.search(r"if\s*\(.*?\)\s*.*?else\s*if", source, re.S):
        nested_if_count = len(re.findall(r"\belse\s+if\b", source))
        if nested_if_count >= 2:
            out.append({
                "title": "Reduce Logic Usage",
                "impact": "high",
                "description": "Consider using bitwise operators or a case statement instead of "
                               "long if-else-if chains to reduce comparator logic.",
            })

    if re.search(r"\*\s*\d", source) or re.search(r"\d\s*\*\s*\w", source):
        out.append({
            "title": "Replace Multiplication with Shifts",
            "impact": "medium",
            "description": "Multiplications by constants can often be replaced with shift "
                           "and add operations, reducing area on FPGA/ASIC targets.",
        })

    return out


# ─────────────────────────────────────────────────────────
# Timing suggestions
# ─────────────────────────────────────────────────────────
def _suggest_timing_improvements(source):
    out = []

    # long combinational chain heuristic: many sequential assigns inside one always @(*)
    comb_blocks = re.findall(r"always\s*@\s*\(\s*\*\s*\).*?end", source, re.S)
    for block in comb_blocks:
        assign_count = len(re.findall(r";", block))
        if assign_count >= 6:
            out.append({
                "title": "Improve Timing",
                "impact": "medium",
                "description": "Pipeline the critical path for better performance — this "
                               "combinational block has a long logic chain that may limit "
                               "maximum clock frequency.",
            })
            break

    if re.search(r"always\s*@\s*\(\s*posedge\s+\w+\s*,\s*posedge\s+\w+\s*\)", source):
        out.append({
            "title": "Avoid Dual-Edge Sensitivity",
            "impact": "medium",
            "description": "Multiple posedge-sensitive signals in one always block can "
                           "complicate timing closure. Consider separating clock domains.",
        })

    return out


# ─────────────────────────────────────────────────────────
# Power suggestions
# ─────────────────────────────────────────────────────────
def _suggest_power_reduction(source, analysis_result):
    out = []

    unused = [i for i in analysis_result["issues"] if "never used" in i["message"]]
    if unused:
        out.append({
            "title": "Reduce Power",
            "impact": "low",
            "description": "Remove unused signals to reduce power consumption — "
                           f"{len(unused)} unused signal(s) detected.",
        })

    if re.search(r"always\s*@\s*\(\s*\*\s*\)", source) and "clk" in source.lower():
        out.append({
            "title": "Add Clock Gating",
            "impact": "low",
            "description": "Consider clock gating idle functional blocks to reduce "
                           "dynamic power draw during inactive cycles.",
        })

    return out


# ─────────────────────────────────────────────────────────
# Suggestions derived directly from analyzer issues
# ─────────────────────────────────────────────────────────
def _suggest_from_issues(analysis_result):
    out = []

    has_latch_warning = any("latch" in i["message"].lower() for i in analysis_result["issues"])
    if has_latch_warning:
        out.append({
            "title": "Eliminate Inferred Latches",
            "impact": "high",
            "description": "Add 'else' branches or default case values to combinational "
                           "blocks to avoid unintended latch inference, which wastes area "
                           "and complicates timing.",
        })

    has_blocking_warning = any("non-blocking" in i["message"].lower() for i in analysis_result["issues"])
    if has_blocking_warning:
        out.append({
            "title": "Fix Blocking Assignments",
            "impact": "medium",
            "description": "Use non-blocking assignments (<=) in all clocked always blocks "
                           "to ensure correct simulation/synthesis match.",
        })

    if not out and analysis_result["score"] >= 90:
        out.append({
            "title": "Design Looks Clean",
            "impact": "low",
            "description": "No major optimization opportunities found. Code follows good "
                           "synthesizable Verilog practices.",
        })

    return out