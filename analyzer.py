import re


def analyze_verilog(source: str, filename: str = "") -> dict:
    lines = source.splitlines()
    issues = []

    _check_balance(lines, issues)
    _check_blocking_in_sequential(lines, issues)
    _check_unused_signals(source, lines, issues)
    _check_case_default(lines, issues)
    _check_incomplete_if(lines, issues)
    _check_magic_numbers(lines, issues)
    _check_module_structure(source, lines, issues)
    _check_sensitivity_list(lines, issues)

    if not issues:
        issues.append({
            "severity": "info",
            "line": 1,
            "message": "No issues detected. Code follows standard Verilog conventions.",
        })

    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    infos = [i for i in issues if i["severity"] == "info"]

    score = _compute_score(len(errors), len(warnings), len(infos), len(lines))

    # sort issues top-to-bottom by line number for readability
    issues.sort(key=lambda i: i["line"])

    return {
        "score": score,
        "counts": {
            "errors": len(errors),
            "warnings": len(warnings),
            "infos": len(infos),
        },
        "issues": issues,
        "line_count": len(lines),
        "filename": filename,
    }


# ─────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────
def _compute_score(n_err, n_warn, n_info, n_lines):
    score = 100
    score -= n_err * 12
    score -= n_warn * 4
    score -= n_info * 1
    score = max(0, min(100, score))
    return score


# ─────────────────────────────────────────────────────────
# Rule: begin/end and module/endmodule balance
# ─────────────────────────────────────────────────────────
def _check_balance(lines, issues):
    stack = []
    module_depth = 0
    in_block_comment = False

    for idx, raw_line in enumerate(lines, start=1):
        line = _strip_comments(raw_line, in_block_comment)
        if "/*" in raw_line and "*/" not in raw_line.split("/*", 1)[1]:
            in_block_comment = True
        elif "*/" in raw_line:
            in_block_comment = False

        tokens = re.findall(r"\b(module|endmodule|begin|end|function|endfunction|task|endtask)\b", line)
        for tok in tokens:
            if tok in ("module",):
                module_depth += 1
            elif tok == "endmodule":
                module_depth -= 1
                if module_depth < 0:
                    issues.append({
                        "severity": "error",
                        "line": idx,
                        "message": "Found 'endmodule' with no matching 'module' declaration.",
                    })
                    module_depth = 0
            elif tok in ("begin", "function", "task"):
                stack.append((tok, idx))
            elif tok in ("end", "endfunction", "endtask"):
                if not stack:
                    issues.append({
                        "severity": "error",
                        "line": idx,
                        "message": f"Unmatched '{tok}' — no corresponding opening block.",
                    })
                else:
                    stack.pop()

    if module_depth > 0:
        issues.append({
            "severity": "error",
            "line": len(lines),
            "message": "Missing 'endmodule' — module declaration is not closed.",
        })

    for tok, line_no in stack:
        issues.append({
            "severity": "error",
            "line": line_no,
            "message": f"Unclosed '{tok}' block — missing matching 'end'.",
        })


# ─────────────────────────────────────────────────────────
# Rule: blocking assignment (=) inside sequential always block
# ─────────────────────────────────────────────────────────
def _check_blocking_in_sequential(lines, issues):
    in_seq_block = False
    block_depth = 0

    for idx, line in enumerate(lines, start=1):
        clean = _strip_comments(line)

        if re.search(r"always\s*@\s*\(\s*posedge|always\s*@\s*\(\s*negedge", clean):
            in_seq_block = True
            block_depth = 0

        if in_seq_block:
            block_depth += len(re.findall(r"\bbegin\b", clean))
            block_depth -= len(re.findall(r"\bend\b", clean))

            # blocking assignment: identifier = expr; (not <=, not ==, not !=, not >=)
            match = re.search(r"\b(\w+)\s*=(?!=)[^=<>]", clean)
            if match and "<=" not in clean and not clean.strip().startswith(("if", "case", "for", "while")):
                issues.append({
                    "severity": "warning",
                    "line": idx,
                    "message": f"Line {idx}: Consider using non-blocking assignment (<=) "
                               f"instead of blocking (=) inside a clocked always block.",
                })

            if block_depth <= 0 and "begin" not in clean and "end" in clean:
                in_seq_block = False


# ─────────────────────────────────────────────────────────
# Rule: declared but unused signals
# ─────────────────────────────────────────────────────────
def _check_unused_signals(source, lines, issues):
    decl_pattern = re.compile(
        r"\b(?:reg|wire|logic|integer)\s*(?:\[[^\]]*\])?\s*([a-zA-Z_]\w*)\s*(?:[,;=]|$)"
    )

    declared = {}
    for idx, line in enumerate(lines, start=1):
        clean = _strip_comments(line)
        for m in decl_pattern.finditer(clean):
            name = m.group(1)
            if name not in declared:
                declared[name] = idx

    for name, decl_line in declared.items():
        # count usages elsewhere in the file (excluding the declaration line itself)
        usage_pattern = re.compile(r"\b" + re.escape(name) + r"\b")
        usages = 0
        for idx, line in enumerate(lines, start=1):
            if idx == decl_line:
                continue
            if usage_pattern.search(_strip_comments(line)):
                usages += 1
        if usages == 0:
            issues.append({
                "severity": "info",
                "line": decl_line,
                "message": f"Signal '{name}' is declared but never used.",
            })


# ─────────────────────────────────────────────────────────
# Rule: case statement missing default
# ─────────────────────────────────────────────────────────
def _check_case_default(lines, issues):
    case_start = None
    has_default = False
    depth = 0

    for idx, line in enumerate(lines, start=1):
        clean = _strip_comments(line)

        if re.search(r"\bcase[xz]?\s*\(", clean):
            case_start = idx
            has_default = False
            depth = 0

        if case_start is not None:
            if re.search(r"\bdefault\s*:", clean):
                has_default = True
            depth += len(re.findall(r"\bbegin\b", clean))
            depth -= len(re.findall(r"\bend\b", clean))
            if re.search(r"\bendcase\b", clean):
                if not has_default:
                    issues.append({
                        "severity": "warning",
                        "line": case_start,
                        "message": "Case statement has no 'default' branch — "
                                   "may cause unintended latch inference.",
                    })
                case_start = None


# ─────────────────────────────────────────────────────────
# Rule: incomplete if/else inside combinational always (latch inference)
# ─────────────────────────────────────────────────────────
def _check_incomplete_if(lines, issues):
    in_comb_block = False
    saw_if = False
    saw_else = False
    block_start = None

    for idx, line in enumerate(lines, start=1):
        clean = _strip_comments(line)

        if re.search(r"always\s*@\s*\(\s*\*\s*\)|always_comb", clean):
            in_comb_block = True
            saw_if = False
            saw_else = False
            block_start = idx
            continue

        if in_comb_block:
            if re.search(r"\bif\s*\(", clean):
                saw_if = True
            if re.search(r"\belse\b", clean):
                saw_else = True
            if re.search(r"\bend\b", clean) and "begin" not in clean:
                if saw_if and not saw_else:
                    issues.append({
                        "severity": "warning",
                        "line": block_start,
                        "message": "Combinational block contains 'if' without 'else' — "
                                   "this may infer an unintended latch.",
                    })
                in_comb_block = False


# ─────────────────────────────────────────────────────────
# Rule: magic numbers (unparameterized hard-coded widths/values)
# ─────────────────────────────────────────────────────────
def _check_magic_numbers(lines, issues):
    pattern = re.compile(r"\[\s*(\d{2,})\s*:\s*0\s*\]")
    seen_lines = set()
    for idx, line in enumerate(lines, start=1):
        clean = _strip_comments(line)
        for m in pattern.finditer(clean):
            width = int(m.group(1)) + 1
            if width >= 8 and idx not in seen_lines:
                issues.append({
                    "severity": "info",
                    "line": idx,
                    "message": f"Hard-coded bus width [{m.group(1)}:0] ({width}-bit) — "
                               f"consider using a parameter for maintainability.",
                })
                seen_lines.add(idx)


# ─────────────────────────────────────────────────────────
# Rule: basic module structure sanity (ports, syntax near 'end')
# ─────────────────────────────────────────────────────────
def _check_module_structure(source, lines, issues):
    if not re.search(r"\bmodule\b", source):
        issues.append({
            "severity": "error",
            "line": 1,
            "message": "No 'module' declaration found in file.",
        })
        return

    for idx, line in enumerate(lines, start=1):
        clean = _strip_comments(line).strip()
        # naive syntax error detector: a lone 'end' followed by an unexpected token
        # (allow legitimate continuations: else, endmodule/endfunction/endtask/endcase/endgenerate)
        if re.match(r"^end\s+\w", clean) and not re.match(
            r"^end\s*(module|function|task|case|generate|else\b)", clean
        ):
            issues.append({
                "severity": "error",
                "line": idx,
                "message": "Syntax error near 'end' — unexpected token after block terminator.",
            })

        # missing semicolon heuristic: assign without trailing ;
        if re.match(r"^assign\s+.+[^;]\s*$", clean) and clean and not clean.endswith(("begin", "(", ",")):
            if not clean.endswith(";"):
                issues.append({
                    "severity": "error",
                    "line": idx,
                    "message": "Missing semicolon at end of 'assign' statement.",
                })


# ─────────────────────────────────────────────────────────
# Rule: always block with empty/missing sensitivity list items
# ─────────────────────────────────────────────────────────
def _check_sensitivity_list(lines, issues):
    for idx, line in enumerate(lines, start=1):
        clean = _strip_comments(line)
        m = re.search(r"always\s*@\s*\(([^)]*)\)", clean)
        if m:
            sens = m.group(1).strip()
            if sens == "":
                issues.append({
                    "severity": "warning",
                    "line": idx,
                    "message": "Empty sensitivity list in 'always @()' — block will never trigger.",
                })


# ─────────────────────────────────────────────────────────
# Helper: strip // and (single-line) /* */ comments
# ─────────────────────────────────────────────────────────
def _strip_comments(line, in_block_comment=False):
    if in_block_comment:
        if "*/" in line:
            return line.split("*/", 1)[1]
        return ""
    line = re.sub(r"/\*.*?\*/", "", line)
    line = line.split("//", 1)[0]
    return line